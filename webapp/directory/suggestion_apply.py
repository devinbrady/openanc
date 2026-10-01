"""Applies a reviewed, structured Suggestion directly to the database -- one handler function
per Suggestion.suggestion_type, dispatched from SuggestionAdmin's "Apply selected suggestions"
action (admin.py). Reuses directory/matching.py's Person matching for any person-name field.

'general' suggestions stay a manual free-text edit -- apply_general below makes no database
change itself, since there's nothing structured to read. It exists so a moderator has a way to
mark one as handled once they've made that edit by hand elsewhere; without it, an approved
'general' suggestion would sit in the "Approved, not yet applied" admin filter forever, since
nothing could ever set applied_at.

Each handler expects Suggestion.structured_data to hold the fields documented on it below, reads
them, makes the change, and returns (person, district) for the caller to record on the
suggestion. Raises SuggestionApplyError (with a message suitable for showing a moderator) if the
data is missing/invalid or the change conflicts with existing data -- callers should run the
whole apply inside transaction.atomic() so nothing is partially applied.
"""
import datetime
from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from simple_history.utils import update_change_reason

from .matching import build_person_choices, match_name
from .models import Candidate, CandidateStatus, CommissionerTerm, District, Election, Person, PersonImportRow, Suggestion


class SuggestionApplyError(Exception):
    """The suggestion couldn't be applied as-is. str(exception) is shown to the moderator."""


def _get_or_link_person(person_name):
    """Auto-links to a high-confidence existing Person match (same matching used by the
    candidate-import tool); otherwise creates a new Person."""
    choices = build_person_choices()
    candidates, decision = match_name(person_name, choices)
    if decision == PersonImportRow.DECISION_LINK and candidates:
        return Person.objects.get(pk=candidates[0]['person_id'])
    return Person.objects.create(full_name=person_name)


def _get_district(district_id):
    try:
        return District.objects.get(pk=district_id)
    except (District.DoesNotExist, ValueError, TypeError):
        raise SuggestionApplyError(f'No district with id {district_id!r}.')


def _get_required(data, *keys):
    missing = [key for key in keys if key not in data or data[key] in (None, '')]
    if missing:
        raise SuggestionApplyError(f'structured_data is missing required field(s): {", ".join(missing)}.')
    return [data[key] for key in keys]


def _as_date(value):
    return datetime.date.fromisoformat(value) if isinstance(value, str) else value


def _run_full_clean(instance):
    try:
        instance.full_clean()
    except ValidationError as e:
        raise SuggestionApplyError('; '.join(e.messages))


def apply_new_candidate(suggestion):
    """structured_data: {person_name, district_id, election_year, ballot_or_write_in
    ('ballot' or 'write_in', defaults to 'ballot')}."""
    person_name, district_id, election_year = _get_required(
        suggestion.structured_data, 'person_name', 'district_id', 'election_year',
    )
    ballot_or_write_in = suggestion.structured_data.get('ballot_or_write_in', 'ballot')

    district = _get_district(district_id)
    election, _ = Election.objects.get_or_create(year=election_year)
    status_name = 'Write-In Candidate' if ballot_or_write_in == 'write_in' else 'Declared Intention to Run'
    status = CandidateStatus.objects.filter(name=status_name).first()
    if not status:
        raise SuggestionApplyError(f'CandidateStatus "{status_name}" not found -- was it renamed in the admin?')

    person = _get_or_link_person(person_name)
    candidate, created = Candidate.objects.get_or_create(
        person=person, election=election,
        defaults={'district': district, 'status': status, 'source': 'suggestion'},
    )
    if not created:
        raise SuggestionApplyError(f'{person} is already a candidate in the {election.year} election.')

    update_change_reason(candidate, f'Suggestion #{suggestion.pk}')
    return person, district


