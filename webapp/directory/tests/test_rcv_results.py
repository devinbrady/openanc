"""Ranked-choice (RCV) round-by-round results: parsing DCBOE's RCVis tabulations, the
import_rcv_results command, and how the rounds show up on the site."""
import datetime
import io
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from directory import rcv
from directory.models import Election, ElectionResult, RankedChoiceContest, RankedChoiceTally
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import (
    make_anc,
    make_candidate,
    make_candidate_status,
    make_district,
    make_election,
    make_person,
    make_ward,
)

RELEASE_5 = 'Preliminary RCV Results 5 - Published November 20, 2026'
RELEASE_4 = 'Preliminary RCV Results 4 - Published November 16, 2026'


def summary(contest, rounds):
    """An RCTab summary JSON. rounds: [(tally, tallyResults)], tally {name: votes}."""
    return {
        'config': {'contest': contest, 'date': '', 'generatedBy': 'RCTab 2.1.0', 'jurisdiction': '', 'office': ''},
        'jsonFormatVersion': '1',
        'results': [
            {'round': n, 'tally': tally, 'tallyResults': results,
             'inactiveBallots': {'exhaustedChoices': '0', 'overvotes': '0', 'repeatedRankings': '0', 'skippedRankings': '0'}}
            for n, (tally, results) in enumerate(rounds, start=1)
        ],
        'summary': {'finalThreshold': '1', 'numCandidates': 3, 'numWinners': 1, 'totalNumBallots': '1', 'undervotes': 0},
    }


# 5E02 in release 5: the first-choice leader (Karla M. Lewis) lost in round 3.
THREE_ROUNDS = summary('1A01', [
    ({'Ada Avitabile': 173.0, 'Karla M. Lewis': 274.0, 'Matt Malinowski': 237.0, 'Write-in': 6.0, 'Inactive Ballots': 0},
     [{'eliminated': 'Write-in', 'transfers': {'Karla M. Lewis': 1.0, 'Inactive Ballots': 5.0}}]),
    ({'Ada Avitabile': 173.0, 'Karla M. Lewis': 275.0, 'Matt Malinowski': 237.0, 'Inactive Ballots': 5.0},
     [{'eliminated': 'Ada Avitabile', 'transfers': {'Karla M. Lewis': 35.0, 'Matt Malinowski': 88.0, 'Inactive Ballots': 50.0}}]),
    ({'Karla M. Lewis': 310.0, 'Matt Malinowski': 325.0, 'Inactive Ballots': 55.0},
     [{'elected': 'Matt Malinowski', 'transfers': {}}]),
])

ONE_ROUND = summary('1A02', [
    ({'Bree Ryback': 465.0, 'Andrew Davis': 157.0, 'Write-in': 9.0},
     [{'elected': 'Bree Ryback', 'transfers': {}}]),
])


def rcvis_page(summary_dict):
    return (
        '<html><head><title>1A01: Ranked Choice Voting Visualization</title></head><body>\n'
        f'<script id="rawDataId" type="application/json">{json.dumps(summary_dict)}</script>\n'
        '</body></html>'
    )


def contest_stats(*entries):
    """entries: (office_name, slug)."""
    return [
        {'ContestNumber': n, 'OfficeName': office, 'TotalVotesTallied': 100, 'SeatCount': 1,
         'VisualizationSourceURL': f'https://www.rcvis.com/v/{slug}', 'DetailedReportUrl': None}
        for n, (office, slug) in enumerate(entries, start=1)
    ]


class FakeResponse:
    def __init__(self, text=None, payload=None, status_code=200):
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload)
        self._payload = payload

    def json(self):
        return self._payload if self._payload is not None else json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f'{self.status_code}')


class FakeWeb:
    """Stands in for requests.get: DCBOE's election info and contest list, and RCVis pages."""

    def __init__(self, releases, stats_by_release, pages):
        self.releases = releases
        self.stats_by_release = stats_by_release
        self.pages = pages
        self.urls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.urls.append(url)
        if url.endswith('/electionResults/getElectionInfo/2026-General-Election'):
            return FakeResponse(payload={'ElectionCode': '2026-General-Election', 'IsRCV': True,
                                         'RCVPublishedDisplayNames': self.releases})
        if url.endswith('/RCV/GetContestStats/2026-General-Election'):
            return FakeResponse(payload=self.stats_by_release[params['displayName']])
        match = re.match(r'https://www\.rcvis\.com/v/(.+)$', url)
        if match and match.group(1) in self.pages:
            return FakeResponse(text=self.pages[match.group(1)])
        return FakeResponse(text='not found', status_code=404)

    def rcvis_urls(self):
        return [u for u in self.urls if 'rcvis.com' in u]


