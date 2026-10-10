from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from directory.tests.factories import make_person


class PersonAdminSearchTests(TestCase):
    """Regression coverage for a real report: searching "Lopez" in the Person admin didn't find
    "Mónica Martínez López", because search_fields' default icontains is a plain SQL LIKE, which
    SQLite doesn't fold accents on."""

    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def _search(self, term):
        response = self.client.get(reverse('admin:directory_person_changelist'), {'q': term})
        return response.content.decode()

    def test_unaccented_search_term_finds_an_accented_name(self):
        make_person(full_name='Mónica Martínez López')
        content = self._search('Lopez')
        self.assertIn('Mónica Martínez López', content)

    def test_accented_search_term_finds_an_unaccented_name(self):
        make_person(full_name='Monica Martinez Lopez')
        content = self._search('López')
        self.assertIn('Monica Martinez Lopez', content)

    def test_unrelated_search_term_does_not_match(self):
        make_person(full_name='Mónica Martínez López')
        content = self._search('Bhatia')
        self.assertNotIn('Mónica Martínez López', content)

    def test_autocomplete_endpoint_is_also_diacritic_insensitive(self):
        """CommissionerTerm/Candidate/Suggestion admin forms all look up Person through the same
        shared autocomplete endpoint, which calls PersonAdmin.get_search_results under the
        hood -- so fixing that one method fixes every one of those widgets too."""
        person = make_person(full_name='Mónica Martínez López')
        response = self.client.get(reverse('admin:autocomplete'), {
            'app_label': 'directory', 'model_name': 'commissionerterm', 'field_name': 'person', 'term': 'Lopez',
        })
        data = response.json()
        self.assertIn(str(person.pk), [result['id'] for result in data['results']])


class PersonLinkInlineTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def test_link_url_is_an_editable_input_without_a_currently_line(self):
        person = make_person()
        person.links.create(url='https://janesmith.org/')
        response = self.client.get(reverse('admin:directory_person_change', args=[person.id]))
        self.assertContains(response, 'value="https://janesmith.org/"')
        self.assertNotContains(response, 'Currently:')
