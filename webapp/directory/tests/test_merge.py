import datetime

from django.contrib.auth.models import User
from django.core import serializers
from django.test import TestCase
from django.urls import reverse

from directory.merge import MergeError, merge_people, plan_merge, undo_merge
from directory.models import (
    Candidate, CommissionerTerm, ElectionResult, Person, PersonAlias, PersonImportBatch, PersonImportRow,
    PersonLink, PersonMerge, PersonSlugRedirect, Suggestion, WriteInWinner,
)
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import (
    make_anc, make_candidate, make_candidate_status, make_commissioner_term, make_district, make_election,
    make_person, make_ward,
)

D = datetime.date


def snapshot():
    """Every row a merge can touch, as comparable data -- for checking undo restores exactly."""
    models = [Person, PersonAlias, PersonLink, CommissionerTerm, Candidate, ElectionResult, Suggestion,
              WriteInWinner, PersonImportRow, PersonSlugRedirect]
    data = {}
    for model in models:
        rows = serializers.serialize('python', model.objects.order_by('pk'))
        for row in rows:
            for volatile in ('modified_at',):
                row['fields'].pop(volatile, None)
        data[model.__name__] = rows
    return data


class MergeTestBase(TestCase):
    def setUp(self):
        self.ward = make_ward(number=4)
        self.anc = make_anc(designator='4B')
        self.district = make_district(designator='4B05', anc=self.anc, ward=self.ward)
        self.status = make_candidate_status()
        self.e2024 = make_election(year=2024)
        self.e2026 = make_election(year=2026)
        self.kept = make_person(full_name='Jose Barrios')
        self.removed = make_person(full_name='Jose (Joe) L. Barrios Jr.')


