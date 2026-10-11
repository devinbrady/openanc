from django.test import TestCase

from directory.models import Person


class LegacyUrlRedirectTests(TestCase):
    def assertPermanentRedirect(self, old, new):
        response = self.client.get(old)
        self.assertEqual(response.status_code, 301, old)
        self.assertEqual(response['Location'], new, old)

    def test_top_level_pages(self):
        for old, new in [
            ('/index.html', '/'),
            ('/about.html', '/about/'),
            ('/about', '/about/'),
            ('/updates.html', '/updates/'),
            ('/counts.html', '/counts/'),
            ('/contested.html', '/contested/'),
            ('/list.html', '/districts/'),
            ('/people/index.html', '/people/'),
            ('/map_2022/ancs/index.html', '/districts/'),
            ('/map_2012/wards/', '/districts/'),
        ]:
            self.assertPermanentRedirect(old, new)

    def test_anc_district_and_ward_pages(self):
        for old, new in [
            ('/map_2022/ancs/1A.html', '/ancs/2022/1A/'),
            ('/map_2012/ancs/6B', '/ancs/2012/6B/'),
            ('/map_2022/ancs/districts/1A01.html', '/districts/2022/1A01/'),
            ('/map_2012/ancs/districts/2B09.html', '/districts/2012/2B09/'),
            ('/map_2022/wards/7.html', '/wards/2022/7/'),
        ]:
            self.assertPermanentRedirect(old, new)

    def test_dual_ward_designators_get_their_slash_back(self):
        self.assertPermanentRedirect('/map_2022/ancs/34G.html', '/ancs/2022/3-4G/')
        self.assertPermanentRedirect('/map_2022/ancs/68F.html', '/ancs/2022/6-8F/')
        self.assertPermanentRedirect('/map_2022/ancs/districts/34G01.html', '/districts/2022/3-4G01/')

    def test_renamed_ancs_point_at_their_dual_ward_successor(self):
        self.assertPermanentRedirect('/map_2012/ancs/3G.html', '/ancs/2012/3-4G/')
        self.assertPermanentRedirect('/map_2022/ancs/districts/8F01.html', '/districts/2022/6-8F01/')
        # Only in the year the rename applies to.
        self.assertPermanentRedirect('/map_2022/ancs/3G.html', '/ancs/2022/3G/')

    def test_person_page_uses_old_person_id(self):
        # data/people.csv: 10001,Layla Bonnot,...,person_LaylaBonnot
        person = Person.objects.create(id=10001, full_name='Layla Bonnot')
        self.assertPermanentRedirect('/people/LaylaBonnot.html', person.get_absolute_url())
        self.assertPermanentRedirect('/people/LaylaBonnot', person.get_absolute_url())

    def test_person_lookup_ignores_case_and_unicode_normalization(self):
        # The old file on disk was MichaelJMcgarty.html; people.csv says MichaelJMcGarty.
        mcgarty = Person.objects.create(id=11851, full_name='Michael J. McGarty')
        self.assertPermanentRedirect('/people/MichaelJMcgarty.html', mcgarty.get_absolute_url())

    def test_unknown_old_person_page_is_404(self):
        self.assertEqual(self.client.get('/people/NoSuchPerson.html').status_code, 404)

    def test_new_person_slug_without_trailing_slash_still_appends_it(self):
        self.assertPermanentRedirect('/people/aaron-brown', '/people/aaron-brown/')

    def test_new_person_pages_are_not_shadowed(self):
        person = Person.objects.create(full_name='Aaron Brown')
        self.assertEqual(self.client.get(person.get_absolute_url()).status_code, 200)
