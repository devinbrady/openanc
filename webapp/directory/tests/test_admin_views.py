import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from directory.models import Candidate, Person, PersonImportBatch, PersonImportRow
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import make_candidate_status, make_district, make_election, make_person


class PersonImportFlowTests(PageRenderingTestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)
        self.district = make_district(designator='1A01')
        self.election = make_election(year=2026)
        self.status = make_candidate_status(name='Declared Intention to Run')
        self.existing_person = make_person(full_name='Jaspal Bhatia')

    def _upload_csv(self, content):
        csv_file = SimpleUploadedFile('candidates.csv', content.encode(), content_type='text/csv')
        return self.client.post(reverse('admin:directory_person_import_upload'), {
            'csv_file': csv_file,
            'source_label': 'test upload',
            'election': self.election.pk,
            'default_status': self.status.pk,
        })

    def test_upload_creates_batch_and_matched_rows(self):
        csv_content = 'name,district\nJaspal Bhatia,1A01\nBrand New Person,1A01\n'
        response = self._upload_csv(csv_content)

        self.assertEqual(PersonImportBatch.objects.count(), 1)
        batch = PersonImportBatch.objects.get()
        self.assertRedirects(response, reverse('admin:directory_person_import_review', kwargs={'batch_id': batch.pk}))

        rows = list(batch.rows.all())
        self.assertEqual(len(rows), 2)
        exact_match_row = batch.rows.get(raw_name='Jaspal Bhatia')
        self.assertEqual(exact_match_row.decision, PersonImportRow.DECISION_LINK)
        self.assertEqual(exact_match_row.chosen_person, self.existing_person)
        self.assertEqual(exact_match_row.district, self.district)

        new_row = batch.rows.get(raw_name='Brand New Person')
        self.assertEqual(new_row.decision, PersonImportRow.DECISION_NEW)

    def test_upload_matches_district_from_a_dcboe_style_anc_smd_column(self):
        """DCBOE's own ballot export CSVs (data/dcboe/excel-clean/*.csv) use "ANC-SMD" as the
        column header, not "district" -- the parser needs to recognize that alias too, or every
        row comes back with no district matched."""
        csv_content = 'ANC-SMD,Name\n1A01,Brand New Person\n'
        self._upload_csv(csv_content)

        row = PersonImportRow.objects.get(raw_name='Brand New Person')
        self.assertEqual(row.district, self.district)

    def test_review_page_saves_decisions(self):
        self._upload_csv('name,district\nBrand New Person,1A01\n')
        batch = PersonImportBatch.objects.get()
        row = batch.rows.get()

        response = self.client.post(reverse('admin:directory_person_import_review', kwargs={'batch_id': batch.pk}), {
            f'decision_{row.id}': PersonImportRow.DECISION_SKIP,
        })
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.decision, PersonImportRow.DECISION_SKIP)

    def test_apply_creates_person_and_candidate(self):
        self._upload_csv('name,district\nBrand New Person,1A01\n')
        batch = PersonImportBatch.objects.get()

        response = self.client.post(reverse('admin:directory_person_import_apply', kwargs={'batch_id': batch.pk}))
        self.assertEqual(response.status_code, 302)

        person = Person.objects.get(full_name='Brand New Person')
        candidate = Candidate.objects.get(person=person, election=self.election)
        self.assertEqual(candidate.district, self.district)
        self.assertEqual(candidate.status, self.status)
        self.assertEqual(candidate.source, 'import')

        row = batch.rows.get()
        self.assertTrue(row.applied)

    def test_apply_is_idempotent(self):
        self._upload_csv('name,district\nBrand New Person,1A01\n')
        batch = PersonImportBatch.objects.get()
        apply_url = reverse('admin:directory_person_import_apply', kwargs={'batch_id': batch.pk})

        self.client.post(apply_url)
        self.client.post(apply_url)

        self.assertEqual(Person.objects.filter(full_name='Brand New Person').count(), 1)
        self.assertEqual(Candidate.objects.count(), 1)

    def test_apply_links_existing_person_when_decision_is_link(self):
        self._upload_csv('name,district\nJaspal Bhatia,1A01\n')
        batch = PersonImportBatch.objects.get()

        self.client.post(reverse('admin:directory_person_import_apply', kwargs={'batch_id': batch.pk}))

        self.assertEqual(Person.objects.filter(full_name='Jaspal Bhatia').count(), 1)
        candidate = Candidate.objects.get(person=self.existing_person)
        self.assertEqual(candidate.district, self.district)

    def test_upload_requires_staff_login(self):
        self.client.logout()
        response = self.client.get(reverse('admin:directory_person_import_upload'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
