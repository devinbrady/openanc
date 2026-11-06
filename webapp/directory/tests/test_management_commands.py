import datetime
import io

from django.core.management import call_command
from django.test import TestCase

from directory.models import Candidate, CommissionerTerm, SiteUpdate, WriteInWinner
from directory.tests.factories import (
    make_candidate, make_candidate_status, make_commissioner_term, make_district, make_election, make_person,
)


class DraftSiteUpdateTests(TestCase):
    def test_creates_unpublished_draft_mentioning_the_district(self):
        district = make_district(designator='1A01')
        outgoing = make_person(full_name='Outgoing Commissioner')
        incoming = make_person(full_name='Incoming Commissioner')
        today = datetime.date.today()

        term = make_commissioner_term(
            outgoing, district, start_date=today - datetime.timedelta(days=400), end_date=today + datetime.timedelta(days=1),
        )
        term.end_date = today
        term.save()
        make_commissioner_term(incoming, district, start_date=today, end_date=today + datetime.timedelta(days=730))

        call_command('draft_site_update')

        draft = SiteUpdate.objects.get()
        self.assertFalse(draft.is_published)
        self.assertEqual(draft.date, today)
        self.assertIn('1A01', draft.body)
        self.assertIn('Incoming Commissioner', draft.body)

    def test_no_changes_creates_no_draft(self):
        call_command('draft_site_update')
        self.assertEqual(SiteUpdate.objects.count(), 0)

    def test_since_defaults_to_last_published_update(self):
        old = datetime.date.today() - datetime.timedelta(days=30)
        SiteUpdate.objects.create(date=old, body='old news', is_published=True)
        make_person(full_name='Someone New')

        call_command('draft_site_update')

        draft = SiteUpdate.objects.get(is_published=False)
        self.assertIn('Someone New', draft.body)

    def test_skips_changes_already_covered_by_last_published_update(self):
        make_person(full_name='Already Announced')
        SiteUpdate.objects.create(date=datetime.date.today(), body='earlier today', is_published=True)
        make_person(full_name='Added Afterward')

        call_command('draft_site_update')

        body = SiteUpdate.objects.get(is_published=False).body
        self.assertNotIn('Already Announced', body)
        self.assertIn('Added Afterward', body)

    def test_candidate_lines_link_district_and_person(self):
        district = make_district(designator='1A01')
        person = make_person(full_name='Write In Person')
        make_candidate(person, make_election(year=2026), district, status=make_candidate_status(name='Write-In Candidate'))

        call_command('draft_site_update')

        body = SiteUpdate.objects.get().body
        self.assertIn(
            f'<a href="{district.get_absolute_url()}">SMD 1A01 (2022)</a>: '
            f'<a href="{person.get_absolute_url()}">Write In Person</a> added as a candidate '
            '(election year 2026, status: Write-In Candidate).',
            body,
        )

    def test_summary_table_counts_changes_by_candidate_status(self):
        election = make_election(year=2026)
        write_in = make_candidate_status(name='Write-In Candidate', display_order=1)
        withdrew = make_candidate_status(name='Withdrew', display_order=2)
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        first = make_district(designator='1A01')
        make_candidate(make_person(full_name='Existing'), election, first, status=write_in)
        Candidate.history.update(history_date=datetime.datetime.combine(yesterday, datetime.time(12), tzinfo=datetime.timezone.utc))
        make_candidate(make_person(full_name='Newcomer'), election, make_district(designator='1A02', anc=first.anc, ward=first.ward), status=write_in)
        dropout = make_candidate(make_person(full_name='Dropout'), election, make_district(designator='1A03', anc=first.anc, ward=first.ward), status=write_in)
        dropout.status = withdrew
        dropout.save()

        call_command('draft_site_update', since=datetime.date.today())

        body = SiteUpdate.objects.get().body
        self.assertIn('<tr><th>Type</th><th>Old</th><th>Diff</th><th>New</th></tr>', body)
        self.assertIn('<tr><td>Write-in candidates</td><td>1</td><td>+1</td><td>2</td></tr>', body)
        self.assertIn('<tr><td>Withdrawn candidates</td><td>0</td><td>+1</td><td>1</td></tr>', body)


