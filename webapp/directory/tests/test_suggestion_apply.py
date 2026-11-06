import datetime

from django.test import TestCase
from django.utils import timezone

from directory.models import Candidate, CandidateStatus, CommissionerTerm, Person, PersonLink, Suggestion
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

    def test_links_to_existing_person_on_exact_name_match_in_same_district(self):
        existing = make_person(full_name='Already Here')
        make_commissioner_term(existing, self.district)
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Already Here', 'district_id': self.district.id, 'election_year': 2026,
        })

        person, _ = apply_suggestion(suggestion)

        self.assertEqual(person, existing)
        self.assertEqual(Person.objects.filter(full_name='Already Here').count(), 1)

    def test_exact_name_with_no_district_connection_stops_for_a_moderator(self):
        existing = make_person(full_name='Already Here')
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Already Here', 'district_id': self.district.id, 'election_year': 2026,
        })

        with self.assertRaisesMessage(SuggestionApplyError, f'Already Here (#{existing.pk})'):
            apply_suggestion(suggestion)
        self.assertFalse(Candidate.objects.exists())

    def test_close_fuzzy_match_stops_for_a_moderator(self):
        make_person(full_name='Jonathan Q. Smithson')
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Jonathan Smithson', 'district_id': self.district.id, 'election_year': 2026,
        })
        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)

    def test_moderator_chosen_person_is_used_and_spelling_recorded(self):
        existing = make_person(full_name='Already Here')
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Al Here', 'district_id': self.district.id, 'election_year': 2026,
        })
        suggestion.person = existing
        suggestion.save()

        person, _ = apply_suggestion(suggestion)

        self.assertEqual(person, existing)
        self.assertTrue(existing.aliases.filter(name='Al Here', source='suggestion').exists())

    def test_create_new_person_flag_makes_a_namesake(self):
        existing = make_person(full_name='Already Here')
        suggestion = make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {
            'person_name': 'Already Here', 'district_id': self.district.id, 'election_year': 2026,
            'create_new_person': True,
        })

        person, _ = apply_suggestion(suggestion)

        self.assertNotEqual(person, existing)
        self.assertEqual(Person.objects.filter(full_name='Already Here').count(), 2)

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
    def test_general_type_has_no_structured_change_but_can_still_be_marked_applied(self):
        """'general' suggestions are a manual free-text edit -- apply_suggestion makes no
        database change for one, but it still succeeds and sets applied_at, so a moderator has a
        way to clear it from the "Approved, not yet applied" filter once they've made that edit
        by hand."""
        suggestion = make_suggestion(Suggestion.TYPE_GENERAL, {})

        apply_suggestion(suggestion)

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, Suggestion.STATUS_APPROVED)
        self.assertIsNotNone(suggestion.applied_at)

    def test_general_type_carries_through_an_already_set_person_and_district(self):
        person = make_person()
        district = make_district()
        suggestion = Suggestion.objects.create(
            message='test', suggestion_type=Suggestion.TYPE_GENERAL, person=person, district=district,
        )

        apply_suggestion(suggestion)

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.resulting_person, person)
        self.assertEqual(suggestion.resulting_district, district)