def apply_candidate_withdraws(suggestion):
    """structured_data: {candidate_id}."""
    (candidate_id,) = _get_required(suggestion.structured_data, 'candidate_id')
    try:
        candidate = Candidate.objects.select_related('person', 'district').get(pk=candidate_id)
    except (Candidate.DoesNotExist, ValueError, TypeError):
        raise SuggestionApplyError(f'No candidate with id {candidate_id!r}.')

    status = CandidateStatus.objects.filter(name='Withdrew').first()
    if not status:
        raise SuggestionApplyError('CandidateStatus "Withdrew" not found -- was it renamed in the admin?')

    candidate.status = status
    candidate.save()
    update_change_reason(candidate, f'Suggestion #{suggestion.pk}')
    return candidate.person, candidate.district


def apply_commissioner_change(suggestion):
    """A commissioner stops serving early (resigns, dies) -- ends their current term.
    structured_data: {district_id, end_date (ISO date), reason (optional, freeform)}."""
    district_id, end_date = _get_required(suggestion.structured_data, 'district_id', 'end_date')

    district = _get_district(district_id)
    today = timezone.localdate()
    term = CommissionerTerm.objects.filter(district=district, start_date__lte=today, end_date__gte=today).first()
    if not term:
        raise SuggestionApplyError(f'{district} has no current commissioner term to end.')

    term.end_date = _as_date(end_date)
    _run_full_clean(term)
    term.save()

    reason = suggestion.structured_data.get('reason', '')
    update_change_reason(term, f'Suggestion #{suggestion.pk}: {reason}'.rstrip(': '))
    return term.person, district


def apply_new_commissioner(suggestion):
    """structured_data: {district_id, person_name, start_date (ISO date)}. end_date is inferred
    as the mode of currently-active commissioner terms' end_date (i.e. whatever date the rest of
    that term-cycle's commissioners share)."""
    district_id, person_name, start_date = _get_required(
        suggestion.structured_data, 'district_id', 'person_name', 'start_date',
    )

    district = _get_district(district_id)
    today = timezone.localdate()
    current_end_dates = list(
        CommissionerTerm.objects.filter(start_date__lte=today, end_date__gte=today).values_list('end_date', flat=True)
    )
    if not current_end_dates:
        raise SuggestionApplyError('No currently-active commissioner terms exist to infer a term end date from.')
    end_date = Counter(current_end_dates).most_common(1)[0][0]

    person = _get_or_link_person(person_name)
    term = CommissionerTerm(person=person, district=district, start_date=_as_date(start_date), end_date=end_date)
    _run_full_clean(term)
    term.save()
    update_change_reason(term, f'Suggestion #{suggestion.pk}')
    return person, district


def apply_general(suggestion):
    """No structured change to make -- the moderator edits the data by hand, outside this flow.
    Running "Apply" just records that it's been handled (and, when the suggestion already names
    a person/district, carries those through to resulting_person/resulting_district for display)."""
    return suggestion.person, suggestion.district


HANDLERS = {
    Suggestion.TYPE_GENERAL: apply_general,
    Suggestion.TYPE_NEW_CANDIDATE: apply_new_candidate,
    Suggestion.TYPE_CANDIDATE_WITHDRAWS: apply_candidate_withdraws,
    Suggestion.TYPE_COMMISSIONER_CHANGE: apply_commissioner_change,
    Suggestion.TYPE_NEW_COMMISSIONER: apply_new_commissioner,
}


def apply_suggestion(suggestion):
    """Applies a structured suggestion to the database inside its own transaction -- nothing is
    partially applied on failure. Raises SuggestionApplyError if the handler runs into a
    problem (a 'general' suggestion's handler never raises -- see apply_general above)."""
    handler = HANDLERS.get(suggestion.suggestion_type)
    if handler is None:
        raise SuggestionApplyError(
            f'No automatic handler for suggestion type "{suggestion.get_suggestion_type_display()}" -- apply by hand.'
        )

    with transaction.atomic():
        person, district = handler(suggestion)
        suggestion.resulting_person = person
        suggestion.resulting_district = district
        suggestion.applied_at = timezone.now()
        suggestion.status = Suggestion.STATUS_APPROVED
        suggestion.save()
    return person, district