class ParsingTests(SimpleTestCase):
    def test_extracts_summary_json_from_rcvis_page(self):
        self.assertEqual(rcv.extract_summary(rcvis_page(THREE_ROUNDS)), THREE_ROUNDS)

    def test_page_without_summary_is_an_error(self):
        with self.assertRaisesMessage(rcv.RcvError, 'No tabulation data'):
            rcv.extract_summary('<html><body>Not found</body></html>')

    def test_rounds_mark_eliminated_and_elected_and_separate_inactive_ballots(self):
        rounds = rcv.parse_rounds(THREE_ROUNDS)
        self.assertEqual([r.number for r in rounds], [1, 2, 3])
        self.assertEqual(rounds[0].tallies, {'Ada Avitabile': 173, 'Karla M. Lewis': 274, 'Matt Malinowski': 237, 'Write-in': 6})
        self.assertEqual(rounds[0].inactive, 0)
        self.assertEqual(rounds[0].eliminated, ['Write-in'])
        self.assertEqual(rounds[1].eliminated, ['Ada Avitabile'])
        self.assertEqual(rounds[2].elected, ['Matt Malinowski'])
        self.assertEqual(rounds[2].inactive, 55)

    def test_fractional_votes_are_an_error(self):
        bad = summary('1A01', [({'A': 1.5, 'B': 2.0}, [{'elected': 'B', 'transfers': {}}])])
        with self.assertRaisesMessage(rcv.RcvError, 'not a whole number'):
            rcv.parse_rounds(bad)

    def test_designators(self):
        self.assertEqual(rcv.office_designator('ANC-1B03'), '1B03')
        self.assertIsNone(rcv.office_designator('MAYOR OF THE DISTRICT OF COLUMBIA'))
        self.assertEqual(rcv.summary_designator({'config': {'contest': '1b03'}}), '1B03')
        self.assertEqual(rcv.summary_designator({'config': {'contest': 'ANC 6A06'}}), '6A06')
        self.assertEqual(rcv.summary_designator({'config': {'contest': 'ANC-6A06'}}), '6A06')

    def test_only_rcvis_visualization_links_are_fetched(self):
        self.assertEqual(rcv.rcvis_slug('https://www.rcvis.com/v/anc-6a06-5'), 'anc-6a06-5')
        with self.assertRaisesMessage(rcv.RcvError, 'Not an RCVis visualization link'):
            rcv.rcvis_slug('https://example.com/v/1a01')

    def test_release_date_from_display_name(self):
        self.assertEqual(rcv.release_date(RELEASE_5), datetime.date(2026, 11, 20))
        self.assertIsNone(rcv.release_date('Final RCV Results'))


class RcvFixtureMixin:
    def setUp(self):
        ward = make_ward(number=1)
        anc = make_anc(designator='1A')
        self.d1 = make_district(designator='1A01', anc=anc, ward=ward)
        self.d2 = make_district(designator='1A02', anc=anc, ward=ward)
        self.election = make_election(
            year=2026, uses_ranked_choice=True, results_status=Election.RESULTS_UNOFFICIAL,
            results_as_of=datetime.date(2026, 11, 20),
        )
        self.status = make_candidate_status()
        self.results = {}
        for district, names in ((self.d1, ['Karla M. Lewis', 'Matt Malinowski', 'Ada Avitabile']),
                                (self.d2, ['Bree Ryback', 'Andrew Davis'])):
            first_choice = {'Karla M. Lewis': 272, 'Matt Malinowski': 236, 'Ada Avitabile': 172,
                            'Bree Ryback': 465, 'Andrew Davis': 157}
            for ranking, name in enumerate(names, start=1):
                candidate = make_candidate(make_person(full_name=name), self.election, district, status=self.status)
                self.results[name] = ElectionResult.objects.create(
                    election=self.election, district=district, candidate=candidate,
                    candidate_name_raw=name, votes=first_choice[name], ranking=ranking,
                )
            self.results[f'Write-in {district.designator}'] = ElectionResult.objects.create(
                election=self.election, district=district, candidate_name_raw='Write-in', votes=6,
                ranking=len(names) + 1,
            )


