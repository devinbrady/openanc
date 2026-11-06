"""Small model properties, __str__ labels (what the admin and history show), boundary lookups,
and template filters that the page-level tests don't reach on their own."""
import datetime

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from directory.boundaries import boundary_geometry
from directory.models import (
    ElectionResult, MapColor, PersonImportBatch, PersonImportRow, PersonSlugRedirect, SiteUpdate, WriteInWinner,
)
from directory.templatetags.directory_extras import strip_diacritics
from directory.tests.factories import (
    make_candidate, make_commissioner_term, make_district, make_election, make_person,
)

D = datetime.date


class StrLabelTests(TestCase):
    def setUp(self):
        self.district = make_district(designator='1A01')
        self.election = make_election(year=2026)
        self.person = make_person(full_name='Jane Doe')

    def test_simple_labels(self):
        self.assertEqual(str(self.district.ward), 'Ward 1 (2022)')
        self.assertEqual(self.district.anc.name, 'ANC 1A')
        self.assertEqual(str(MapColor(hex_code='#abcdef')), '#abcdef')
        self.assertEqual(str(PersonSlugRedirect(slug='old-slug', person=self.person)), 'old-slug -> Jane Doe')
        self.assertEqual(str(SiteUpdate(date=D(2026, 11, 6))), 'Update on 2026-11-06')

    def test_candidate_and_result_labels(self):
        candidate = make_candidate(self.person, self.election, self.district)
        self.assertEqual(str(candidate), f'Jane Doe — {self.district} (2026)')

        common = dict(election=self.election, district=self.district, votes=12)
        linked = str(ElectionResult(candidate=candidate, **common))
        self.assertTrue(linked.startswith('Jane Doe — ') and linked.endswith(': 12 votes'), linked)
        self.assertEqual(str(ElectionResult(candidate_name_raw='RAW NAME', **common)), f'RAW NAME — {self.district} (2026): 12 votes')
        self.assertEqual(str(ElectionResult(**common)), f'Write-ins combined — {self.district} (2026): 12 votes')

    def test_write_in_and_import_row_labels(self):
        winner = WriteInWinner(election=self.election, district=self.district, candidate_name_raw='Pat W')
        self.assertEqual(str(winner), f'Pat W — {self.district} (2026)')
        row = PersonImportRow(batch=PersonImportBatch(), raw_name='Pat W', decision=PersonImportRow.DECISION_SKIP)
        self.assertEqual(str(row), f'Pat W ({row.get_decision_display()})')


class TermAndElectionPropertyTests(TestCase):
    def setUp(self):
        self.district = make_district()
        self.person = make_person()

    def test_future_commissioner_term(self):
        today = timezone.localdate()
        self.assertIsNone(self.district.future_commissioner_term)
        later = make_commissioner_term(self.person, self.district, start_date=today + datetime.timedelta(days=30))
        make_commissioner_term(make_person(full_name='Even Later'), self.district,
                               start_date=today + datetime.timedelta(days=90))
        self.assertEqual(self.district.future_commissioner_term, later)

    def test_term_label_and_covers_date(self):
        term = make_commissioner_term(self.person, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        self.assertEqual(term.term_label, 'January 2, 2023 to January 2, 2025')
        term.start_date_is_approximate = True
        self.assertEqual(term.term_label, '~2023 to January 2, 2025')
        self.assertTrue(term.covers_date(D(2024, 6, 1)))
        self.assertFalse(term.covers_date(D(2025, 1, 3)))

    def test_petition_window(self):
        election = make_election()
        self.assertFalse(election.is_petition_window_open)
        today = timezone.localdate()
        election.petition_open_date = today - datetime.timedelta(days=1)
        election.petition_close_date = today + datetime.timedelta(days=1)
        self.assertTrue(election.is_petition_window_open)
        election.petition_close_date = today - datetime.timedelta(days=1)
        self.assertFalse(election.is_petition_window_open)

    def test_is_incumbent(self):
        election = make_election(year=2026)
        candidate = make_candidate(self.person, election, self.district)
        self.assertFalse(candidate.is_incumbent)  # no election date recorded

        election.election_date = D(2026, 11, 3)
        election.save()
        candidate.refresh_from_db()
        self.assertFalse(candidate.is_incumbent)

        make_commissioner_term(self.person, self.district, start_date=D(2025, 1, 2), end_date=D(2027, 1, 2))
        self.assertTrue(candidate.is_incumbent)


class BoundaryGeometryTests(SimpleTestCase):
    def test_known_boundaries_load(self):
        for kind, designator in [('anc', '1A'), ('ward', 1), ('district', '1A01')]:
            for year in (2012, 2022):
                with self.subTest(kind=kind, year=year):
                    self.assertIsNotNone(boundary_geometry(kind, designator, year))

    def test_2012_ward_3_4_anc_uses_source_file_name(self):
        self.assertIsNotNone(boundary_geometry('anc', '3/4G', 2012))
        self.assertEqual(boundary_geometry('anc', '3/4G', 2012), boundary_geometry('anc', '3G', 2012))

    def test_unknown_year_or_designator_returns_none(self):
        self.assertIsNone(boundary_geometry('anc', '1A', 1999))
        self.assertIsNone(boundary_geometry('district', '9Z99', 2022))


class StripDiacriticsFilterTests(SimpleTestCase):
    def test_strips_accents(self):
        self.assertEqual(strip_diacritics('Mónica Martínez López'), 'Monica Martinez Lopez')
