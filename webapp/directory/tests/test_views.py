from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import (
    make_anc,
    make_candidate,
    make_candidate_status,
    make_commissioner_term,
    make_district,
    make_election,
    make_person,
    make_ward,
)


class PageSmokeTests(PageRenderingTestCase):
    """One district/person/etc with a full-ish object graph, then confirm every page in the
    site renders without error. Catches template/context bugs, not visual regressions."""

    def setUp(self):
        self.ward = make_ward()
        self.anc = make_anc()
        self.district = make_district(anc=self.anc, ward=self.ward)
        self.person = make_person()
        make_commissioner_term(self.person, self.district)

        self.election = make_election()
        self.status = make_candidate_status()
        self.candidate = make_candidate(
            make_person(full_name='A Candidate'), self.election, self.district, status=self.status
        )

    def test_home(self):
        response = self.client.get(reverse('directory:home'))
        self.assertEqual(response.status_code, 200)

    def test_district_list(self):
        response = self.client.get(reverse('directory:district_list'))
        self.assertEqual(response.status_code, 200)

    def test_district_detail(self):
        response = self.client.get(self.district.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.person.full_name)

    def test_district_detail_with_no_commissioner(self):
        vacant = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        response = self.client.get(vacant.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No commissioner on record')

    def test_anc_detail(self):
        response = self.client.get(self.anc.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_ward_detail(self):
        response = self.client.get(self.ward.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_person_list(self):
        response = self.client.get(reverse('directory:person_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.person.full_name)

    def test_person_list_excludes_people_with_no_role(self):
        make_person(full_name='Nobody In Particular')
        response = self.client.get(reverse('directory:person_list'))
        self.assertNotContains(response, 'Nobody In Particular')

    def test_person_detail(self):
        response = self.client.get(self.person.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_about(self):
        response = self.client.get(reverse('directory:about'))
        self.assertEqual(response.status_code, 200)

    def test_updates(self):
        response = self.client.get(reverse('directory:updates'))
        self.assertEqual(response.status_code, 200)

    def test_counts(self):
        response = self.client.get(reverse('directory:counts'))
        self.assertEqual(response.status_code, 200)

    def test_contested(self):
        response = self.client.get(reverse('directory:contested'))
        self.assertEqual(response.status_code, 200)

    def test_district_summary_api(self):
        url = reverse(
            'directory:district_summary',
            kwargs={'year': self.district.redistricting_year, 'designator': self.district.designator},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.person.full_name)

    def test_district_summary_api_404s_for_unknown_district(self):
        url = reverse('directory:district_summary', kwargs={'year': 2022, 'designator': 'ZZ99'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class CommissionerHistoryGroupingTests(PageRenderingTestCase):
    """A commissioner's consecutive terms in the same district (no gap between one term's
    end_date and the next term's start_date) should render as a single row; non-consecutive
    stints -- the person left and later came back -- should stay separate rows."""

    def setUp(self):
        self.district = make_district()

    def test_consecutive_terms_are_merged_into_one_row(self):
        person = make_person(full_name='Jaspal Bhatia')
        today = timezone.localdate()
        make_commissioner_term(
            person, self.district, start_date=today - timedelta(days=400), end_date=today - timedelta(days=30)
        )
        make_commissioner_term(
            person, self.district, start_date=today - timedelta(days=30), end_date=today + timedelta(days=400)
        )
        response = self.client.get(self.district.get_absolute_url())
        self.assertContains(response, 'Jaspal Bhatia', count=1)
        self.assertContains(response, 'Current')

    def test_nonconsecutive_stints_stay_as_separate_rows(self):
        person = make_person(full_name='Returning Commissioner')
        today = timezone.localdate()
        # First stint, then someone else served, then this person returns -- a real gap.
        make_commissioner_term(
            person, self.district, start_date=today - timedelta(days=1000), end_date=today - timedelta(days=800)
        )
        other_person = make_person(full_name='In Between Commissioner')
        make_commissioner_term(
            other_person, self.district, start_date=today - timedelta(days=800), end_date=today - timedelta(days=400)
        )
        make_commissioner_term(
            person, self.district, start_date=today - timedelta(days=400), end_date=today - timedelta(days=30)
        )
        response = self.client.get(self.district.get_absolute_url())
        self.assertContains(response, 'Returning Commissioner', count=2)


class PersonDistrictHistoryGroupingTests(PageRenderingTestCase):
    """The person page groups a person's own terms by district the same way the district
    page groups terms by person: consecutive terms in the same district merge into one row."""

    def setUp(self):
        self.person = make_person(full_name='Jaspal Bhatia')

    def test_consecutive_terms_in_the_same_district_are_merged(self):
        district = make_district()
        today = timezone.localdate()
        make_commissioner_term(
            self.person, district, start_date=today - timedelta(days=400), end_date=today - timedelta(days=30)
        )
        make_commissioner_term(
            self.person, district, start_date=today - timedelta(days=30), end_date=today + timedelta(days=400)
        )
        response = self.client.get(self.person.get_absolute_url())
        self.assertContains(response, f'SMD {district.designator}', count=1)

    def test_terms_in_different_districts_stay_separate(self):
        ward = make_ward()
        district1 = make_district(designator='1A01', anc=make_anc(designator='1A'), ward=ward)
        district2 = make_district(designator='1B01', anc=make_anc(designator='1B'), ward=ward)
        today = timezone.localdate()
        make_commissioner_term(
            self.person, district1, start_date=today - timedelta(days=800), end_date=today - timedelta(days=400)
        )
        make_commissioner_term(
            self.person, district2, start_date=today - timedelta(days=400), end_date=today - timedelta(days=30)
        )
        response = self.client.get(self.person.get_absolute_url())
        self.assertContains(response, 'SMD 1A01', count=1)
        self.assertContains(response, 'SMD 1B01', count=1)
