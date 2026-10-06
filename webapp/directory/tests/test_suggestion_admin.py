from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from directory.admin import ApprovedNotAppliedFilter, SuggestionAdmin
from directory.forms import SuggestionAdminForm
from directory.models import Suggestion
from directory.tests.factories import make_candidate, make_candidate_status, make_district, make_election, make_person


def base_data(**overrides):
    data = {
        'suggestion_type': Suggestion.TYPE_GENERAL,
        'status': Suggestion.STATUS_PENDING,
        'message': 'test message',
        'ballot_or_write_in': 'ballot',
    }
    data.update(overrides)
    return data


class SuggestionTypeLabelTests(TestCase):
    """Suggestion type labels should read as past-tense events (an already-completed thing),
    except the free-text catch-all, which isn't an event."""

    def test_labels(self):
        labels = dict(Suggestion.TYPE_CHOICES)
        self.assertEqual(labels[Suggestion.TYPE_COMMISSIONER_CHANGE], 'Commissioner resigned')
        self.assertEqual(labels[Suggestion.TYPE_CANDIDATE_WITHDRAWS], 'Candidate withdrew')
        self.assertEqual(labels[Suggestion.TYPE_NEW_CANDIDATE], 'New candidate declared')
        self.assertEqual(labels[Suggestion.TYPE_NEW_COMMISSIONER], 'New commissioner appointed')


class SuggestionAdminFormRequiredFieldTests(TestCase):
    def setUp(self):
        self.district = make_district()

    def test_new_candidate_requires_district_person_name_and_election_year_to_approve(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_NEW_CANDIDATE, status=Suggestion.STATUS_APPROVED,
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('district', form.errors)
        self.assertIn('person_name', form.errors)
        self.assertIn('election_year', form.errors)

    def test_new_candidate_valid_with_all_fields(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_NEW_CANDIDATE, status=Suggestion.STATUS_APPROVED,
            district=self.district.id, person_name='New Person', election_year=2026,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_candidate_withdraws_requires_candidate_to_approve(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_CANDIDATE_WITHDRAWS, status=Suggestion.STATUS_APPROVED,
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('candidate', form.errors)

    def test_candidate_withdraws_valid_with_candidate(self):
        person = make_person()
        election = make_election()
        status = make_candidate_status()
        candidate = make_candidate(person, election, self.district, status=status)
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_CANDIDATE_WITHDRAWS, status=Suggestion.STATUS_APPROVED,
            candidate=candidate.id,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_commissioner_change_requires_district_and_end_date_to_approve(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_COMMISSIONER_CHANGE, status=Suggestion.STATUS_APPROVED,
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('district', form.errors)
        self.assertIn('end_date', form.errors)

    def test_commissioner_change_valid_with_fields(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_COMMISSIONER_CHANGE, status=Suggestion.STATUS_APPROVED,
            district=self.district.id, end_date='2026-10-01',
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_new_commissioner_requires_district_person_name_and_start_date_to_approve(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_NEW_COMMISSIONER, status=Suggestion.STATUS_APPROVED,
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('district', form.errors)
        self.assertIn('person_name', form.errors)
        self.assertIn('start_date', form.errors)

    def test_general_type_has_no_extra_requirements(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_GENERAL, status=Suggestion.STATUS_APPROVED,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_rejecting_a_structured_suggestion_does_not_require_its_fields(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_COMMISSIONER_CHANGE, status=Suggestion.STATUS_REJECTED,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_leaving_a_structured_suggestion_pending_does_not_require_its_fields(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_NEW_COMMISSIONER, status=Suggestion.STATUS_PENDING,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_populates_structured_data_from_typed_fields(self):
        form = SuggestionAdminForm(data=base_data(
            suggestion_type=Suggestion.TYPE_NEW_COMMISSIONER, status=Suggestion.STATUS_APPROVED,
            district=self.district.id, person_name='Fresh Appointee', start_date='2026-10-01',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        suggestion = form.save()
        self.assertEqual(suggestion.structured_data, {
            'district_id': self.district.id, 'person_name': 'Fresh Appointee', 'start_date': '2026-10-01',
        })


class SuggestionAdminConfigTests(TestCase):
    def test_show_facets_always_on(self):
        """So the sidebar's By status filter shows counts (Pending review (3), etc.) without an
        extra click."""
        self.assertEqual(SuggestionAdmin.show_facets, django_admin.ShowFacets.ALWAYS)

    def test_approved_not_applied_filter_registered(self):
        self.assertIn(ApprovedNotAppliedFilter, SuggestionAdmin.list_filter)

    def test_default_ordering_is_newest_submitted_first(self):
        self.assertEqual(SuggestionAdmin.ordering, ['-submitted_at'])


class ApprovedNotAppliedFilterTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def test_filter_shows_only_approved_and_unapplied_suggestions(self):
        approved_unapplied = Suggestion.objects.create(message='a', status=Suggestion.STATUS_APPROVED)
        approved_applied = Suggestion.objects.create(
            message='b', status=Suggestion.STATUS_APPROVED, applied_at=timezone.now(),
        )
        pending = Suggestion.objects.create(message='c', status=Suggestion.STATUS_PENDING)

        response = self.client.get(reverse('admin:directory_suggestion_changelist'), {'approved_not_applied': 'yes'})
        content = response.content.decode()
        self.assertIn(f'/suggestion/{approved_unapplied.pk}/change/', content)
        self.assertNotIn(f'/suggestion/{approved_applied.pk}/change/', content)
        self.assertNotIn(f'/suggestion/{pending.pk}/change/', content)

    def test_facet_count_is_site_wide_even_when_another_filter_is_active(self):
        """Regression test: SimpleListFilter's default facet-count behavior counts against
        whatever OTHER filters are active, so under "By status: Pending review" this facet
        would always show (0) -- pending and approved are mutually exclusive -- no matter how
        many suggestions actually got approved. It should always reflect the true, filter-
        independent count instead, since that's the whole point of a "still need to apply"
        counter."""
        Suggestion.objects.create(message='a', status=Suggestion.STATUS_APPROVED)
        Suggestion.objects.create(message='b', status=Suggestion.STATUS_PENDING)

        response = self.client.get(
            reverse('admin:directory_suggestion_changelist'), {'status__exact': Suggestion.STATUS_PENDING},
        )
        content = response.content.decode()
        self.assertIn('Approved, not yet applied (1)', content)
