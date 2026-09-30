import csv
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.test import TestCase

from directory.management.commands.check_oanc_commissioners import Command
from directory.models import Suggestion
from directory.tests.factories import make_anc, make_commissioner_term, make_district, make_person, make_ward

# A minimal page in the same shape as the real OANC site: a header row rendered as a plain <tr>
# (as ANC 5F's real page does) rather than inside <thead>, one seat with an officer title
# appended on its own line, one seat marked vacant, one where the site has wrapped part of
# an accented name in its own <span> (a real, observed quirk -- see _extract_name's docstring),
# and two vacant seats where OANC itself wraps "Vacant" in an <em> -- with and without a title
# (a real, observed quirk on ANC 1E's and ANC 2E's pages respectively).
SAMPLE_HTML = """
<table class="uk-table">
<tbody>
<tr><td><strong>SMD</strong></td><td><strong>Name</strong></td></tr>
<tr><td>1A01</td><td><div>Jaspal Bhatia</div><div><em>Treasurer</em></div></td></tr>
<tr><td>1A02</td><td>Vacant</td></tr>
<tr><td>1A03</td><td><div>M<span>ónica Martínez Ló</span>pez</div></td></tr>
<tr><td>1A04</td><td><div><em>Vacant</em></div></td></tr>
<tr><td>1A05</td><td><div><em>Vacant</em></div><div><em>Secretary</em></div></td></tr>
</tbody>
</table>
"""


def mock_response(html):
    response = Mock()
    response.text = html
    response.raise_for_status = Mock()
    return response


class FetchOfficialRosterTests(TestCase):
    def test_parses_name_title_and_vacant_rows_and_skips_header_row(self):
        command = Command()
        anc = make_anc(dc_oanc_link='https://oanc.dc.gov/anc-profile/anc-1a')
        with patch('directory.management.commands.check_oanc_commissioners.requests.get', return_value=mock_response(SAMPLE_HTML)):
            rows = command._fetch_official_roster(anc)
        self.assertEqual(rows, [
            {'smd_text': '1A01', 'raw_text': 'Jaspal BhatiaTreasurer', 'oanc_name': 'Jaspal Bhatia'},
            {'smd_text': '1A02', 'raw_text': 'Vacant', 'oanc_name': None},
            {'smd_text': '1A03', 'raw_text': 'Mónica Martínez López', 'oanc_name': 'Mónica Martínez López'},
            {'smd_text': '1A04', 'raw_text': 'Vacant', 'oanc_name': None},
            {'smd_text': '1A05', 'raw_text': 'VacantSecretary', 'oanc_name': None},
        ])


class ExtractNameTests(TestCase):
    """Regression coverage for a real bug: a name with an accented character split across a
    <span> the site wraps around it was truncated down to just its first letter."""

    def _cell(self, html):
        return BeautifulSoup(f'<td>{html}</td>', 'lxml').find('td')

    def test_plain_name(self):
        command = Command()
        self.assertEqual(command._extract_name(self._cell('Jaspal Bhatia')), 'Jaspal Bhatia')

    def test_name_with_title_in_em_tag(self):
        command = Command()
        cell = self._cell('<div>Jaspal Bhatia</div><div><em>Treasurer</em></div>')
        self.assertEqual(command._extract_name(cell), 'Jaspal Bhatia')

    def test_name_with_accented_letters_split_across_a_span(self):
        command = Command()
        cell = self._cell('<div>M<span>ónica Martínez Ló</span>pez</div>')
        self.assertEqual(command._extract_name(cell), 'Mónica Martínez López')

    def test_name_with_accented_letters_and_a_title(self):
        command = Command()
        cell = self._cell('<div>Fran<span>çois</span> Dupont</div><div><em>Secretary</em></div>')
        self.assertEqual(command._extract_name(cell), 'François Dupont')


