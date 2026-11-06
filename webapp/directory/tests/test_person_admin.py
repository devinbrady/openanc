from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from directory.tests.factories import make_anc, make_person


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


class ANCLinkInlineTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def test_anc_change_page_has_editable_links(self):
        anc = make_anc()
        anc.links.create(url='https://anc1a.org/', publish=False)
        response = self.client.get(reverse('admin:directory_anc_change', args=[anc.id]))
        self.assertContains(response, 'value="https://anc1a.org/"')
        self.assertContains(response, 'name="links-0-publish"')
        self.assertNotContains(response, 'Currently:')


class PersonAliasAdminTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def test_person_search_finds_people_by_alias(self):
        person = make_person(full_name='Zachary Adams')
        person.aliases.create(name='Zach Adams', source='dcboe_ballot')
        response = self.client.get(reverse('admin:directory_person_changelist'), {'q': 'Zach Adams'})
        self.assertContains(response, 'Zachary Adams')

    def test_person_change_page_shows_alias_inline(self):
        person = make_person(full_name='Zachary Adams')
        person.aliases.create(name='Zach Adams', source='dcboe_ballot')
        response = self.client.get(reverse('admin:directory_person_change', args=[person.pk]))
        self.assertContains(response, 'Zach Adams')

    def test_use_as_display_name_action(self):
        person = make_person(full_name='Erika Nunez')
        accented = person.aliases.create(name='Erika Núñez', source='oanc')
        self.client.post(reverse('admin:directory_personalias_changelist'), {
            'action': 'use_as_display_name', '_selected_action': [accented.pk],
        })
        person.refresh_from_db()
        self.assertEqual(person.full_name, 'Erika Núñez')
        self.assertTrue(person.aliases.filter(name='Erika Nunez').exists())


class PersonAdminActionEdgeCaseTests(TestCase):
    def setUp(self):
        staff = User.objects.create_user('staff3', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(staff)

    def messages(self, response):
        return [str(m) for m in response.context['messages']]

    def test_merge_action_needs_exactly_two_people(self):
        people = [make_person(full_name=f'Person {i}') for i in range(3)]
        response = self.client.post(reverse('admin:directory_person_changelist'), {
            'action': 'merge_people', '_selected_action': [p.pk for p in people],
        }, follow=True)
        self.assertIn('Select exactly two people to merge.', self.messages(response))

    def test_search_term_with_no_name_characters_does_not_error(self):
        make_person(full_name='Jane Doe')
        response = self.client.get(reverse('admin:directory_person_changelist'), {'q': '...'})
        self.assertEqual(response.status_code, 200)

    def test_alias_changelist_flags_the_display_name(self):
        person = make_person(full_name='Erika Nunez')
        person.aliases.create(name='Erika Núñez', source='oanc')
        response = self.client.get(reverse('admin:directory_personalias_changelist'))
        self.assertContains(response, 'alt="True"')
        self.assertContains(response, 'alt="False"')

    def test_use_as_display_name_rejects_two_aliases_of_one_person(self):
        person = make_person(full_name='Erika Nunez')
        a = person.aliases.create(name='Erika Núñez', source='oanc')
        b = person.aliases.create(name='E. Nunez', source='oanc')
        response = self.client.post(reverse('admin:directory_personalias_changelist'), {
            'action': 'use_as_display_name', '_selected_action': [a.pk, b.pk],
        }, follow=True)
        self.assertIn('Pick at most one alias per person.', self.messages(response))
        person.refresh_from_db()
        self.assertEqual(person.full_name, 'Erika Nunez')

    def test_import_batch_changelist_links_to_review(self):
        from directory.models import PersonImportBatch
        batch = PersonImportBatch.objects.create(source_label='x')
        response = self.client.get(reverse('admin:directory_personimportbatch_changelist'))
        self.assertContains(response, reverse('admin:directory_person_import_review', kwargs={'batch_id': batch.pk}))