class PlanAndMergeTests(MergeTestBase):
    def test_moves_everything_and_redirects_old_slug(self):
        kept_c = make_candidate(self.kept, self.e2026, self.district, status=self.status)
        removed_c = make_candidate(self.removed, self.e2024, self.district, status=self.status)
        ElectionResult.objects.create(election=self.e2024, district=self.district, candidate=removed_c,
                                      candidate_name_raw='Jose Barrios', votes=10, ranking=1)
        term = make_commissioner_term(self.removed, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        self.removed.links.create(url='https://joe.example/')
        self.removed.aliases.create(name='Joe Barrios', source='manual')
        suggestion = Suggestion.objects.create(message='x', person=self.removed, resulting_person=self.removed)
        wiw = WriteInWinner.objects.create(election=self.e2024, district=self.district, person=self.removed,
                                           candidate_name_raw='Joe Barrios')
        batch = PersonImportBatch.objects.create(source_label='t')
        import_row = PersonImportRow.objects.create(batch=batch, raw_name='Joe', chosen_person=self.removed)
        old_slug, removed_pk = self.removed.slug, self.removed.pk

        merge = merge_people(self.kept, self.removed)

        self.assertFalse(Person.objects.filter(pk=removed_pk).exists())
        removed_c.refresh_from_db(); term.refresh_from_db(); suggestion.refresh_from_db(); wiw.refresh_from_db()
        import_row.refresh_from_db()
        self.assertEqual(removed_c.person, self.kept)
        self.assertEqual(kept_c.person, self.kept)
        self.assertEqual(term.person, self.kept)
        self.assertEqual((suggestion.person, suggestion.resulting_person), (self.kept, self.kept))
        self.assertEqual(wiw.person, self.kept)
        self.assertEqual(import_row.chosen_person, self.kept)
        self.assertEqual(set(self.kept.aliases.values_list('name', flat=True)),
                         {'Jose Barrios', 'Jose (Joe) L. Barrios Jr.', 'Joe Barrios'})
        self.assertTrue(self.kept.links.filter(url='https://joe.example/').exists())
        self.assertEqual(PersonSlugRedirect.objects.get(slug=old_slug).person, self.kept)
        self.assertEqual(merge.removed_person_id, removed_pk)
        self.kept.refresh_from_db()
        self.assertEqual(self.kept.full_name, 'Jose Barrios')

    def test_same_election_same_district_moves_results_to_chosen_row(self):
        kept_c = make_candidate(self.kept, self.e2026, self.district, status=self.status, source='import')
        removed_c = make_candidate(self.removed, self.e2026, self.district, status=self.status, source='suggestion')
        result = ElectionResult.objects.create(election=self.e2026, district=self.district, candidate=kept_c,
                                               candidate_name_raw='Jose Barrios', votes=99, ranking=1)
        plan = plan_merge(self.kept, self.removed)
        self.assertTrue(plan.can_merge)
        self.assertEqual(len(plan.candidacy_conflicts), 1)

        merge_people(self.kept, self.removed, keep_candidacy={self.e2026.pk: removed_c.pk})

        self.assertFalse(Candidate.objects.filter(pk=kept_c.pk).exists())
        removed_c.refresh_from_db(); result.refresh_from_db()
        self.assertEqual(removed_c.person, self.kept)
        self.assertEqual(result.candidate, removed_c)

    def test_same_election_different_districts_is_blocked(self):
        other = make_district(designator='4B06', anc=self.anc, ward=self.ward)
        make_candidate(self.kept, self.e2026, self.district, status=self.status)
        make_candidate(self.removed, self.e2026, other, status=self.status)
        self.assertFalse(plan_merge(self.kept, self.removed).can_merge)
        with self.assertRaises(MergeError):
            merge_people(self.kept, self.removed)
        self.assertTrue(Person.objects.filter(pk=self.removed.pk).exists())

    def test_identical_term_is_dropped_but_overlapping_term_blocks(self):
        make_commissioner_term(self.kept, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        dup = make_commissioner_term(self.removed, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        plan = plan_merge(self.kept, self.removed)
        self.assertEqual(plan.duplicate_terms, [dup])
        self.assertTrue(plan.can_merge)

        elsewhere = make_district(designator='7B01', anc=make_anc(designator='7B'), ward=make_ward(number=7))
        CommissionerTerm.objects.create(person=self.removed, district=elsewhere, start_date=D(2024, 1, 2), end_date=D(2025, 6, 1))
        self.assertFalse(plan_merge(self.kept, self.removed).can_merge)

    def test_handoff_on_the_same_day_is_not_an_overlap(self):
        make_commissioner_term(self.kept, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        make_commissioner_term(self.removed, self.district, start_date=D(2025, 1, 2), end_date=D(2027, 1, 2))
        self.assertTrue(plan_merge(self.kept, self.removed).can_merge)

    def test_duplicate_link_and_alias_are_dropped(self):
        self.kept.links.create(url='https://same.example/')
        self.removed.links.create(url='https://same.example/')
        self.kept.aliases.create(name='Joe Barrios', source='manual')
        self.removed.aliases.create(name='Joe Barrios', source='dcboe_ballot')
        merge_people(self.kept, self.removed)
        self.assertEqual(self.kept.links.filter(url='https://same.example/').count(), 1)
        self.assertEqual(self.kept.aliases.filter(name='Joe Barrios').count(), 1)

    def test_cannot_merge_person_into_themselves(self):
        self.assertFalse(plan_merge(self.kept, self.kept).can_merge)

    def test_accented_display_name_of_kept_person_survives(self):
        kept = make_person(full_name='Erika Núñez')
        dup = make_person(full_name='Erika Nunez')
        merge_people(kept, dup)
        kept.refresh_from_db()
        self.assertEqual(kept.full_name, 'Erika Núñez')
        self.assertTrue(kept.aliases.filter(name='Erika Nunez').exists())


class UndoMergeTests(MergeTestBase):
    def build_graph(self):
        kept_c = make_candidate(self.kept, self.e2026, self.district, status=self.status)
        removed_c = make_candidate(self.removed, self.e2026, self.district, status=self.status)
        old_c = make_candidate(self.removed, self.e2024, self.district, status=self.status)
        ElectionResult.objects.create(election=self.e2026, district=self.district, candidate=removed_c,
                                      candidate_name_raw='Jose Barrios', votes=5, ranking=1)
        ElectionResult.objects.create(election=self.e2024, district=self.district, candidate=old_c,
                                      candidate_name_raw='Joe Barrios', votes=7, ranking=1)
        make_commissioner_term(self.kept, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        make_commissioner_term(self.removed, self.district, start_date=D(2023, 1, 2), end_date=D(2025, 1, 2))
        self.kept.links.create(url='https://same.example/')
        self.removed.links.create(url='https://same.example/')
        self.removed.links.create(url='https://only-removed.example/')
        self.removed.aliases.create(name='Joe Barrios', source='manual')
        Suggestion.objects.create(message='x', person=self.removed, candidate=removed_c)
        PersonSlugRedirect.objects.create(slug='older-merged-away', person=self.removed)
        return kept_c, removed_c

    def test_undo_restores_everything_exactly(self):
        kept_c, removed_c = self.build_graph()
        removed_pk = self.removed.pk
        before = snapshot()

        merge = merge_people(self.kept, self.removed, keep_candidacy={self.e2026.pk: kept_c.pk})
        self.assertNotEqual(snapshot(), before)
        restored = undo_merge(merge)

        self.assertEqual(restored.pk, removed_pk)
        self.assertEqual(snapshot(), before)
        merge.refresh_from_db()
        self.assertIsNotNone(merge.undone_at)

    def test_undo_when_removed_persons_candidacy_was_kept(self):
        kept_c, removed_c = self.build_graph()
        before = snapshot()
        merge = merge_people(self.kept, self.removed, keep_candidacy={self.e2026.pk: removed_c.pk})
        undo_merge(merge)
        self.assertEqual(snapshot(), before)

    def test_cannot_undo_twice(self):
        merge = merge_people(self.kept, self.removed)
        undo_merge(merge)
        with self.assertRaises(MergeError):
            undo_merge(merge)


class MergeAdminTests(PageRenderingTestCase):
    def setUp(self):
        staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        district = make_district()
        self.kept = make_person(full_name='Robbie Woodland')
        self.removed = make_person(full_name='Robbie "The Advocate" Woodland')
        make_commissioner_term(self.kept, district)

    def test_changelist_action_goes_to_preview(self):
        response = self.client.post(reverse('admin:directory_person_changelist'), {
            'action': 'merge_people', '_selected_action': [self.kept.pk, self.removed.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:directory_person_merge'), response['Location'])

    def test_preview_defaults_to_keeping_the_record_with_history(self):
        url = f"{reverse('admin:directory_person_merge')}?ids={self.removed.pk},{self.kept.pk}"
        response = self.client.get(url)
        self.assertContains(response, f'Merge Robbie &quot;The Advocate&quot; Woodland into Robbie Woodland')
        self.assertFalse(PersonMerge.objects.exists())

    def test_post_merges_and_undo_action_restores(self):
        url = reverse('admin:directory_person_merge')
        response = self.client.post(url, {'ids': f'{self.kept.pk},{self.removed.pk}', 'keep': self.kept.pk})
        self.assertRedirects(response, reverse('admin:directory_person_change', args=[self.kept.pk]))
        merge = PersonMerge.objects.get()
        self.assertFalse(Person.objects.filter(pk=self.removed.pk).exists())

        self.client.post(reverse('admin:directory_personmerge_changelist'), {
            'action': 'undo_merges', '_selected_action': [merge.pk],
        })
        self.assertTrue(Person.objects.filter(pk=self.removed.pk).exists())

    def test_merge_list_and_detail_render(self):
        merge = merge_people(self.kept, self.removed)
        self.assertEqual(self.client.get(reverse('admin:directory_personmerge_changelist')).status_code, 200)
        response = self.client.get(reverse('admin:directory_personmerge_change', args=[merge.pk]))
        self.assertContains(response, 'moved')


class OldPersonUrlTests(PageRenderingTestCase):
    def test_merged_away_slug_redirects_permanently(self):
        district = make_district()
        kept = make_person(full_name='Takiyah Tate')
        make_commissioner_term(kept, district)
        removed = make_person(full_name='Takiyah "T.N." Tate')
        old_url = removed.get_absolute_url()
        merge_people(kept, removed)

        response = self.client.get(old_url)
        self.assertRedirects(response, kept.get_absolute_url(), status_code=301)

    def test_unknown_slug_is_still_404(self):
        response = self.client.get(reverse('directory:person_detail', kwargs={'slug': 'no-such-person'}))
        self.assertEqual(response.status_code, 404)
