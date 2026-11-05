"""Merging two Person records that turn out to be the same person, and undoing a merge.

plan_merge() describes what a merge would do and whether anything blocks it, for the admin's
preview screen. merge_people() does it: every row pointing at the removed person is repointed to
the kept one, true duplicates are dropped, the removed person is deleted, and their old URL
redirects to the kept person. Everything deleted and every foreign key moved is recorded on a
PersonMerge row, which undo_merge() uses to put it all back exactly (same primary keys).

What counts as a conflict:
  - Both people are candidates in the same election. In the same district, it's one candidacy
    entered twice: the moderator picks which row to keep, and the other row's election results
    (and any suggestion pointing at it) move onto the kept row. In different districts, the
    merge is blocked -- that looks like two different people.
  - Both have a commissioner term covering the same dates. An identical term (same district,
    same dates) is a duplicate and the removed person's copy is dropped. Any other overlap
    blocks the merge -- no one serves two seats at once.
  - The same link URL or the same alias on both: the removed person's copy is dropped.

Production gets a merge through sync_production.sh: `push --prune` removes the deleted rows
there. An undo restores the original primary keys, so a normal push brings them back.
"""
import datetime
import json
from dataclasses import dataclass, field

from django.apps import apps
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from simple_history.utils import update_change_reason

from .models import (
    Candidate, CommissionerTerm, ElectionResult, Person, PersonAlias, PersonImportRow, PersonLink, PersonMerge,
    PersonSlugRedirect, Suggestion, WriteInWinner,
)


class _ExactJSONEncoder(DjangoJSONEncoder):
    """DjangoJSONEncoder rounds datetimes to milliseconds; an undo should restore them exactly."""

    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return super().default(o)


class MergeError(Exception):
    """The merge (or undo) can't go ahead. str(exception) is shown to the moderator."""


@dataclass
class CandidacyConflict:
    election: object
    kept_candidacy: Candidate
    removed_candidacy: Candidate

    @property
    def same_district(self):
        return self.kept_candidacy.district_id == self.removed_candidacy.district_id


@dataclass
class MergePlan:
    kept: Person
    removed: Person
    blockers: list = field(default_factory=list)
    candidacy_conflicts: list = field(default_factory=list)
    duplicate_terms: list = field(default_factory=list)   # removed person's copies, to drop
    duplicate_links: list = field(default_factory=list)
    duplicate_aliases: list = field(default_factory=list)

    @property
    def can_merge(self):
        return not self.blockers


def _terms_overlap(a, b):
    # A shared boundary day is the normal same-day handoff, not an overlap (see CommissionerTerm.clean).
    return a.start_date < b.end_date and b.start_date < a.end_date


def plan_merge(kept, removed):
    plan = MergePlan(kept=kept, removed=removed)
    if kept.pk == removed.pk:
        plan.blockers.append('Pick two different people.')
        return plan

    kept_by_election = {c.election_id: c for c in kept.candidacies.select_related('election', 'district')}
    for candidacy in removed.candidacies.select_related('election', 'district'):
        other = kept_by_election.get(candidacy.election_id)
        if other is None:
            continue
        conflict = CandidacyConflict(candidacy.election, other, candidacy)
        plan.candidacy_conflicts.append(conflict)
        if not conflict.same_district:
            plan.blockers.append(
                f'Both are {candidacy.election.year} candidates, in different districts '
                f'(SMD {other.district.designator} and SMD {candidacy.district.designator}) -- '
                'that looks like two different people.'
            )

    kept_terms = list(kept.commissioner_terms.select_related('district'))
    for term in removed.commissioner_terms.select_related('district'):
        for other in kept_terms:
            if (term.district_id, term.start_date, term.end_date) == (other.district_id, other.start_date, other.end_date):
                plan.duplicate_terms.append(term)
                break
            if _terms_overlap(term, other):
                plan.blockers.append(
                    f'Overlapping commissioner terms: {other} and {term}. Fix or remove one of them first.'
                )
                break

    kept_urls = set(kept.links.values_list('url', flat=True))
    plan.duplicate_links = [link for link in removed.links.all() if link.url in kept_urls]
    kept_names = set(kept.aliases.values_list('name', flat=True))
    plan.duplicate_aliases = [alias for alias in removed.aliases.all() if alias.name in kept_names]
    return plan


class _Recorder:
    """Collects what a merge changes, then writes the PersonMerge row."""

    def __init__(self, reason):
        self.reason = reason
        self.moved = []
        self.deleted = []

    def move(self, obj, field_name, new_value):
        attname = obj._meta.get_field(field_name).attname
        self.moved.append([obj._meta.label, obj.pk, field_name, getattr(obj, attname)])
        setattr(obj, attname, new_value.pk if new_value is not None else None)
        obj.save(update_fields=[field_name])
        if hasattr(type(obj), 'history'):
            update_change_reason(obj, self.reason)

    def delete(self, obj):
        self.deleted.extend(serializers.serialize('python', [obj]))
        obj.delete()