class ImportRcvResultsTests(RcvFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.cache_dir = Path(tempfile.mkdtemp())
        self.web = FakeWeb(
            releases=[RELEASE_5, RELEASE_4],
            stats_by_release={
                RELEASE_5: contest_stats(('MAYOR OF THE DISTRICT OF COLUMBIA', 'mayor-18'),
                                         ('ANC-1A01', '1a01-4'), ('ANC-1A02', 'anc-1a02-5')),
                RELEASE_4: contest_stats(('ANC-1A01', '1a01-3')),
            },
            pages={'1a01-4': rcvis_page(THREE_ROUNDS), 'anc-1a02-5': rcvis_page(ONE_ROUND),
                   '1a01-3': rcvis_page(THREE_ROUNDS)},
        )

    def run_import(self, *extra):
        out = io.StringIO()
        with mock.patch('directory.rcv.requests.get', side_effect=self.web.get), \
                mock.patch('directory.rcv.time.sleep') as sleep:
            call_command('import_rcv_results', '--year', '2026', '--cache-dir', str(self.cache_dir), *extra, stdout=out)
        self.sleep = sleep
        return out.getvalue()

    def test_dry_run_reports_and_writes_nothing(self):
        out = self.run_import()
        self.assertIn(RELEASE_5, out)
        self.assertIn('1A01: 3 rounds, Matt Malinowski elected (first-choice leader was Karla M. Lewis)', out)
        self.assertIn('1A02: 1 round, Bree Ryback elected', out)
        self.assertIn('Dry run', out)
        self.assertFalse(RankedChoiceContest.objects.exists())
        self.assertFalse(ElectionResult.objects.exclude(rcv_outcome='').exists())

    def test_apply_stores_rounds_and_outcomes(self):
        self.run_import('--apply')
        contest = RankedChoiceContest.objects.get(district=self.d1)
        self.assertEqual(contest.election, self.election)
        self.assertEqual(contest.rcvis_url, 'https://www.rcvis.com/v/1a01-4')
        self.assertEqual(contest.release_name, RELEASE_5)
        self.assertEqual(contest.release_date, datetime.date(2026, 11, 20))
        self.assertEqual(contest.num_rounds, 3)

        tallies = {(t.round_number, t.candidate_name_raw): t for t in contest.tallies.all()}
        self.assertEqual(len(tallies), (4 + 1) + (3 + 1) + (2 + 1))  # candidates left, plus inactive ballots, each round
        karla = tallies[(1, 'Karla M. Lewis')]
        self.assertEqual((karla.votes, karla.candidate, karla.outcome), (274, self.results['Karla M. Lewis'].candidate, ''))
        self.assertEqual(tallies[(1, 'Write-in')].outcome, RankedChoiceTally.OUTCOME_ELIMINATED)
        self.assertIsNone(tallies[(1, 'Write-in')].candidate)
        self.assertEqual(tallies[(2, 'Ada Avitabile')].outcome, RankedChoiceTally.OUTCOME_ELIMINATED)
        self.assertEqual(tallies[(3, 'Matt Malinowski')].outcome, RankedChoiceTally.OUTCOME_ELECTED)
        inactive = tallies[(3, 'Inactive ballots')]
        self.assertTrue(inactive.is_inactive)
        self.assertEqual(inactive.votes, 55)

        outcomes = {r.candidate_name_raw: r.rcv_outcome for r in ElectionResult.objects.filter(district=self.d1)}
        self.assertEqual(outcomes, {'Matt Malinowski': 'elected', 'Karla M. Lewis': 'eliminated',
                                    'Ada Avitabile': 'eliminated', 'Write-in': 'eliminated'})
        self.assertEqual(RankedChoiceContest.objects.get(district=self.d2).num_rounds, 1)
        self.assertEqual(str(contest), f'{self.d1} (2026): 3 RCV round(s)')
        self.assertEqual(str(tallies[(3, 'Matt Malinowski')]), f'{self.d1} round 3: Matt Malinowski 325')
        self.assertEqual(self.results['Andrew Davis'].__class__.objects.get(pk=self.results['Andrew Davis'].pk).rcv_outcome,
                         'eliminated')

    def test_non_anc_contests_are_skipped_and_pages_are_throttled(self):
        self.run_import()
        self.assertEqual(self.web.rcvis_urls(), ['https://www.rcvis.com/v/1a01-4', 'https://www.rcvis.com/v/anc-1a02-5'])
        self.sleep.assert_called_with(rcv.RCVIS_REQUEST_DELAY_SECONDS)

    def test_rcvis_pages_and_contest_lists_are_cached(self):
        self.run_import()
        self.web.urls.clear()
        self.run_import('--apply')
        self.assertEqual(self.web.rcvis_urls(), [])
        self.assertFalse(any('GetContestStats' in u for u in self.web.urls))
        self.assertTrue((self.cache_dir / '2026-General-Election' / 'rcvis' / '1a01-4.json').exists())

    def test_named_release_is_imported_and_a_new_release_replaces_it(self):
        self.run_import('--release', RELEASE_4, '--apply')
        self.assertEqual(RankedChoiceContest.objects.get().rcvis_url, 'https://www.rcvis.com/v/1a01-3')

        self.run_import('--apply')
        self.assertEqual(RankedChoiceContest.objects.count(), 2)
        contest = RankedChoiceContest.objects.get(district=self.d1)
        self.assertEqual((contest.rcvis_url, contest.release_name), ('https://www.rcvis.com/v/1a01-4', RELEASE_5))
        self.assertEqual(contest.tallies.count(), 12)

    def test_district_no_longer_tabulated_is_cleared(self):
        self.run_import('--apply')
        self.web.stats_by_release[RELEASE_5] = contest_stats(('ANC-1A01', '1a01-4'))
        self.web.releases = [RELEASE_5]
        (self.cache_dir / '2026-General-Election').joinpath('contests', f'{rcv.cache_name(RELEASE_5)}.json').unlink()
        self.run_import('--apply')
        self.assertFalse(RankedChoiceContest.objects.filter(district=self.d2).exists())
        self.assertFalse(ElectionResult.objects.filter(district=self.d2).exclude(rcv_outcome='').exists())

    def test_unknown_release_is_an_error(self):
        with self.assertRaisesMessage(CommandError, 'not one of DCBOE'):
            self.run_import('--release', 'Preliminary RCV Results 9')

    def test_unmatched_name_writes_nothing(self):
        self.web.pages['anc-1a02-5'] = rcvis_page(summary('1A02', [
            ({'Bree Ryback': 465.0, 'Somebody Else': 157.0}, [{'elected': 'Bree Ryback', 'transfers': {}}]),
        ]))
        with self.assertRaisesMessage(CommandError, '1A02: "Somebody Else" has no first-choice result row'):
            self.run_import('--apply')
        self.assertFalse(RankedChoiceContest.objects.exists())

    def test_contest_name_must_match_dcboe_office(self):
        self.web.pages['anc-1a02-5'] = rcvis_page(dict(ONE_ROUND, config={'contest': '1A03'}))
        with self.assertRaisesMessage(CommandError, 'anc-1a02-5 is contest 1A03, but DCBOE lists it for 1A02'):
            self.run_import()

    def test_contest_needs_exactly_one_winner(self):
        self.web.pages['anc-1a02-5'] = rcvis_page(summary('1A02', [
            ({'Bree Ryback': 300.0, 'Andrew Davis': 300.0}, [{'eliminated': 'Andrew Davis', 'transfers': {}}]),
        ]))
        with self.assertRaisesMessage(CommandError, '1A02: expected one winner in the last round'):
            self.run_import()

    def test_missing_rcvis_page_is_an_error(self):
        del self.web.pages['anc-1a02-5']
        with self.assertRaisesMessage(CommandError, 'anc-1a02-5'):
            self.run_import()

    def test_certified_election_marks_rcv_winner(self):
        self.election.results_status = Election.RESULTS_CERTIFIED
        self.election.save()
        ElectionResult.objects.filter(ranking=1).update(is_winner=True)
        self.run_import('--apply')
        winners = set(ElectionResult.objects.filter(is_winner=True).values_list('candidate_name_raw', flat=True))
        self.assertEqual(winners, {'Matt Malinowski', 'Bree Ryback'})

    def test_election_without_rcv_is_an_error(self):
        with self.assertRaisesMessage(CommandError, 'No 2030 election'):
            out = io.StringIO()
            call_command('import_rcv_results', '--year', '2030', stdout=out)
        make_election(year=2024)
        with self.assertRaisesMessage(CommandError, "doesn't use ranked choice"):
            call_command('import_rcv_results', '--year', '2024', stdout=io.StringIO())

    def test_no_releases_yet_is_an_error(self):
        self.web.releases = []
        with self.assertRaisesMessage(CommandError, 'has not published any RCV results'):
            self.run_import()


class IsLeaderTests(RcvFixtureMixin, TestCase):
    def test_first_choice_leader_leads_without_rcv(self):
        self.assertTrue(self.results['Karla M. Lewis'].is_leader)
        self.assertFalse(self.results['Matt Malinowski'].is_leader)

    def test_rcv_winner_leads_once_tabulated(self):
        ElectionResult.objects.filter(district=self.d1).update(rcv_outcome='eliminated')
        ElectionResult.objects.filter(candidate_name_raw='Matt Malinowski').update(rcv_outcome='elected')
        karla = ElectionResult.objects.get(candidate_name_raw='Karla M. Lewis')
        matt = ElectionResult.objects.get(candidate_name_raw='Matt Malinowski')
        self.assertFalse(karla.is_leader)
        self.assertEqual(karla.outcome_label, '')
        self.assertTrue(matt.is_leader)
        self.assertEqual(matt.outcome_label, 'Leading')

    def test_certified_goes_by_is_winner(self):
        self.election.results_status = Election.RESULTS_CERTIFIED
        self.election.save()
        ElectionResult.objects.filter(candidate_name_raw='Matt Malinowski').update(rcv_outcome='elected', is_winner=True)
        self.assertTrue(ElectionResult.objects.get(candidate_name_raw='Matt Malinowski').is_leader)
        self.assertFalse(ElectionResult.objects.get(candidate_name_raw='Karla M. Lewis').is_leader)


class RcvDisplayTests(RcvFixtureMixin, PageRenderingTestCase):
    def setUp(self):
        super().setUp()
        cache_dir = Path(tempfile.mkdtemp())
        web = FakeWeb(
            releases=[RELEASE_5],
            stats_by_release={RELEASE_5: contest_stats(('ANC-1A01', '1a01-4'), ('ANC-1A02', 'anc-1a02-5'))},
            pages={'1a01-4': rcvis_page(THREE_ROUNDS), 'anc-1a02-5': rcvis_page(ONE_ROUND)},
        )
        with mock.patch('directory.rcv.requests.get', side_effect=web.get), mock.patch('directory.rcv.time.sleep'):
            call_command('import_rcv_results', '--year', '2026', '--cache-dir', str(cache_dir), '--apply',
                         stdout=io.StringIO())

    def rcv_table(self, district):
        content = self.client.get(district.get_absolute_url()).content.decode()
        start = content.index('Ranked-choice rounds')
        return re.sub(r'\s+', ' ', content[start:content.index('</table>', start)])

    def test_multi_round_contest_shows_each_round(self):
        response = self.client.get(self.d1.get_absolute_url())
        self.assertContains(response, 'Ranked-choice rounds')
        for heading in ('Round 1', 'Round 2', 'Round 3'):
            self.assertContains(response, f'<th>{heading}</th>', html=True)
        self.assertContains(response, RELEASE_5)
        self.assertContains(response, 'href="https://www.rcvis.com/v/1a01-4"')
        self.assertNotContains(response, 'No candidate has a majority of first-choice votes')

        table = self.rcv_table(self.d1)
        rows = re.findall(r'<tr>(.*?)</tr>', table)
        names = [re.sub(r'<[^>]+>', '', re.findall(r'<td>(.*?)</td>', row)[0]).strip() for row in rows[1:]]
        # Winner first, then by how long each candidate lasted, inactive ballots last.
        self.assertEqual(names, ['Matt Malinowski', 'Karla M. Lewis', 'Ada Avitabile', 'Write-in', 'Inactive ballots'])
        self.assertIn('<td>237</td> <td>237</td> <td>325</td> <td>Leading</td>', table)
        self.assertIn('<td>173</td> <td>173</td> <td>—</td> <td>Eliminated in round 2</td>', table)
        self.assertIn('<td>274</td> <td>275</td> <td>310</td> <td>Trailing</td>', table)

    def test_certified_round_table_says_won_and_runner_up(self):
        self.election.results_status = Election.RESULTS_CERTIFIED
        self.election.save()
        table = self.rcv_table(self.d1)
        self.assertIn('<td>325</td> <td>Won</td>', table)
        self.assertIn('<td>310</td> <td>Runner-up</td>', table)

    def test_leading_label_follows_rcv_winner_in_first_choice_table(self):
        response = self.client.get(self.d1.get_absolute_url())
        content = re.sub(r'\s+', ' ', response.content.decode())
        first_choice = content[content.index('First-choice votes'):content.index('Ranked-choice rounds')]
        self.assertRegex(first_choice, r'Matt Malinowski</a> </td> <td>236</td> <td>[\d.]+%</td> <td>Leading</td>')
        self.assertRegex(first_choice, r'Karla M. Lewis</a> </td> <td>272</td> <td>[\d.]+%</td> <td></td>')

    def test_single_round_contest_has_no_round_table(self):
        response = self.client.get(self.d2.get_absolute_url())
        self.assertNotContains(response, 'Ranked-choice rounds')
        self.assertContains(response, 'won a majority in the first round')
        self.assertContains(response, 'href="https://www.rcvis.com/v/anc-1a02-5"')

    def test_person_page_labels_follow_rcv(self):
        matt = self.results['Matt Malinowski'].candidate.person
        karla = self.results['Karla M. Lewis'].candidate.person
        self.assertContains(self.client.get(matt.get_absolute_url()), 'Leading after 3 ranked-choice rounds')
        self.assertNotContains(self.client.get(karla.get_absolute_url()), 'Leading')

    def test_district_json_includes_rounds(self):
        url = reverse('directory:api_district', kwargs={'year': 2022, 'designator': '1A01'})
        with self.settings(CURRENT_ELECTION_YEAR=2026):
            data = self.client.get(url).json()
        ranked = data['election']['ranked_choice']
        self.assertEqual(ranked['source'], RELEASE_5)
        self.assertEqual(ranked['rcvis_url'], 'https://www.rcvis.com/v/1a01-4')
        self.assertEqual(ranked['winner'], 'Matt Malinowski')
        self.assertEqual(len(ranked['rounds']), 3)
        self.assertEqual(ranked['rounds'][2], {
            'round': 3,
            'votes': {'Matt Malinowski': 325, 'Karla M. Lewis': 310},
            'inactive_ballots': 55,
            'eliminated': [],
            'elected': ['Matt Malinowski'],
        })
        self.assertTrue(data['election']['results'][1]['is_leading'])

    def test_district_list_bolds_rcv_winner(self):
        with self.settings(CURRENT_ELECTION_YEAR=2026):
            response = self.client.get(reverse('directory:district_list'))
        matt = self.results['Matt Malinowski'].candidate.person
        self.assertContains(response, f'<strong><a href="{matt.get_absolute_url()}">Matt Malinowski</a></strong>')
        self.assertNotContains(response, '>Karla M. Lewis</a></strong>')


class RcvAdminTests(RcvFixtureMixin, PageRenderingTestCase):
    def test_contest_page_shows_rounds_read_only(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True))
        contest = RankedChoiceContest.objects.create(
            election=self.election, district=self.d1, rcvis_url='https://www.rcvis.com/v/1a01-4',
            release_name=RELEASE_5, num_rounds=1,
        )
        RankedChoiceTally.objects.create(contest=contest, round_number=1, candidate_name_raw='Matt Malinowski',
                                         votes=325, outcome=RankedChoiceTally.OUTCOME_ELECTED)
        response = self.client.get(reverse('admin:directory_rankedchoicecontest_change', args=[contest.pk]))
        self.assertContains(response, 'Matt Malinowski')
        self.assertNotContains(response, 'name="tallies-0-votes"')
        self.assertNotContains(response, 'name="tallies-__prefix__-votes"')
        self.assertEqual(self.client.get(reverse('admin:directory_rankedchoicecontest_changelist')).status_code, 200)
