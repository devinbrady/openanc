import datetime
import io
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from directory.models import Election, ElectionResult
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

HEADER = 'ElectionDate,ElectionName,ContestNumber,ContestName,PrecinctNumber,WardNumber,Candidate,Party,Votes\n'


def results_csv(rows):
    """rows: (contest_name, precinct, candidate, votes). Adds the citywide rows DCBOE files
    always start with, which the importer must skip."""
    lines = [HEADER, '11/3/2026 12:00:00 AM,General Election,-1,BALLOTS CAST - TOTAL,1,1,,CITYWIDE,999\n']
    for contest, precinct, candidate, votes in rows:
        lines.append(f'11/3/2026 12:00:00 AM,General Election,20,{contest},{precinct},1,{candidate},NPN,{votes}\n')
    return ''.join(lines)


class ImportElectionResultsBase(TestCase):
    def setUp(self):
        ward = make_ward(number=1)
        anc = make_anc(designator='1A')
        self.d1 = make_district(designator='1A01', anc=anc, ward=ward)
        self.d2 = make_district(designator='1A02', anc=anc, ward=ward)
        self.election = make_election(year=2026, uses_ranked_choice=True)
        status = make_candidate_status()
        # Display name differs from the ballot spelling; the ballot spelling is an alias.
        self.zach = make_person(full_name='Zachary Adams')
        self.zach.aliases.create(name='Zach Adams', source='dcboe_ballot')
        self.maria = make_person(full_name='María López')
        self.third = make_person(full_name='Third Person')
        self.zach_c = make_candidate(self.zach, self.election, self.d1, status=status)
        self.maria_c = make_candidate(self.maria, self.election, self.d1, status=status)
        make_candidate(self.third, self.election, self.d1, status=status)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write(self, rows, name='results.csv'):
        path = Path(self._tmp.name) / name
        path.write_text(results_csv(rows), encoding='utf-8')
        return str(path)

    def run_import(self, path, *extra, status='election_night', as_of='2026-11-04'):
        out = io.StringIO()
        call_command('import_election_results', path, '--year', '2026', '--status', status,
                     '--as-of', as_of, *extra, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def night_one(self):
        return self.write([
            ('ANC-1A01', 1, 'Zach Adams', 100), ('ANC-1A01', 2, 'Zach Adams', 50),
            ('ANC-1A01', 1, 'Maria Lopez', 120),
            ('ANC-1A01', 1, 'Third Person', 40),
            ('ANC-1A01', 1, 'Write-in', 5), ('ANC-1A01', 1, 'OVER VOTES', 2), ('ANC-1A01', 1, 'UNDER VOTES', 30),
            ('ANC-1A02 1A02', 1, 'Write-in', 12), ('ANC-1A02 1A02', 1, 'UNDER VOTES', 80),
        ])



class ImportElectionResultsTests(ImportElectionResultsBase):
    def test_dry_run_reports_and_writes_nothing(self):
        output = self.run_import(self.night_one())
        self.assertIn('2 ANC contests, 5 result rows, 327 first-choice votes', output)
        self.assertIn('No first-choice majority', output)
        self.assertIn('1A01 (leader 47.6%)', output)
        self.assertFalse(ElectionResult.objects.exists())

    def test_apply_sums_precincts_links_by_alias_and_ranks(self):
        self.run_import(self.night_one(), '--apply')

        rows = list(ElectionResult.objects.filter(district=self.d1).order_by('ranking'))
        self.assertEqual([(r.candidate, r.votes) for r in rows], [
            (self.zach_c, 150), (self.maria_c, 120), (self.third.candidacies.get(), 40), (None, 5),
        ])
        self.assertEqual(rows[0].candidate_name_raw, 'Zach Adams')
        self.assertEqual(rows[0].margin_of_victory, 30)
        self.assertEqual(rows[1].margin_of_victory, -30)
        self.assertFalse(any(r.is_winner for r in rows))  # not certified yet

        write_in_only = ElectionResult.objects.get(district=self.d2)
        self.assertEqual((write_in_only.candidate, write_in_only.votes, write_in_only.ranking), (None, 12, 1))
        self.assertIsNone(write_in_only.margin_of_victory)

        # The accent-free ballot spelling is now remembered; the display name is unchanged.
        self.assertTrue(self.maria.aliases.filter(name='Maria Lopez', source='dcboe_results').exists())
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.full_name, 'María López')

        self.election.refresh_from_db()
        self.assertEqual(self.election.results_status, Election.RESULTS_ELECTION_NIGHT)
        self.assertEqual(self.election.results_as_of, datetime.date(2026, 11, 4))
        self.assertEqual(self.election.results_source, 'results.csv')

    def test_rerun_updates_in_place_and_reports_leader_change(self):
        self.run_import(self.night_one(), '--apply')
        first_ids = set(ElectionResult.objects.values_list('pk', flat=True))

        update = self.write([
            ('ANC-1A01', 1, 'Zach Adams', 150), ('ANC-1A01', 1, 'Maria Lopez', 190),
            ('ANC-1A01', 1, 'Third Person', 41), ('ANC-1A01', 1, 'Write-in', 5),
            ('ANC-1A02', 1, 'Write-in', 14),
        ], name='update.csv')
        output = self.run_import(update, status='unofficial', as_of='2026-11-06')
        self.assertIn('1A01: Zach Adams -> Maria Lopez', output)
        self.assertIn('1A02 Write-in: 12 -> 14', output)

        self.run_import(update, '--apply', status='unofficial', as_of='2026-11-06')
        self.assertEqual(set(ElectionResult.objects.values_list('pk', flat=True)), first_ids)
        maria_row = ElectionResult.objects.get(candidate=self.maria_c)
        self.assertEqual((maria_row.votes, maria_row.ranking), (190, 1))
        self.assertEqual(maria_row.history.count(), 2)

    def test_certified_sets_winners(self):
        self.run_import(self.night_one(), '--apply', status='certified')
        self.assertTrue(ElectionResult.objects.get(candidate=self.zach_c).is_winner)
        write_in_only = ElectionResult.objects.get(district=self.d2)
        self.assertTrue(write_in_only.is_winner)
        self.assertTrue(write_in_only.is_write_in_winner)

    def test_unlinkable_name_writes_nothing(self):
        path = self.write([('ANC-1A01', 1, 'Zach Adams', 10), ('ANC-1A01', 1, 'Somebody Unknown', 5)])
        with self.assertRaises(CommandError):
            self.run_import(path, '--apply')
        self.assertFalse(ElectionResult.objects.exists())

    def test_namesake_from_another_district_is_not_linked(self):
        other_ward = make_ward(number=7)
        far = make_district(designator='7B01', anc=make_anc(designator='7B'), ward=other_ward)
        make_commissioner_term(make_person(full_name='Pat Smith'), far)
        path = self.write([('ANC-1A01', 1, 'Pat Smith', 10)])
        with self.assertRaises(CommandError):
            self.run_import(path)

    def test_contest_for_unknown_district_is_an_error(self):
        with self.assertRaises(CommandError):
            self.run_import(self.write([('ANC-9Z01', 1, 'Write-in', 1)]))