class ClassifyTests(TestCase):
    def setUp(self):
        self.anc = make_anc()
        self.ward = make_ward()
        self.district = make_district(anc=self.anc, ward=self.ward)
        self.command = Command()

    def test_both_vacant_is_not_a_mismatch(self):
        self.assertEqual(self.command._classify(self.district, None), [])

    def test_official_has_name_we_are_vacant_is_new_commissioner(self):
        [(suggestion_type, message, structured_data)] = self.command._classify(self.district, 'Jaspal Bhatia')
        self.assertEqual(suggestion_type, Suggestion.TYPE_NEW_COMMISSIONER)
        self.assertIn('Jaspal Bhatia', message)
        self.assertEqual(structured_data, {'district_id': self.district.id, 'person_name': 'Jaspal Bhatia'})

    def test_official_vacant_we_have_commissioner_is_commissioner_change(self):
        make_commissioner_term(make_person(full_name='Jaspal Bhatia'), self.district)
        [(suggestion_type, message, structured_data)] = self.command._classify(self.district, None)
        self.assertEqual(suggestion_type, Suggestion.TYPE_COMMISSIONER_CHANGE)
        self.assertIn('Jaspal Bhatia', message)
        self.assertEqual(structured_data, {'district_id': self.district.id})

    def test_close_name_match_is_not_a_mismatch(self):
        make_commissioner_term(make_person(full_name='Trupti "Trip" J. Patel'), self.district)
        self.assertEqual(self.command._classify(self.district, 'Trupti "Trip" Patel'), [])

    def test_exact_name_match_is_not_a_mismatch(self):
        make_commissioner_term(make_person(full_name='Jaspal Bhatia'), self.district)
        self.assertEqual(self.command._classify(self.district, 'Jaspal Bhatia'), [])

    def test_accent_only_difference_is_surfaced_as_a_general_suggestion_not_a_personnel_change(self):
        """A name that only differs in accented characters is the same person -- not a
        resignation-and-appointment -- but should still be surfaced, since whether to display
        the accents is an editorial call, not something to silently ignore."""
        make_commissioner_term(make_person(full_name='Monica Martinez Lopez'), self.district)
        mismatches = self.command._classify(self.district, 'Mónica Martínez López')
        self.assertEqual(len(mismatches), 1)
        suggestion_type, message, structured_data = mismatches[0]
        self.assertEqual(suggestion_type, Suggestion.TYPE_GENERAL)
        self.assertIn('Mónica Martínez López', message)
        self.assertIn('Monica Martinez Lopez', message)
        self.assertEqual(structured_data, {})

    def test_very_different_names_produce_both_a_change_and_a_new_commissioner_suggestion(self):
        make_commissioner_term(make_person(full_name='Someone Else Entirely'), self.district)
        mismatches = self.command._classify(self.district, 'Jaspal Bhatia')
        self.assertEqual(len(mismatches), 2)

        change_type, change_message, change_data = mismatches[0]
        self.assertEqual(change_type, Suggestion.TYPE_COMMISSIONER_CHANGE)
        self.assertIn('Someone Else Entirely', change_message)
        self.assertEqual(change_data, {'district_id': self.district.id})

        new_type, new_message, new_data = mismatches[1]
        self.assertEqual(new_type, Suggestion.TYPE_NEW_COMMISSIONER)
        self.assertIn('Jaspal Bhatia', new_message)
        self.assertEqual(new_data, {'district_id': self.district.id, 'person_name': 'Jaspal Bhatia'})


