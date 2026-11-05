"""Links names from outside sources (DCBOE files, the OANC roster, suggestions, candidate imports)
to Person rows.

Two layers:

  - resolve_person(): an exact lookup on PersonAlias.normalized_name, narrowed by district
    context when more than one person shares the name (or to confirm a single match). Only an
    EXACT result is ever linked automatically.
  - fuzzy_candidates(): rapidfuzz scoring against every alias, for the review UI's ranked list
    of "did you mean" choices. A fuzzy score alone never links anyone -- close matches always go
    to a human.
"""
from dataclasses import dataclass, field

from django.db.models import Q
from rapidfuzz import fuzz, process

from .models import CommissionerTerm, Candidate, DistrictOverlap, Person, PersonAlias, PersonImportRow
from .names import normalize_name, strip_diacritics  # noqa: F401 -- strip_diacritics re-exported

# Below this fuzzy score an import row defaults to "create a new person"; at or above it the row
# is left pending for a human to pick. There's deliberately no auto-link threshold.
NEW_THRESHOLD = 70

EXACT = 'exact'
AMBIGUOUS = 'ambiguous'
UNCONFIRMED = 'unconfirmed'
NONE = 'none'


@dataclass
class Resolution:
    """status is one of:
      EXACT       -- one person has this alias and is confirmed by district context; `person`.
      AMBIGUOUS   -- several people with this alias are equally connected to the district.
      UNCONFIRMED -- people have this alias, but none has a connection to the district (or no
                     district was given), so it could be a namesake.
      NONE        -- no alias matches.
    `people` lists everyone the alias matched, most plausible first."""
    status: str
    person: Person | None = None
    people: list = field(default_factory=list)

    @property
    def is_exact(self):
        return self.status == EXACT


def _people_connected(person_ids, district_q_for_terms, district_q_for_candidacies):
    term_ids = CommissionerTerm.objects.filter(district_q_for_terms, person_id__in=person_ids).values_list('person_id', flat=True)
    candidacy_ids = Candidate.objects.filter(district_q_for_candidacies, person_id__in=person_ids).values_list('person_id', flat=True)
    return set(term_ids) | set(candidacy_ids)


def _context_tiers(person_ids, district, election):
    """Yields sets of person ids connected to `district`, strongest connection first."""
    if election is not None:
        yield set(
            Candidate.objects.filter(person_id__in=person_ids, district=district, election=election)
            .values_list('person_id', flat=True)
        )
    yield _people_connected(person_ids, Q(district=district), Q(district=district))

    overlapping = set(
        DistrictOverlap.objects.filter(from_district=district, overlap_percentage__gt=0).values_list('to_district_id', flat=True)
    ) | set(
        DistrictOverlap.objects.filter(to_district=district, overlap_percentage__gt=0).values_list('from_district_id', flat=True)
    )
    if overlapping:
        yield _people_connected(person_ids, Q(district_id__in=overlapping), Q(district_id__in=overlapping))

    ward_number = district.ward.ward_number
    yield _people_connected(
        person_ids, Q(district__ward__ward_number=ward_number), Q(district__ward__ward_number=ward_number),
    )


def resolve_person(name, district=None, election=None):
    """Looks `name` up by alias. See Resolution for what comes back."""
    key = normalize_name(name)
    if not key:
        return Resolution(NONE)
    person_ids = set(PersonAlias.objects.filter(normalized_name=key).values_list('person_id', flat=True))
    if not person_ids:
        return Resolution(NONE)

    people_by_id = Person.objects.in_bulk(person_ids)
    everyone = sorted(people_by_id.values(), key=lambda p: (p.full_name, p.pk))

    if district is not None:
        for tier in _context_tiers(person_ids, district, election):
            if len(tier) == 1:
                person = people_by_id[next(iter(tier))]
                return Resolution(EXACT, person=person, people=[person] + [p for p in everyone if p != person])
            if len(tier) > 1:
                tied = sorted((people_by_id[i] for i in tier), key=lambda p: (p.full_name, p.pk))
                return Resolution(AMBIGUOUS, people=tied + [p for p in everyone if p not in tied])

    return Resolution(UNCONFIRMED, people=everyone)


def is_alias_of(person, name):
    """True if `name`, exactly as written, is already recorded as one of `person`'s names."""
    return person.aliases.filter(name=name).exists()


def add_alias(person, name, source, note=''):
    """Records `name` as an alias of `person` (a no-op if it already is one). Returns the alias."""
    alias, _ = PersonAlias.objects.get_or_create(
        person=person, name=name, defaults={'source': source, 'note': note},
    )
    return alias


def build_alias_choices():
    """{alias_id: (person_id, normalized_name)} for every alias -- built once per batch."""
    return {
        alias_id: (person_id, normalized)
        for alias_id, person_id, normalized in PersonAlias.objects.values_list('id', 'person_id', 'normalized_name')
    }


def fuzzy_candidates(raw_name, alias_choices, limit=5):
    """Up to `limit` {person_id, full_name, score} dicts, best first, one per person (the best of
    their aliases). Scores compare normalized names, so case and accents don't cost points."""
    key = normalize_name(raw_name)
    if not key or not alias_choices:
        return []
    keys = {alias_id: normalized for alias_id, (_, normalized) in alias_choices.items()}
    results = process.extract(key, keys, scorer=fuzz.WRatio, limit=limit * 4)

    best = {}
    for _, score, alias_id in results:
        person_id = alias_choices[alias_id][0]
        if person_id not in best or score > best[person_id]:
            best[person_id] = score
    ranked = sorted(best.items(), key=lambda item: -item[1])[:limit]
    names = dict(Person.objects.filter(pk__in=[pid for pid, _ in ranked]).values_list('pk', 'full_name'))
    return [{'person_id': pid, 'full_name': names[pid], 'score': round(score, 1)} for pid, score in ranked]


def match_for_import(raw_name, district, election, alias_choices, limit=5):
    """Returns (candidates, decision, chosen_person_id) for one import row. Links automatically
    only on an EXACT alias resolution; alias matches that are ambiguous or unconfirmed are put
    at the top of the list as pending; otherwise it's the fuzzy list, pending or new by score."""
    resolution = resolve_person(raw_name, district=district, election=election)
    fuzzy = fuzzy_candidates(raw_name, alias_choices, limit=limit)

    alias_people = [{'person_id': p.pk, 'full_name': p.full_name, 'score': 100.0} for p in resolution.people]
    alias_ids = {c['person_id'] for c in alias_people}
    candidates = (alias_people + [c for c in fuzzy if c['person_id'] not in alias_ids])[:max(limit, len(alias_people))]

    if resolution.is_exact:
        return candidates, PersonImportRow.DECISION_LINK, resolution.person.pk
    if alias_people:
        return candidates, PersonImportRow.DECISION_PENDING, None
    top_score = candidates[0]['score'] if candidates else 0
    decision = PersonImportRow.DECISION_PENDING if top_score >= NEW_THRESHOLD else PersonImportRow.DECISION_NEW
    return candidates, decision, None


def match_person_rows(batch):
    """Runs matching for every row in an import batch, storing results (and an auto-preselected
    decision) directly on each PersonImportRow."""
    alias_choices = build_alias_choices()
    for row in batch.rows.select_related('district__ward'):
        candidates, decision, chosen_id = match_for_import(row.raw_name, row.district, batch.election, alias_choices)
        row.match_candidates_json = candidates
        row.best_match_score = candidates[0]['score'] if candidates else None
        row.decision = decision
        row.chosen_person_id = chosen_id
        row.save()
