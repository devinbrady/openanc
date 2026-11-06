from datetime import date, timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from directory.models import ANCOverlap, DistrictOverlap, ElectionResult, WriteInWinner
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

    def test_district_list_defaults_to_current_commissioners_view(self):
        response = self.client.get(reverse('directory:district_list'))
        content = response.content.decode()
        self.assertIn('view-tab active">Current Commissioners', content)
        self.assertContains(response, self.person.full_name)

    def test_district_list_by_ward_view(self):
        response = self.client.get(reverse('directory:district_list'), {'view': 'by_ward'})
        content = response.content.decode()
        self.assertIn('view-tab active">By Ward', content)
        self.assertContains(response, self.ward.name)

    def test_district_list_current_commissioners_shows_vacant_seat(self):
        vacant = make_district(designator='1A99', anc=self.anc, ward=self.ward)
        response = self.client.get(reverse('directory:district_list'))
        content = response.content.decode()
        self.assertIn(vacant.designator, content)
        self.assertIn('Vacant', content)

    def test_district_list_shows_current_election_candidates_on_the_ballot(self):
        # setUp already created a current-year election, an 'On the Ballot' status, and a
        # candidate ('A Candidate') in self.district.
        year = settings.CURRENT_ELECTION_YEAR
        election = self.election
        counted = self.status
        withdrew = make_candidate_status(name='Withdrew', publish_candidate=True, count_as_candidate=False)
        hidden = make_candidate_status(name='Hide Record', publish_candidate=False, count_as_candidate=False)
        make_candidate(make_person(full_name='Ballot Person'), election, self.district, status=counted)
        make_candidate(make_person(full_name='Withdrawn Person'), election, self.district, status=withdrew)
        make_candidate(make_person(full_name='Hidden Person'), election, self.district, status=hidden)
        old_election = make_election(year=year - 2)
        make_candidate(make_person(full_name='Old Election Person'), old_election, self.district, status=counted)

        response = self.client.get(reverse('directory:district_list'))

        self.assertContains(response, '<th>On the Ballot</th>')
        self.assertContains(response, 'A Candidate')
        self.assertContains(response, 'Ballot Person')
        self.assertNotContains(response, 'Withdrawn Person')
        self.assertNotContains(response, 'Hidden Person')
        self.assertNotContains(response, 'Old Election Person')

    def test_district_list_has_a_column_per_candidate_status_and_candidates_move_with_their_status(self):
        write_in = make_candidate_status(name='Write-In Candidate', display_order=5)
        write_in_candidate = make_candidate(
            make_person(full_name='Write In Person'), self.election, self.district, status=write_in,
        )
        # A second ANC with no write-ins must still get the same columns, so tables line up.
        other_district = make_district(designator='2B01', anc=make_anc(designator='2B'), ward=self.ward)

        response = self.client.get(reverse('directory:district_list'))
        content = response.content.decode()
        self.assertEqual(content.count('<th>Write-In Candidate</th>'), 2)
        self.assertEqual(content.count('<th>On the Ballot</th>'), 2)
        self.assertLess(content.index('<th>On the Ballot</th>'), content.index('<th>Write-In Candidate</th>'))

        districts_by_designator = {
            d.designator: d for anc in response.context['ancs'] for d in anc.districts.all()
        }
        on_ballot_cell, write_in_cell = districts_by_designator[self.district.designator].ballot_columns
        self.assertEqual([c.person.full_name for c in on_ballot_cell], ['A Candidate'])
        self.assertEqual([c.person.full_name for c in write_in_cell], ['Write In Person'])
        self.assertEqual(districts_by_designator[other_district.designator].ballot_columns, [[], []])

        # Change the write-in's status: they move to the matching column, and the now-empty
        # Write-In Candidate column disappears.
        write_in_candidate.status = self.status
        write_in_candidate.save()
        response = self.client.get(reverse('directory:district_list'))
        self.assertNotContains(response, 'Write-In Candidate')
        (on_ballot_cell,) = next(
            d for anc in response.context['ancs'] for d in anc.districts.all() if d.id == self.district.id
        ).ballot_columns
        self.assertEqual({c.person.full_name for c in on_ballot_cell}, {'A Candidate', 'Write In Person'})

    def test_ward_and_anc_detail_show_candidate_columns_by_status(self):
        write_in = make_candidate_status(name='Write-In Candidate', display_order=5)
        make_candidate(make_person(full_name='Write In Person'), self.election, self.district, status=write_in)

        for url in (self.ward.get_absolute_url(), self.anc.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                content = response.content.decode()
                self.assertContains(response, '<th>On the Ballot</th>')
                self.assertContains(response, '<th>Write-In Candidate</th>')
                self.assertLess(content.index('<th>On the Ballot</th>'), content.index('<th>Write-In Candidate</th>'))
                self.assertContains(response, 'A Candidate')
                self.assertContains(response, 'Write In Person')

    def _result(self, district, votes, ranking, candidate=None, **kwargs):
        return ElectionResult.objects.create(
            election=self.election, district=district, candidate=candidate,
            candidate_name_raw='' if candidate else 'Write-in', votes=votes, ranking=ranking, **kwargs,
        )

    def test_district_tables_bold_the_leading_candidate(self):
        trailing = make_candidate(make_person(full_name='Trailing Person'), self.election, self.district, status=self.status)
        self._result(self.district, 100, 1, candidate=self.candidate)
        self._result(self.district, 50, 2, candidate=trailing)
        self._result(self.district, 5, 3)

        for url in (reverse('directory:district_list'), self.ward.get_absolute_url(), self.anc.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'<strong><a href="{self.candidate.person.get_absolute_url()}">A Candidate</a></strong>')
                self.assertNotContains(response, '<strong><a href="' + trailing.person.get_absolute_url())
                self.assertNotContains(response, 'Write-in leads')
                self.assertContains(response, 'Candidates in <strong>bold</strong> are leading in the unofficial 2026 vote count.')

    def test_vote_leader_note_shows_results_date_and_switches_after_certification(self):
        self._result(self.district, 100, 1, candidate=self.candidate)
        self.election.results_as_of = date(2026, 11, 5)
        self.election.save()
        response = self.client.get(reverse('directory:district_list'))
        self.assertContains(response, 'leading in the unofficial 2026 vote count as of November 5, 2026.')

        self.election.results_status = 'certified'
        self.election.save()
        ElectionResult.objects.update(is_winner=True)
        response = self.client.get(reverse('directory:district_list'))
        self.assertContains(response, 'Candidates in <strong>bold</strong> won the 2026 election.')

    def test_vote_leader_note_hidden_without_results(self):
        for url in (reverse('directory:district_list'), self.ward.get_absolute_url(), self.anc.get_absolute_url()):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), 'in <strong>bold</strong>')

    def test_district_tables_say_write_in_leads_in_the_write_in_column(self):
        write_in = make_candidate_status(name='Write-In Candidate', display_order=5)
        write_in_candidate = make_candidate(make_person(full_name='Write In Person'), self.election, self.district, status=write_in)
        self._result(self.district, 80, 1)
        self._result(self.district, 20, 2, candidate=self.candidate)

        response = self.client.get(reverse('directory:district_list'))
        self.assertContains(response, '<strong>Write-in leads, name unknown</strong>', count=1)
        self.assertNotContains(response, '<strong><a href=')
        district = next(d for anc in response.context['ancs'] for d in anc.districts.all() if d.id == self.district.id)
        self.assertEqual(district.write_in_leads_column, 1)

        # Once certified, the named write-in winner is bolded instead.
        self.election.results_status = 'certified'
        self.election.save()
        ElectionResult.objects.filter(ranking=1).update(is_winner=True, is_write_in_winner=True)
        WriteInWinner.objects.create(election=self.election, district=self.district, person=write_in_candidate.person)
        response = self.client.get(reverse('directory:district_list'))
        self.assertNotContains(response, 'Write-in leads')
        self.assertContains(response, f'<strong><a href="{write_in_candidate.person.get_absolute_url()}">Write In Person</a></strong>')

    def test_district_tables_put_write_in_leads_in_last_column_without_write_in_candidates(self):
        self._result(self.district, 30, 1)
        self._result(self.district, 10, 2, candidate=self.candidate)
        response = self.client.get(reverse('directory:district_list'))
        self.assertContains(response, '<br><strong>Write-in leads, name unknown</strong>', count=1)

    def test_ward_and_anc_detail_omit_candidate_columns_when_no_one_is_on_the_ballot(self):
        self.candidate.delete()
        for url in (self.ward.get_absolute_url(), self.anc.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, '<th>On the Ballot</th>')

    def test_redistricting_cycle_is_in_the_overlap_section_not_at_the_top_of_the_page(self):
        ward_2012 = make_ward(year=2012)
        anc_2012 = make_anc(designator='1A', year=2012)
        district_2012 = make_district(designator='1A01', year=2012, anc=anc_2012, ward=ward_2012)
        DistrictOverlap.objects.create(from_district=self.district, to_district=district_2012, overlap_percentage=0.9)
        ANCOverlap.objects.create(from_anc=self.anc, to_anc=anc_2012, overlap_percentage=0.9)

        for url, noun in ((self.district.get_absolute_url(), 'district'), (self.anc.get_absolute_url(), 'ANC')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, '2022 redistricting cycle</p>')
                self.assertContains(
                    response,
                    f"This {noun} is from the 2022 redistricting cycle. This {noun}'s territory overlaps",
                )

        response = self.client.get(self.ward.get_absolute_url())
        self.assertNotContains(response, 'redistricting cycle')

    def test_district_detail(self):
        response = self.client.get(self.district.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.person.full_name)

    def test_district_detail_shows_last_edited_date(self):
        """The commissioner term and candidate created in setUp both leave audit-trail history,
        so the page should show a "Last edited" date reflecting the most recent of them."""
        response = self.client.get(self.district.get_absolute_url())
        self.assertContains(response, 'Last edited')
        # The page localizes history_date to TIME_ZONE via the |date filter -- compare against
        # the same local time, not raw timezone.now() (UTC), which disagrees for part of the day.
        self.assertContains(response, timezone.localtime(timezone.now()).strftime('%B %-d, %Y'))

    def test_district_detail_shows_neighbor_current_commissioner(self):
        neighbor = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        neighbor_person = make_person(full_name='Neighboring Person')
        make_commissioner_term(neighbor_person, neighbor)
        self.district.neighbors.add(neighbor)

        response = self.client.get(self.district.get_absolute_url())
        self.assertContains(response, '>SMD 1A02</a>: Neighboring Person')

    def test_district_detail_omits_commissioner_for_vacant_neighbor(self):
        neighbor = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        self.district.neighbors.add(neighbor)

        response = self.client.get(self.district.get_absolute_url())
        self.assertContains(response, '>SMD 1A02</a>')
        self.assertNotContains(response, '>SMD 1A02</a>:')

    def test_district_detail_with_no_commissioner(self):
        vacant = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        response = self.client.get(vacant.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No commissioner on record')

    def test_district_detail_with_no_history_omits_last_edited(self):
        vacant = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        response = self.client.get(vacant.get_absolute_url())
        self.assertNotContains(response, 'Last edited')

    def test_district_detail_same_day_handoff_shows_only_the_incoming_commissioner_as_current(self):
        """self.district's term from setUp becomes the incoming term (starts today); a second
        term for a different person ends today. Only the incoming commissioner should be
        labeled Current, not both."""
        today = timezone.localdate()
        incoming_term = self.district.commissioner_terms.get(person=self.person)
        incoming_term.start_date = today
        incoming_term.save()

        outgoing_person = make_person(full_name='Outgoing Commissioner')
        make_commissioner_term(outgoing_person, self.district, start_date=today - timedelta(days=400), end_date=today)

        response = self.client.get(self.district.get_absolute_url())
        content = response.content.decode()
        self.assertEqual(content.count('term-current'), 1)
        self.assertContains(response, self.person.full_name)
        self.assertContains(response, 'Outgoing Commissioner')

    def test_anc_detail(self):
        response = self.client.get(self.anc.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_anc_detail_lists_only_published_links(self):
        self.anc.links.create(url='https://www.anc1a.org/', publish=True)
        self.anc.links.create(url='https://twitter.com/ANC1A', publish=False)
        response = self.client.get(self.anc.get_absolute_url())
        self.assertContains(response, '<a href="https://www.anc1a.org/">anc1a.org</a>', html=True)
        self.assertNotContains(response, 'twitter.com/ANC1A')

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

    def test_person_list_filter_key_is_accent_stripped(self):
        """The client-side name filter matches against each <li>'s data-name attribute; it needs
        to be plain ASCII so typing "Lopez" (no accent) still finds "López" (see the
        strip_diacritics template filter and the matching JS-side normalization)."""
        person = make_person(full_name='Mónica Martínez López')
        make_commissioner_term(person, self.district)
        response = self.client.get(reverse('directory:person_list'))
        self.assertContains(response, 'data-name="monica martinez lopez"')

    def test_person_list_filter_key_includes_aliases_but_page_does_not_show_them(self):
        person = make_person(full_name='Zachary Adams')
        person.aliases.create(name='Zach "Z" Adams', source='dcboe_ballot')
        make_commissioner_term(person, self.district)
        response = self.client.get(reverse('directory:person_list'))
        self.assertContains(response, 'data-name="zachary adams | zach z adams"')
        self.assertNotContains(response, 'Zach &quot;Z&quot;')
        self.assertNotContains(response, 'Zach "Z"')

    def test_person_detail(self):
        response = self.client.get(self.person.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_person_detail_lists_only_published_links(self):
        self.person.links.create(url='https://www.janesmith.org/', publish=True)
        self.person.links.create(url='https://x.com/janesmith', publish=False)
        response = self.client.get(self.person.get_absolute_url())
        self.assertContains(response, '<a href="https://www.janesmith.org/">janesmith.org</a>', html=True)
        self.assertNotContains(response, 'x.com/janesmith')

    def test_person_detail_orders_links_by_position(self):
        self.person.links.create(url='https://first-added.example/', position=2)
        self.person.links.create(url='https://second-added.example/', position=1)
        response = self.client.get(self.person.get_absolute_url())
        content = response.content.decode()
        self.assertLess(content.index('second-added.example'), content.index('first-added.example'))

    def test_about(self):
        response = self.client.get(reverse('directory:about'))
        self.assertEqual(response.status_code, 200)

    def test_updates(self):
        response = self.client.get(reverse('directory:updates'))
        self.assertEqual(response.status_code, 200)

    def test_counts(self):
        response = self.client.get(reverse('directory:counts'))
        self.assertEqual(response.status_code, 200)

    def test_counts_status_table_splits_active_and_inactive_totals(self):
        """Active = Count as Candidate checked. self.status (from setUp) counts and already has
        one candidate; only the current election is included."""
        withdrew = make_candidate_status(name='Withdrew', publish_candidate=True, count_as_candidate=False)
        make_candidate(make_person(full_name='Second'), self.election, self.district, status=self.status)
        make_candidate(make_person(full_name='Withdrawn'), self.election, self.district, status=withdrew)
        make_candidate(make_person(full_name='Past'), make_election(year=2024), self.district, status=self.status)

        response = self.client.get(reverse('directory:counts'))

        self.assertEqual(response.context['status_totals'], {'active': 2, 'inactive': 1})
        self.assertContains(response, '<th>Total</th>', html=False)

    def test_counts_vacancy_count_is_not_thrown_off_by_a_same_day_handoff(self):
        """Regression test: a same-day handoff (one term ending today, the next starting today)
        briefly leaves two terms matching "current" for the same district. The vacancy count
        used to count terms rather than distinct districts, so every such handoff inflated
        "filled" by one extra -- enough of them and "total - filled" went negative."""
        today = timezone.localdate()
        incoming_term = self.district.commissioner_terms.get(person=self.person)
        incoming_term.start_date = today
        incoming_term.save()

        make_commissioner_term(
            make_person(full_name='Outgoing Commissioner'), self.district,
            start_date=today - timedelta(days=400), end_date=today,
        )
        # self.district now has two terms matching "current" (the same-day handoff above), and
        # is the only district in this test's data, so it should count as exactly one filled
        # district -- zero vacancies, never negative.

        response = self.client.get(reverse('directory:counts'))
        self.assertContains(response, '1 districts, 0 currently vacant.')

    def test_contested_filters_districts_by_live_candidate_count(self):
        """self.district has one candidate from setUp. Withdrawn candidates (Count as Candidate
        unchecked) don't count, and only the current election is considered."""
        withdrew = make_candidate_status(name='Withdrew', publish_candidate=True, count_as_candidate=False)
        two = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        make_candidate(make_person(full_name='Two A'), self.election, two, status=self.status)
        make_candidate(make_person(full_name='Two B'), self.election, two, status=self.status)
        none_counted = make_district(designator='1A03', anc=self.anc, ward=self.ward)
        make_candidate(make_person(full_name='Withdrawn'), self.election, none_counted, status=withdrew)
        make_candidate(make_person(full_name='Past'), make_election(year=2024), none_counted, status=self.status)
        empty = make_district(designator='1A04', anc=self.anc, ward=self.ward)

        response = self.client.get(reverse('directory:contested'))

        buckets = response.context['designators_by_bucket']
        self.assertEqual(buckets['no_candidates'], ['1A03', '1A04'])
        self.assertEqual(buckets['one_candidate'], [self.district.designator])
        self.assertEqual(buckets['two_plus_candidates'], ['1A02'])
        self.assertContains(response, 'Filter districts by:')
        self.assertNotContains(response, 'Color districts by:')

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
        self.assertNotContains(response, 'in <strong>bold</strong>')

    def _summary(self, district):
        return self.client.get(reverse(
            'directory:district_summary',
            kwargs={'year': district.redistricting_year, 'designator': district.designator},
        ))

    def test_district_summary_api_bolds_the_leading_candidate(self):
        trailing = make_candidate(make_person(full_name='Trailing Person'), self.election, self.district, status=self.status)
        self._result(self.district, 100, 1, candidate=self.candidate)
        self._result(self.district, 50, 2, candidate=trailing)
        response = self._summary(self.district)
        self.assertContains(response, f'<strong><a href="{self.candidate.person.get_absolute_url()}">A Candidate</a></strong>')
        self.assertNotContains(response, '<strong><a href="' + trailing.person.get_absolute_url())
        self.assertNotContains(response, 'Write-in leads')
        self.assertContains(response, 'Candidates in <strong>bold</strong> are leading')

    def test_district_summary_api_shows_write_in_leads_with_no_candidates(self):
        empty = make_district(designator='1A02', anc=self.anc, ward=self.ward)
        self._result(empty, 12, 1)
        response = self._summary(empty)
        self.assertContains(response, '<li><strong>Write-in leads, name unknown</strong></li>')
        self.assertContains(response, 'Candidates in <strong>bold</strong> are leading')

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


class ViewEdgeCaseTests(PageRenderingTestCase):
    def setUp(self):
        self.district = make_district(designator='1A01')
        self.person = make_person(full_name='Pat Elect')

    def test_district_detail_lists_commissioner_elect(self):
        today = date.today()
        make_commissioner_term(self.person, self.district, start_date=today + timedelta(days=30),
                               end_date=today + timedelta(days=760))
        response = self.client.get(self.district.get_absolute_url())
        self.assertEqual(response.context['future_terms'][0].person, self.person)
        row = response.context['commissioner_history'][0]
        self.assertEqual((row['status'], row['css_class']), ('future', 'term-future'))
        self.assertContains(response, 'Commissioner-elect')

    def test_person_detail_candidacy_without_result_has_no_label(self):
        make_candidate(self.person, make_election(year=2026), self.district)
        response = self.client.get(self.person.get_absolute_url())
        self.assertEqual(response.context['candidacies'][0].result_label, '')