class CommandIntegrationTests(TestCase):
    """Every call passes --csv-dir pointing at a throwaway temp directory -- never the real
    data/oanc/, which is only for real runs against the live site."""

    def setUp(self):
        self.anc = make_anc(designator='1A', dc_oanc_link='https://oanc.dc.gov/anc-profile/anc-1a')
        self.ward = make_ward()
        # Vacant in our data; the sample page shows a real name for this seat.
        self.district = make_district(designator='1A01', anc=self.anc, ward=self.ward)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.csv_dir = self._tmpdir.name

    def _run(self, *extra_args):
        with patch('directory.management.commands.check_oanc_commissioners.requests.get', return_value=mock_response(SAMPLE_HTML)) as mocked_get:
            call_command('check_oanc_commissioners', '--csv-dir', self.csv_dir, *extra_args)
        return mocked_get

    def test_creates_suggestion_for_mismatch(self):
        self._run()

        suggestion = Suggestion.objects.get(district=self.district)
        self.assertEqual(suggestion.suggestion_type, Suggestion.TYPE_NEW_COMMISSIONER)
        self.assertEqual(suggestion.status, Suggestion.STATUS_PENDING)
        self.assertEqual(suggestion.name, 'OANC comparison')
        self.assertEqual(suggestion.structured_data, {'district_id': self.district.id, 'person_name': 'Jaspal Bhatia'})

    def test_creates_general_suggestion_for_accent_only_difference(self):
        """Regression test: this end-to-end run is what caught a KeyError the unit tests on
        _classify alone didn't -- created_counts needs an entry for every type _classify can
        return, including TYPE_GENERAL for the accent-difference case."""
        accented_district = make_district(designator='1A03', anc=self.anc, ward=self.ward)
        make_commissioner_term(make_person(full_name='Monica Martinez Lopez'), accented_district)

        self._run()

        suggestion = Suggestion.objects.get(district=accented_district)
        self.assertEqual(suggestion.suggestion_type, Suggestion.TYPE_GENERAL)
        self.assertIn('Mónica Martínez López', suggestion.message)

    def test_em_wrapped_vacant_with_title_is_treated_as_vacant_not_a_blank_name(self):
        """Regression test for a real bug: OANC sometimes wraps "Vacant" itself in an <em> (SMD
        1A05 in SAMPLE_HTML, same markup as a real officer title), which used to make
        _extract_name strip it away to an empty string -- read as a real (blank) name rather
        than a vacancy, producing a nonsensical "Office of ANCs lists  as the commissioner"
        suggestion instead of correctly flagging that our side still shows a sitting commissioner."""
        district = make_district(designator='1A05', anc=self.anc, ward=self.ward)
        make_commissioner_term(make_person(full_name='Someone Currently Serving'), district)

        self._run()

        suggestion = Suggestion.objects.get(district=district)
        self.assertEqual(suggestion.suggestion_type, Suggestion.TYPE_COMMISSIONER_CHANGE)
        self.assertEqual(suggestion.structured_data, {'district_id': district.id})
        self.assertIn('Someone Currently Serving', suggestion.message)

    def test_dry_run_creates_nothing(self):
        self._run('--dry-run')
        self.assertEqual(Suggestion.objects.count(), 0)

    def test_dry_run_does_not_write_csv_cache(self):
        self._run('--dry-run')
        self.assertEqual(list(Path(self.csv_dir).iterdir()), [])

    def test_rerunning_does_not_create_a_duplicate_pending_suggestion(self):
        self._run()
        self._run()
        self.assertEqual(Suggestion.objects.filter(district=self.district).count(), 1)

    def test_rerunning_does_not_duplicate_an_approved_but_not_yet_applied_suggestion(self):
        """Regression test: a moderator can approve a suggestion well before getting around to
        running "Apply selected suggestions" on it. A same-day re-run used to only check for
        *pending* suggestions, so it would see the still-live mismatch (the CommissionerTerm
        the approved suggestion will eventually create doesn't exist yet) and create a second,
        identical suggestion -- which, once the first was applied, could only ever fail to
        apply itself with an overlapping-commissioner-term error."""
        self._run()
        suggestion = Suggestion.objects.get(district=self.district)
        suggestion.status = Suggestion.STATUS_APPROVED
        suggestion.save()

        self._run()

        self.assertEqual(Suggestion.objects.filter(district=self.district).count(), 1)

    def test_rerunning_does_not_recreate_a_rejected_suggestion(self):
        self._run()
        Suggestion.objects.filter(district=self.district).update(status=Suggestion.STATUS_REJECTED)

        self._run()

        self.assertEqual(Suggestion.objects.filter(district=self.district).count(), 1)

    def test_rejected_suggestion_for_a_different_name_does_not_suppress_a_new_one(self):
        self._run()
        Suggestion.objects.filter(district=self.district).update(
            status=Suggestion.STATUS_REJECTED, message='Someone Else appears to now be serving 1A01.',
        )

        self._run()

        self.assertEqual(Suggestion.objects.filter(district=self.district).count(), 2)

    def test_anc_filter_only_compares_the_named_anc(self):
        other_anc = make_anc(designator='1B', dc_oanc_link='https://oanc.dc.gov/anc-profile/anc-1b')
        make_district(designator='1B01', anc=other_anc, ward=self.ward)

        self._run('--anc', '1A')

        self.assertTrue(Suggestion.objects.filter(district=self.district).exists())
        self.assertFalse(Suggestion.objects.filter(district__anc=other_anc).exists())

    def test_first_run_writes_a_cache_file_and_second_run_skips_the_network(self):
        first_get = self._run()
        self.assertTrue(first_get.called)

        cache_files = list(Path(self.csv_dir).glob('commissioners_*.csv'))
        self.assertEqual(len(cache_files), 1)

        second_get = self._run()
        self.assertFalse(second_get.called)

    def test_force_refresh_rescrapes_even_if_cache_exists(self):
        self._run()
        second_get = self._run('--force-refresh')
        self.assertTrue(second_get.called)

    def test_cached_csv_matches_the_legacy_column_format(self):
        self._run()
        [cache_file] = Path(self.csv_dir).glob('commissioners_*.csv')
        with open(cache_file, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(list(rows[0].keys()), ['smd_id', 'Name', 'oanc_name', 'is_vacant', 'is_chairperson', 'oanc_hash_id'])
        row = next(r for r in rows if r['smd_id'] == f'smd_{self.district.redistricting_year}_{self.district.designator}')
        self.assertEqual(row['Name'], 'Jaspal BhatiaTreasurer')
        self.assertEqual(row['oanc_name'], 'Jaspal Bhatia')
        self.assertEqual(row['is_vacant'], 'False')
        self.assertEqual(row['is_chairperson'], 'False')
        self.assertEqual(len(row['oanc_hash_id']), 56)  # sha224 hexdigest

    def test_second_run_reproduces_the_same_suggestion_from_the_cache_alone(self):
        self._run()
        Suggestion.objects.all().delete()
        self._run()  # second run: reads the cache, no network call
        self.assertTrue(Suggestion.objects.filter(district=self.district).exists())
