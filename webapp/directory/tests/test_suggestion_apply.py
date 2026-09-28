import datetime

from django.test import TestCase
from django.utils import timezone

from directory.models import Candidate, CandidateStatus, CommissionerTerm, Person, Suggestion
from directory.suggestion_apply import SuggestionApplyError, apply_suggestion
from directory.tests.factories import (
    make_candidate,
    make_candidate_status,
    make_commissioner_term,
    make_district,
    make_election,
    make_person,
)


def make_suggestion(suggestion_type, structured_data):
    return Suggestion.objects.create(
        message='test', suggestion_type=suggestion_type, structured_data=structured_data,
    )


class ApplyNewCandidateTests(TestCase):
    def setUp(self):
        make_candidate_status(name='Declared Intention to Run')
        make_candidate_status(name='Write-In Candidate')
        self.district = make_district()
        self.election = make_election(year=2026)

    def test_happy_path_creates_person_and_candidate(self):
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Brand New Candidate',
            'district_id': self.district.id,
            'election_year': 2026,
        })

        person, district = apply_suggestion(suggestion)

        self.assertEqual(person.full_name, 'Brand New Candidate')
        self.assertEqual(district, self.district)
        candidate = Candidate.objects.get(person=person, election=self.election)
        self.assertEqual(candidate.status.name, 'Declared Intention to Run')
        self.assertEqual(candidate.source, 'suggestion')

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, Suggestion.STATUS_APPROVED)
        self.assertIsNotNone(suggestion.applied_at)
        self.assertEqual(suggestion.resulting_person, person)

    def test_write_in_track_uses_write_in_status(self):
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Write In Person',
            'district_id': self.district.id,
            'election_year': 2026,
            'ballot_or_write_in': 'write_in',
        })

        apply_suggestion(suggestion)

        candidate = Candidate.objects.get(person__full_name='Write In Person')
        self.assertEqual(candidate.status.name, 'Write-In Candidate')

    def test_links_to_existing_person_on_exact_name_match(self):
        existing = make_person(full_name='Already Here')
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Already Here', 'district_id': self.district.id, 'election_year': 2026,
        })

        person, _ = apply_suggestion(suggestion)

        self.assertEqual(person, existing)
        self.assertEqual(Person.objects.filter(full_name='Already Here').count(), 1)

    def test_duplicate_candidate_fails_without_partial_apply(self):
        person = make_person(full_name='Already A Candidate')
        make_candidate(person, self.election, self.district, status=CandidateStatus.objects.get(name='Declared Intention to Run'))
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Already A Candidate', 'district_id': self.district.id, 'election_year': 2026,
        })

        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, Suggestion.STATUS_PENDING)
        self.assertIsNone(suggestion.applied_at)
        self.assertEqual(Candidate.objects.filter(person=person).count(), 1)


class ApplyCandidateWithdrawsTests(TestCase):
    def setUp(self):
        make_candidate_status(name='Withdrew')
        self.status = make_candidate_status(name='On the Ballot')
        self.district = make_district()
        self.election = make_election(year=2026)
        self.person = make_person()
        self.candidate = make_candidate(self.person, self.election, self.district, status=self.status)

    def test_happy_path_sets_withdrew_status(self):
        suggestion = make_suggestion(Suggestion.TYPE_CANDIDATE_WITHDRAWS, {'candidate_id': self.candidate.id})

        apply_suggestion(suggestion)

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status.name, 'Withdrew')

    def test_unknown_candidate_id_fails(self):
        suggestion = make_suggestion(Suggestion.TYPE_CANDIDATE_WITHDRAWS, {'candidate_id': 999999})

        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, self.status)


class ApplyCommissionerChangeTests(TestCase):
    def setUp(self):
        self.district = make_district()
        self.person = make_person()
        today = timezone.localdate()
        self.term = make_commissioner_term(
            self.person, self.district,
            start_date=today - datetime.timedelta(days=100), end_date=today + datetime.timedelta(days=500),
        )

    def test_happy_path_ends_current_term(self):
        today = timezone.localdate()
        suggestion = make_suggestion(Suggestion.TYPE_COMMISSIONER_CHANGE, {
            'district_id': self.district.id, 'end_date': today.isoformat(), 'reason': 'resigned',
        })

        apply_suggestion(suggestion)

        self.term.refresh_from_db()
        self.assertEqual(self.term.end_date, today)

    def test_district_with_no_current_term_fails(self):
        empty_district = make_district(designator='1A02', anc=self.district.anc, ward=self.district.ward)
        suggestion = make_suggestion(Suggestion.TYPE_COMMISSIONER_CHANGE, {
            'district_id': empty_district.id, 'end_date': timezone.localdate().isoformat(),
        })

        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)


class ApplyNewCommissionerTests(TestCase):
    def setUp(self):
        self.district = make_district()
        self.today = timezone.localdate()
        # An existing current term elsewhere establishes the "shared end date" the new term
        # should be given.
        self.shared_end_date = self.today + datetime.timedelta(days=400)
        other_district = make_district(designator='1A02', anc=self.district.anc, ward=self.district.ward)
        make_commissioner_term(
            make_person(full_name='Sitting Commissioner'), other_district,
            start_date=self.today - datetime.timedelta(days=300), end_date=self.shared_end_date,
        )

    def test_happy_path_creates_term_with_shared_end_date(self):
        suggestion = make_suggestion(Suggestion.TYPE_NEW_COMMISSIONER, {
            'district_id': self.district.id, 'person_name': 'New Commissioner', 'start_date': self.today.isoformat(),
        })

        person, district = apply_suggestion(suggestion)

        term = CommissionerTerm.objects.get(district=self.district)
        self.assertEqual(term.person.full_name, 'New Commissioner')
        self.assertEqual(term.start_date, self.today)
        self.assertEqual(term.end_date, self.shared_end_date)

    def test_district_already_has_current_term_fails(self):
        make_commissioner_term(
            make_person(full_name='Already Serving'), self.district,
            start_date=self.today - datetime.timedelta(days=10), end_date=self.shared_end_date,
        )
        suggestion = make_suggestion(Suggestion.TYPE_NEW_COMMISSIONER, {
            'district_id': self.district.id, 'person_name': 'Conflicting Appointee', 'start_date': self.today.isoformat(),
        })

        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)

        self.assertFalse(CommissionerTerm.objects.filter(person__full_name='Conflicting Appointee').exists())


class ApplySuggestionGeneralTypeTests(TestCase):
    def test_general_type_has_no_automatic_handler(self):
        suggestion = make_suggestion(Suggestion.TYPE_GENERAL, {})
        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, Suggestion.STATUS_PENDING)