class ResultsDisplayTests(PageRenderingTestCase):
    def setUp(self):
        self.district = make_district()
        self.status = status = make_candidate_status()
        self.election = make_election(
            year=2026, uses_ranked_choice=True, results_status=Election.RESULTS_ELECTION_NIGHT,
            results_as_of=datetime.date(2026, 11, 4),
        )
        self.leader = make_person(full_name='Front Runner')
        self.second = make_person(full_name='Close Second')
        leader_c = make_candidate(self.leader, self.election, self.district, status=status)
        second_c = make_candidate(self.second, self.election, self.district, status=status)
        ElectionResult.objects.create(election=self.election, district=self.district, candidate=leader_c,
                                      candidate_name_raw='Front Runner', votes=46, ranking=1)
        ElectionResult.objects.create(election=self.election, district=self.district, candidate=second_c,
                                      candidate_name_raw='Close Second', votes=44, ranking=2)
        ElectionResult.objects.create(election=self.election, district=self.district,
                                      candidate_name_raw='Write-in', votes=10, ranking=3)

    def test_district_page_shows_unofficial_first_choice_results(self):
        response = self.client.get(self.district.get_absolute_url())
        self.assertContains(response, 'Unofficial results as of November 4, 2026')
        self.assertContains(response, 'First-choice votes')
        self.assertContains(response, '<td>46.0%</td>', html=True)
        self.assertContains(response, '<td>Leading</td>', html=True)
        self.assertNotContains(response, '<td>Won</td>', html=True)
        self.assertContains(response, 'No candidate has a majority of first-choice votes')

    def test_certified_results_show_winner_and_no_banner(self):
        self.election.results_status = Election.RESULTS_CERTIFIED
        self.election.save()
        ElectionResult.objects.filter(ranking=1).update(is_winner=True)
        response = self.client.get(self.district.get_absolute_url())
        self.assertNotContains(response, 'Unofficial results')
        self.assertContains(response, '<td>Won</td>', html=True)
        self.assertNotContains(response, 'No candidate has a majority')

    def test_person_page_marks_votes_unofficial(self):
        response = self.client.get(self.leader.get_absolute_url())
        self.assertContains(response, '46 (unofficial, first choice)')

    def test_older_certified_results_unchanged(self):
        old = make_election(year=2024, results_status=Election.RESULTS_CERTIFIED)
        old_c = make_candidate(self.leader, old, self.district, status=self.status)
        ElectionResult.objects.create(election=old, district=self.district, candidate=old_c,
                                      candidate_name_raw='Front Runner', votes=300, ranking=1, is_winner=True)
        response = self.client.get(self.leader.get_absolute_url())
        self.assertContains(response, '<td>300</td>', html=True)
        district_page = self.client.get(reverse('directory:district_detail', kwargs={
            'year': self.district.redistricting_year, 'designator': self.district.designator}))
        self.assertContains(district_page, '<th>Votes</th>', html=True)