class EditorialRowCountsTests(TestCase):
    def run_command(self):
        from io import StringIO
        out = StringIO()
        call_command('editorial_row_counts', stdout=out)
        return dict(
            (label, rest.split())
            for label, rest in (line.split(': ') for line in out.getvalue().splitlines())
        )

    def test_hash_changes_when_a_row_is_edited_without_changing_the_count(self):
        person = make_person(full_name='Before')
        before = self.run_command()['directory.Person']

        person.full_name = 'After'
        person.save()
        after = self.run_command()['directory.Person']

        self.assertEqual(before[0], after[0])
        self.assertNotEqual(before[1], after[1])

    def test_hash_is_stable_when_nothing_changes(self):
        make_person(full_name='Same')
        self.assertEqual(self.run_command(), self.run_command())

    def test_hash_ignores_sub_millisecond_timestamp_differences(self):
        # Production's copy of a pushed row has timestamps truncated to milliseconds by the
        # JSON fixture; that alone must not make the tables look different.
        candidate = make_candidate(make_person(), make_election(), make_district())
        stamp = datetime.datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=datetime.timezone.utc)
        Candidate.objects.filter(pk=candidate.pk).update(created_at=stamp)
        precise = self.run_command()['directory.Candidate']

        Candidate.objects.filter(pk=candidate.pk).update(created_at=stamp.replace(microsecond=123000))
        truncated = self.run_command()['directory.Candidate']
        self.assertEqual(precise, truncated)


