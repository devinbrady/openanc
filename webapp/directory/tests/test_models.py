from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from directory.models import ANCOverlap, DistrictOverlap, Person
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import make_anc, make_commissioner_term, make_district, make_person, make_ward


class CommissionerTermTests(TestCase):
    def setUp(self):
        self.district = make_district()
        self.person = make_person()

    def test_end_date_must_be_after_start_date(self):
        term = make_commissioner_term(
            self.person, self.district, start_date=timezone.localdate(), end_date=timezone.localdate()
        )
        with self.assertRaises(ValidationError):
            term.clean()

    def test_term_cannot_exceed_two_years(self):
        today = timezone.localdate()
        term = make_commissioner_term(
            self.person, self.district, start_date=today, end_date=today + timedelta(days=800)
        )
        with self.assertRaises(ValidationError):
            term.clean()

    def test_district_cannot_have_two_current_terms(self):
        make_commissioner_term(self.person, self.district)  # a current term already exists
        other_person = make_person(full_name='Other Commissioner')
        second_term = make_commissioner_term(other_person, self.district)
        with self.assertRaises(ValidationError):
            second_term.clean()

    def test_district_cannot_have_two_future_terms(self):
        today = timezone.localdate()
        make_commissioner_term(
            self.person, self.district, start_date=today + timedelta(days=30), end_date=today + timedelta(days=700)
        )
        other_person = make_person(full_name='Other Commissioner')
        second_future = make_commissioner_term(
            other_person, self.district, start_date=today + timedelta(days=60), end_date=today + timedelta(days=730)
        )
        with self.assertRaises(ValidationError):
            second_future.clean()

    def test_overlapping_terms_for_same_district_are_rejected(self):
        """The general invariant: no two CommissionerTerms for the same district may cover
        overlapping dates, regardless of whether either one is current/future/former."""
        today = timezone.localdate()
        make_commissioner_term(
            self.person, self.district,
            start_date=today - timedelta(days=800), end_date=today - timedelta(days=400),
        )
        other_person = make_person(full_name='Other Commissioner')
        overlapping = make_commissioner_term(
            other_person, self.district,
            start_date=today - timedelta(days=500), end_date=today - timedelta(days=300),
        )
        with self.assertRaises(ValidationError):
            overlapping.clean()

    def test_one_term_fully_containing_another_is_rejected(self):
        today = timezone.localdate()
        make_commissioner_term(
            self.person, self.district, start_date=today - timedelta(days=100), end_date=today + timedelta(days=100),
        )
        other_person = make_person(full_name='Other Commissioner')
        containing = make_commissioner_term(
            other_person, self.district, start_date=today - timedelta(days=200), end_date=today + timedelta(days=200),
        )
        with self.assertRaises(ValidationError):
            containing.clean()

    def test_same_day_handoff_between_terms_is_allowed(self):
        """One term's end_date equalling the next term's start_date is the normal same-day
        transition used throughout the real data (e.g. a resignation and its replacement's
        appointment on the same date) -- that's a boundary touch, not an overlap."""
        today = timezone.localdate()
        make_commissioner_term(self.person, self.district, start_date=today - timedelta(days=100), end_date=today)
        other_person = make_person(full_name='Successor Commissioner')
        successor = make_commissioner_term(
            other_person, self.district, start_date=today, end_date=today + timedelta(days=700),
        )
        successor.clean()  # should not raise

    def test_overlapping_terms_in_different_districts_are_allowed(self):
        today = timezone.localdate()
        make_commissioner_term(self.person, self.district)
        other_district = make_district(designator='1B01', anc=make_anc(designator='1B'), ward=make_ward(number=2))
        other_person = make_person(full_name='Other Commissioner')
        other_term = make_commissioner_term(other_person, other_district)
        other_term.clean()  # should not raise -- same dates, different district

    def test_is_current_is_future_is_former(self):
        today = timezone.localdate()
        current = make_commissioner_term(self.person, self.district)
        self.assertTrue(current.is_current)
        self.assertFalse(current.is_future)
        self.assertFalse(current.is_former)

        former_person = make_person(full_name='Former Commissioner')
        other_district = make_district(designator='1B01', anc=make_anc(designator='1B'), ward=make_ward(number=2))
        former = make_commissioner_term(
            former_person, other_district,
            start_date=today - timedelta(days=800), end_date=today - timedelta(days=400),
        )
        self.assertTrue(former.is_former)
        self.assertFalse(former.is_current)


class PersonSlugTests(TestCase):
    def test_slug_is_generated_from_full_name(self):
        person = make_person(full_name='Jaspal Bhatia')
        self.assertEqual(person.slug, 'jaspal-bhatia')

    def test_duplicate_names_get_distinct_slugs(self):
        first = make_person(full_name='Jaspal Bhatia')
        second = Person.objects.create(full_name='Jaspal Bhatia')
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, 'jaspal-bhatia-2')


class SlashDesignatorTests(PageRenderingTestCase):
    """Regression coverage for the dozen districts spanning two wards, e.g. '6/8F01'."""

    def test_get_absolute_url_round_trips_through_the_designator_converter(self):
        district = make_district(designator='6/8F01', anc=make_anc(designator='6/8F'))
        url = district.get_absolute_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SMD 6/8F01')


class OverlapPercentageTests(TestCase):
    """overlap_percentage is stored as a 0-1 fraction, matching the source CSVs."""

    def test_district_overlap_str_shows_a_percentage_not_a_fraction(self):
        anc = make_anc()
        ward = make_ward()
        d1 = make_district(designator='1A01', anc=anc, ward=ward)
        d2 = make_district(designator='1A12', anc=anc, ward=ward)
        overlap = DistrictOverlap.objects.create(from_district=d1, to_district=d2, overlap_percentage=0.5865)
        self.assertIn('58.7%', str(overlap))
        self.assertNotIn('0.6%', str(overlap))

    def test_anc_overlap_str_shows_a_percentage_not_a_fraction(self):
        a1 = make_anc(designator='1A')
        a2 = make_anc(designator='1B')
        overlap = ANCOverlap.objects.create(from_anc=a1, to_anc=a2, overlap_percentage=0.175)
        self.assertIn('17.5%', str(overlap))