class ApplySuggestionLinkTests(TestCase):
    def test_link_is_added_to_the_suggestions_person(self):
        person = make_person()
        suggestion = Suggestion.objects.create(
            message='test', person=person, link='https://news.example.com/resigns',
        )

        apply_suggestion(suggestion)

        link = PersonLink.objects.get(person=person)
        self.assertEqual(link.url, 'https://news.example.com/resigns')
        self.assertTrue(link.publish)
        self.assertEqual(link.history.first().history_change_reason, f'Suggestion #{suggestion.pk}')

    def test_link_goes_to_the_person_a_new_candidate_suggestion_creates(self):
        make_candidate_status(name='Declared Intention to Run')
        district = make_district()
        suggestion = Suggestion.objects.create(
            message='test', suggestion_type=Suggestion.TYPE_NEW_CANDIDATE, link='https://janeforanc.example.com',
            structured_data={'person_name': 'Jane Newcomer', 'district_id': district.id, 'election_year': 2026},
        )

        apply_suggestion(suggestion)

        person = Person.objects.get(full_name='Jane Newcomer')
        self.assertEqual(list(person.links.values_list('url', flat=True)), ['https://janeforanc.example.com'])

    def test_link_the_person_already_has_is_not_duplicated(self):
        person = make_person()
        PersonLink.objects.create(person=person, url='https://example.com/jane')
        suggestion = Suggestion.objects.create(message='test', person=person, link='https://example.com/jane')

        apply_suggestion(suggestion)

        self.assertEqual(PersonLink.objects.filter(person=person).count(), 1)
        suggestion.refresh_from_db()
        self.assertIsNotNone(suggestion.applied_at)

    def test_link_with_no_person_fails_without_marking_applied(self):
        suggestion = Suggestion.objects.create(message='test', link='https://example.com/someone')

        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)

        suggestion.refresh_from_db()
        self.assertIsNone(suggestion.applied_at)
        self.assertFalse(PersonLink.objects.exists())

    def test_no_link_adds_nothing(self):
        suggestion = Suggestion.objects.create(message='test', person=make_person())

        apply_suggestion(suggestion)

        self.assertFalse(PersonLink.objects.exists())


class ApplyNameSpellingTests(TestCase):
    def test_records_alias_without_changing_display_name(self):
        person = make_person(full_name='Erika Núñez')
        suggestion = Suggestion.objects.create(
            name='OANC comparison', message='test', suggestion_type=Suggestion.TYPE_NAME_SPELLING,
            structured_data={'person_name': 'Erika Nunez'}, person=person,
        )

        apply_suggestion(suggestion)

        person.refresh_from_db()
        self.assertEqual(person.full_name, 'Erika Núñez')
        self.assertEqual(person.aliases.get(name='Erika Nunez').source, 'oanc')

    def test_requires_a_person(self):
        suggestion = make_suggestion(Suggestion.TYPE_NAME_SPELLING, {'person_name': 'Erika Nunez'})
        with self.assertRaises(SuggestionApplyError):
            apply_suggestion(suggestion)


class ApplyErrorPathTests(TestCase):
    """Bad or incomplete structured_data, and statuses renamed in the admin, fail cleanly."""

    def setUp(self):
        self.district = make_district()

    def assert_fails(self, suggestion, message):
        with self.assertRaisesMessage(SuggestionApplyError, message):
            apply_suggestion(suggestion)
        suggestion.refresh_from_db()
        self.assertIsNone(suggestion.applied_at)

    def test_missing_required_fields_are_listed(self):
        self.assert_fails(
            make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {'person_name': 'Someone', 'election_year': ''}),
            'structured_data is missing required field(s): district_id, election_year.',
        )

    def test_unknown_district_id(self):
        make_candidate_status(name='Declared Intention to Run')
        self.assert_fails(
            make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {'person_name': 'Someone', 'district_id': 'abc', 'election_year': 2026}),
            "No district with id 'abc'.",
        )

    def test_renamed_declared_status(self):
        self.assert_fails(
            make_suggestion(Suggestion.TYPE_NEW_CANDIDATE, {'person_name': 'Someone', 'district_id': self.district.id, 'election_year': 2026}),
            'CandidateStatus "Declared Intention to Run" not found',
        )
        self.assertFalse(Person.objects.filter(full_name='Someone').exists())

    def test_renamed_withdrew_status(self):
        candidate = make_candidate(make_person(), make_election(), self.district)
        self.assert_fails(
            make_suggestion(Suggestion.TYPE_CANDIDATE_WITHDRAWS, {'candidate_id': candidate.id}),
            'CandidateStatus "Withdrew" not found',
        )

    def test_new_commissioner_with_no_active_terms_anywhere(self):
        self.assert_fails(
            make_suggestion(Suggestion.TYPE_NEW_COMMISSIONER, {'person_name': 'Someone', 'district_id': self.district.id, 'start_date': '2026-10-01'}),
            'No currently-active commissioner terms exist',
        )

    def test_type_without_a_handler(self):
        suggestion = Suggestion(message='x', suggestion_type='retired_type')
        with self.assertRaisesMessage(SuggestionApplyError, 'No automatic handler'):
            apply_suggestion(suggestion)