@transaction.atomic
def merge_people(kept, removed, keep_candidacy=None):
    """Merges `removed` into `kept` and returns the PersonMerge record. keep_candidacy maps an
    election id to the candidacy id to keep where both people are candidates in that election
    (default: kept's own). Raises MergeError if plan_merge() finds a blocker."""
    plan = plan_merge(kept, removed)
    if not plan.can_merge:
        raise MergeError(' '.join(plan.blockers))
    keep_candidacy = keep_candidacy or {}
    rec = _Recorder(f'Merged person #{removed.pk} ({removed.full_name}) into #{kept.pk}')
    person_row = serializers.serialize('python', [removed])

    for conflict in plan.candidacy_conflicts:
        chosen_id = int(keep_candidacy.get(conflict.election.pk, conflict.kept_candidacy.pk))
        if chosen_id not in (conflict.kept_candidacy.pk, conflict.removed_candidacy.pk):
            raise MergeError(f'Candidacy #{chosen_id} is not one of the {conflict.election.year} candidacies.')
        winner, loser = (
            (conflict.kept_candidacy, conflict.removed_candidacy) if chosen_id == conflict.kept_candidacy.pk
            else (conflict.removed_candidacy, conflict.kept_candidacy)
        )
        for result in ElectionResult.objects.filter(candidate=loser):
            rec.move(result, 'candidate', winner)
        for suggestion in Suggestion.objects.filter(candidate=loser):
            rec.move(suggestion, 'candidate', winner)
        rec.delete(loser)

    for candidacy in Candidate.objects.filter(person=removed):
        rec.move(candidacy, 'person', kept)

    duplicate_ids = {
        CommissionerTerm: {t.pk for t in plan.duplicate_terms},
        PersonLink: {l.pk for l in plan.duplicate_links},
        PersonAlias: {a.pk for a in plan.duplicate_aliases},
    }
    for model, dup_ids in duplicate_ids.items():
        for obj in model.objects.filter(person=removed):
            if obj.pk in dup_ids:
                rec.delete(obj)
            else:
                rec.move(obj, 'person', kept)

    for model, field_name in [
        (Suggestion, 'person'), (Suggestion, 'resulting_person'), (WriteInWinner, 'person'),
        (PersonImportRow, 'chosen_person'), (PersonSlugRedirect, 'person'),
    ]:
        for obj in model.objects.filter(**{field_name: removed}):
            rec.move(obj, field_name, kept)

    removed_pk, removed_name, removed_slug = removed.pk, removed.full_name, removed.slug
    removed.delete()
    PersonSlugRedirect.objects.update_or_create(slug=removed_slug, defaults={'person': kept})

    return PersonMerge.objects.create(
        kept_person=kept, removed_person_id=removed_pk, removed_name=removed_name, removed_slug=removed_slug,
        deleted_rows=json.dumps(person_row + rec.deleted, cls=_ExactJSONEncoder),
        moved=rec.moved,
    )


@transaction.atomic
def undo_merge(merge):
    """Restores the removed person and everything the merge deleted, with their original primary
    keys, and moves every repointed foreign key back. Edits made to the kept person since the
    merge stay with the kept person. Returns the restored Person."""
    if merge.undone_at:
        raise MergeError('This merge was already undone.')
    if Person.objects.filter(pk=merge.removed_person_id).exists():
        raise MergeError(f'A person with id #{merge.removed_person_id} already exists.')
    if Person.objects.filter(slug=merge.removed_slug).exists():
        raise MergeError(f'Another person now uses the URL slug "{merge.removed_slug}".')

    reason = f'Undid merge of person #{merge.removed_person_id} ({merge.removed_name})'
    objects = list(serializers.deserialize('json', merge.deleted_rows))
    person_rows = [o for o in objects if isinstance(o.object, Person)]
    other_rows = [o for o in objects if not isinstance(o.object, Person)]

    # Raw saves: restore rows exactly as they were, without Person.save()'s automatic alias.
    for row in person_rows:
        row.save()
    PersonSlugRedirect.objects.filter(slug=merge.removed_slug).delete()

    skipped = 0
    for label, pk, field_name, old_value in reversed(merge.moved):
        model = apps.get_model(label)
        obj = model.objects.filter(pk=pk).first()
        if obj is None:
            skipped += 1  # deleted since the merge; nothing to move back
            continue
        setattr(obj, model._meta.get_field(field_name).attname, old_value)
        obj.save(update_fields=[field_name])
        if hasattr(model, 'history'):
            update_change_reason(obj, reason)

    for row in other_rows:
        row.save()

    merge.undone_at = timezone.now()
    merge.save(update_fields=['undone_at'])
    restored = Person.objects.get(pk=merge.removed_person_id)
    restored.undo_skipped = skipped
    return restored