class PersonPageResultTests(PageRenderingTestCase):
    def setUp(self):
        self.district = make_district()
        self.status = make_candidate_status()
        self.person = make_person(full_name='Front Runner')

    def add_result(self, year, results_status, ranking):
        election = make_election(year=year, results_status=results_status)
        candidacy = make_candidate(self.person, election, self.district, status=self.status)
        return ElectionResult.objects.create(
            election=election, district=self.district, candidate=candidacy, candidate_name_raw='Front Runner',
            votes=100 - ranking, ranking=ranking,
            is_winner=ranking == 1 and results_status == Election.RESULTS_CERTIFIED,
        )

    def result_cells(self):
        import re
        content = self.client.get(self.person.get_absolute_url()).content.decode()
        table = content[content.index('<h2>Candidacies</h2>'):]
        return [re.sub(r'\s+', ' ', row) for row in re.findall(r'<tr>(.*?)</tr>', table, re.S)[1:]]

    def test_first_place_certified_is_won(self):
        self.add_result(2024, Election.RESULTS_CERTIFIED, 1)
        self.assertIn('<td>Won</td>', self.result_cells()[0])

    def test_first_place_unofficial_is_leading(self):
        self.add_result(2026, Election.RESULTS_ELECTION_NIGHT, 1)
        self.assertIn('<td>Leading</td>', self.result_cells()[0])

    def test_not_first_place_shows_nothing(self):
        self.add_result(2024, Election.RESULTS_CERTIFIED, 2)
        self.add_result(2026, Election.RESULTS_UNOFFICIAL, 2)
        for row in self.result_cells():
            self.assertNotIn('Won', row)
            self.assertNotIn('Leading', row)

    def test_certified_write_in_winner_is_won(self):
        from directory.models import WriteInWinner
        election = make_election(year=2024, results_status=Election.RESULTS_CERTIFIED)
        make_candidate(self.person, election, self.district, status=self.status)
        WriteInWinner.objects.create(election=election, district=self.district, person=self.person,
                                     candidate_name_raw='Front Runner')
        self.assertIn('<td>Won (write-in)</td>', self.result_cells()[0])

    def test_withdrawn_first_place_with_no_winner(self):
        """2022's 1E01/6E08/7D10: first place had withdrawn, so no one won and the seat was vacant."""
        result = self.add_result(2022, Election.RESULTS_CERTIFIED, 1)
        result.is_winner = False
        result.save()
        self.assertNotIn('Won', self.result_cells()[0])
        district_page = self.client.get(self.district.get_absolute_url())
        self.assertContains(district_page, 'No one won this election')
        self.assertNotContains(district_page, '<td>Won</td>', html=True)

    def test_no_winner_note_only_when_nobody_won(self):
        self.add_result(2024, Election.RESULTS_CERTIFIED, 1)
        self.assertNotContains(self.client.get(self.district.get_absolute_url()), 'No one won this election')


class ImportElectionResultsErrorTests(ImportElectionResultsBase):
    """Reuses the parent's setUp/write/run_import helpers; see the parent for the happy path."""

    def test_unknown_election_year_is_an_error(self):
        with self.assertRaisesMessage(CommandError, 'No 2030 election.'):
            call_command('import_election_results', self.night_one(), '--year', '2030', '--status', 'unofficial',
                         '--as-of', '2026-11-04', stdout=io.StringIO())

    def test_file_with_no_anc_contests_is_an_error(self):
        path = self.write([('MAYOR', 1, 'Someone', 100)])
        with self.assertRaisesMessage(CommandError, 'No ANC contests found in'):
            self.run_import(path)

    def test_districts_missing_from_the_file_are_reported(self):
        path = self.write([('ANC-1A01', 1, 'Zach Adams', 100), ('ANC-1A01', 1, 'Maria Lopez', 90)])
        self.assertIn('No contest in the file for 1 district(s): 1A02', self.run_import(path))