class BackfillPersonAliasesTests(TestCase):
    def setUp(self):
        import tempfile
        from directory.tests.factories import make_candidate, make_district, make_election, make_person
        self.district = make_district(designator='1A01')
        self.election = make_election(year=2026)
        self.zach = make_person(full_name='Zachary Adams')
        self.other = make_person(full_name='Maria Lopez')
        make_candidate(self.zach, self.election, self.district)
        make_candidate(self.other, self.election, self.district, status=self.zach.candidacies.get().status)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        with open(f'{self._tmp.name}/dcboe-ballot-2026-10-13.csv', 'w') as f:
            f.write('ANC-SMD,Name\n1A01,Zach Adams\n1A01,María López\n1A01,Totally Unknown\n')

    def run_command(self, *args):
        out = io.StringIO()
        call_command('backfill_person_aliases', '--dcboe-dir', self._tmp.name, *args, stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        output = self.run_command()
        self.assertIn('Would add 2 alias(es)', output)
        self.assertIn('"Totally Unknown" in 1A01', output)
        self.assertFalse(self.zach.aliases.filter(name='Zach Adams').exists())

    def test_apply_adds_aliases_and_is_rerunnable(self):
        self.run_command('--apply')
        self.assertEqual(self.zach.aliases.get(name='Zach Adams').source, 'dcboe_ballot')
        self.assertTrue(self.other.aliases.filter(name='María López').exists())
        self.zach.refresh_from_db()
        self.assertEqual(self.zach.full_name, 'Zachary Adams')
        self.assertIn('Would add 0 alias(es)', self.run_command())


class DraftSiteUpdateHistoryTests(TestCase):
    """The individual change lines draft_site_update builds from django-simple-history records."""

    def setUp(self):
        self.district = make_district(designator='1A01')
        self.person = make_person(full_name='Pat Commissioner')
        self.today = datetime.date.today()

    def draft(self, *args):
        out = io.StringIO()
        call_command('draft_site_update', *args, stdout=out)
        draft = SiteUpdate.objects.filter(is_published=False).first()
        return draft.body if draft else None

    def backdate_all_history(self):
        """Move every history record so far to yesterday, i.e. before the window."""
        yesterday = datetime.datetime.combine(
            self.today - datetime.timedelta(days=1), datetime.time(12), tzinfo=datetime.timezone.utc,
        )
        from directory.models import Person
        for model in (CommissionerTerm, Candidate, Person, WriteInWinner):
            model.history.update(history_date=yesterday)

    def test_date_and_since_options_parse_iso_dates(self):
        body = self.draft('--since', self.today.isoformat(), '--date', self.today.isoformat())
        self.assertIn(f'Changes from {self.today.isoformat()} to {self.today.isoformat()}', body)

    def test_published_update_without_history_falls_back_to_start_of_its_date(self):
        update = SiteUpdate.objects.create(date=self.today, body='earlier', is_published=True)
        update.history.all().delete()
        self.assertIn('Pat Commissioner', self.draft())

    def test_term_end_date_change_is_reported_without_summary_table(self):
        term = make_commissioner_term(self.person, self.district, end_date=datetime.date(2027, 1, 2))
        self.backdate_all_history()
        term.end_date = datetime.date(2026, 12, 1)
        term.save()

        body = self.draft()

        self.assertIn("Pat Commissioner</a>'s term now ends 2026-12-01 (was 2027-01-02).", body)
        # The number of terms didn't change, so there's no Old/Diff/New table.
        self.assertNotIn('<table>', body)

    def test_term_edit_that_keeps_the_end_date_is_not_reported(self):
        term = make_commissioner_term(self.person, self.district)
        self.backdate_all_history()
        term.start_date_is_approximate = True
        term.save()
        self.assertIsNone(self.draft())

    def test_removed_term_is_reported(self):
        term = make_commissioner_term(self.person, self.district)
        self.backdate_all_history()
        term.delete()
        self.assertIn("Pat Commissioner</a>'s commissioner term record was removed.", self.draft())

    def test_records_whose_person_was_since_deleted_are_skipped(self):
        make_commissioner_term(self.person, self.district)
        make_candidate(self.person, make_election(year=2026), self.district)
        self.person.delete()
        body = self.draft()
        self.assertIsNone(body)

    def test_candidate_status_change_is_reported_and_other_edits_are_not(self):
        candidate = make_candidate(self.person, make_election(year=2026), self.district)
        self.backdate_all_history()
        candidate.save()
        self.assertIsNone(self.draft())

        candidate.status = make_candidate_status(name='Withdrew')
        candidate.save()
        self.assertIn("Pat Commissioner</a>'s candidate status changed to Withdrew (election year 2026).", self.draft())

    def test_write_in_winners_link_the_person_or_show_the_raw_name(self):
        election = make_election(year=2026)
        other = make_district(designator='1A02', anc=self.district.anc, ward=self.district.ward)
        WriteInWinner.objects.create(election=election, district=self.district, person=self.person, candidate_name_raw='Pat C')
        WriteInWinner.objects.create(election=election, district=other, candidate_name_raw='Unlinked <Name>')

        body = self.draft()

        self.assertIn('<strong>Write-in winners certified</strong>', body)
        self.assertIn(f'<a href="{self.person.get_absolute_url()}">Pat Commissioner</a> certified as write-in winner', body)
        self.assertIn('Unlinked &lt;Name&gt; certified as write-in winner (election year 2026).', body)


class BackfillPersonAliasSourcesTests(TestCase):
    """The non-DCBOE-list alias sources, plus the DCBOE file filtering rules."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.district = make_district(designator='1A01')
        self.person = make_person(full_name='Zachary Adams')

    def write(self, filename, content):
        with open(f'{self._tmp.name}/{filename}', 'w') as f:
            f.write(content)

    def run_command(self, *args):
        out = io.StringIO()
        call_command('backfill_person_aliases', '--dcboe-dir', self._tmp.name, *args, stdout=out)
        return out.getvalue()

    def test_applied_import_rows_become_import_aliases(self):
        from directory.models import PersonImportBatch, PersonImportRow
        batch = PersonImportBatch.objects.create(source_label='ballot filings')
        PersonImportRow.objects.create(batch=batch, raw_name='Zack Adams', chosen_person=self.person, applied=True)
        PersonImportRow.objects.create(batch=batch, raw_name='Not Applied', chosen_person=self.person, applied=False)

        self.run_command('--apply')

        alias = self.person.aliases.get(name='Zack Adams')
        self.assertEqual(alias.source, 'import')
        self.assertEqual(alias.note, f'Import batch #{batch.pk}: ballot filings')
        self.assertFalse(self.person.aliases.filter(name='Not Applied').exists())

    def test_linked_election_results_become_results_aliases(self):
        from directory.models import ElectionResult
        election = make_election(year=2024)
        candidate = make_candidate(self.person, election, self.district)
        ElectionResult.objects.create(election=election, district=self.district, candidate=candidate,
                                      candidate_name_raw='ZACHARY R ADAMS', votes=10)

        self.run_command('--apply')

        alias = self.person.aliases.get(name='ZACHARY R ADAMS')
        self.assertEqual(alias.source, 'dcboe_results')
        self.assertEqual(alias.note, '2024 results, SMD 1A01')

    def test_rejected_oanc_spelling_note_adds_an_alias_for_the_districts_commissioner(self):
        from directory.models import Suggestion
        make_commissioner_term(self.person, self.district)
        note = Suggestion.objects.create(
            name='OANC comparison', status=Suggestion.STATUS_REJECTED, district=self.district,
            message='OANC spells the commissioner\'s name "Zachary  Adáms", OpenANC has "Zachary Adams".',
        )
        Suggestion.objects.create(name='OANC comparison', status=Suggestion.STATUS_REJECTED,
                                  district=self.district, message='Some other note')

        self.run_command('--apply')

        alias = self.person.aliases.get(name='Zachary  Adáms')
        self.assertEqual(alias.source, 'oanc')
        self.assertEqual(alias.note, f'Rejected suggestion #{note.pk}')

    def test_oanc_spelling_without_a_unique_commissioner_is_left_for_review(self):
        from directory.models import Suggestion
        note = Suggestion.objects.create(
            name='OANC comparison', status=Suggestion.STATUS_REJECTED, district=self.district,
            message='OANC spells the commissioner\'s name "Zach Adams", OpenANC has "Zachary Adams".',
        )
        output = self.run_command()
        self.assertIn(f'Suggestion #{note.pk}: OANC "Zach Adams" / ours "Zachary Adams"', output)

    def test_dcboe_lists_skip_other_years_blank_and_repeated_rows(self):
        make_candidate(self.person, make_election(year=2026), self.district)
        self.write('dcboe-ballot-2024-10-01.csv', 'ANC-SMD,Name\n1A01,Old Year Spelling\n')
        self.write('dcboe-write-in-2026-11-05.csv',
                   'Office,Name\n1A01,Zach  Adams\n1A01,Zach Adams\n,No District\n1A01,\n')

        output = self.run_command('--apply')

        alias = self.person.aliases.get(name='Zach Adams')
        self.assertEqual(alias.source, 'dcboe_write_in')
        self.assertFalse(self.person.aliases.filter(name='Old Year Spelling').exists())
        self.assertNotIn('No District', output)

    def test_dcboe_name_in_a_district_with_no_candidates_is_unresolved(self):
        self.write('dcboe-ballot-2026-10-13.csv', 'ANC-SMD,Name\n9Z99,Someone Else\n')
        output = self.run_command()
        self.assertIn('"Someone Else" in 9Z99 -- no 2026 candidates there', output)

    def test_names_that_normalize_to_nothing_are_ignored(self):
        self.person.aliases.all().delete()
        make_person(full_name='...')
        output = self.run_command()
        self.assertIn('Would add 1 alias(es): 1 openanc.', output)
