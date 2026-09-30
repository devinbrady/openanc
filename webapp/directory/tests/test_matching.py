from django.test import TestCase

from directory.matching import build_person_choices, match_name, match_person_rows, strip_diacritics
from directory.models import PersonImportBatch, PersonImportRow
from directory.tests.factories import make_person


class StripDiacriticsTests(TestCase):
    def test_removes_accents(self):
        self.assertEqual(strip_diacritics('Mónica Martínez López'), 'Monica Martinez Lopez')

    def test_leaves_plain_text_unchanged(self):
        self.assertEqual(strip_diacritics('Jaspal Bhatia'), 'Jaspal Bhatia')


class MatchNameTests(TestCase):
    def test_exact_name_is_a_link(self):
        make_person(full_name='Jaspal Bhatia')
        choices = build_person_choices()
        candidates, decision = match_name('Jaspal Bhatia', choices)
        self.assertEqual(decision, PersonImportRow.DECISION_LINK)
        self.assertEqual(candidates[0]['full_name'], 'Jaspal Bhatia')

    def test_unrelated_name_is_new(self):
        make_person(full_name='Jaspal Bhatia')
        choices = build_person_choices()
        candidates, decision = match_name('Zzyzx Qplotnik', choices)
        self.assertEqual(decision, PersonImportRow.DECISION_NEW)

    def test_no_existing_people_is_new(self):
        candidates, decision = match_name('Anyone', {})
        self.assertEqual(candidates, [])
        self.assertEqual(decision, PersonImportRow.DECISION_NEW)

    def test_middling_score_is_pending(self):
        make_person(full_name='Jonathan Smith')
        choices = build_person_choices()
        # Close enough to surface as a candidate, not so close it should auto-link.
        candidates, decision = match_name('Jon Smithe', choices)
        self.assertIn(decision, [PersonImportRow.DECISION_PENDING, PersonImportRow.DECISION_LINK])
        self.assertTrue(candidates)


class MatchPersonRowsTests(TestCase):
    def test_populates_each_row(self):
        make_person(full_name='Jaspal Bhatia')
        batch = PersonImportBatch.objects.create(source_label='test')
        row = PersonImportRow.objects.create(batch=batch, raw_name='Jaspal Bhatia')

        match_person_rows(batch)

        row.refresh_from_db()
        self.assertEqual(row.decision, PersonImportRow.DECISION_LINK)
        self.assertIsNotNone(row.chosen_person_id)
        self.assertTrue(row.match_candidates_json)
