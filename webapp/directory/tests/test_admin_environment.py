from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


class AdminEnvironmentMarkerTests(TestCase):
    """The local admin looks different from production so the two can't be confused."""

    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    @override_settings(ENVIRONMENT_NAME='local')
    def test_local_admin_is_labeled_and_orange(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, '<title>Site administration | OpenANC admin (LOCAL)</title>', html=True)
        self.assertContains(response, 'OpenANC admin (LOCAL)</a>')
        self.assertContains(response, '--header-bg: #c2410c')

    @override_settings(ENVIRONMENT_NAME='production')
    def test_production_admin_is_unmarked(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, '<title>Site administration | OpenANC admin</title>', html=True)
        self.assertContains(response, 'OpenANC admin</a>')
        self.assertNotContains(response, 'LOCAL')
        self.assertNotContains(response, '--header-bg')

    @override_settings(ENVIRONMENT_NAME='local')
    def test_local_login_page_is_marked(self):
        self.client.logout()
        response = self.client.get(reverse('admin:login'))
        self.assertContains(response, 'OpenANC admin (LOCAL)</a>')
        self.assertContains(response, '--header-bg: #c2410c')

    @override_settings(ENVIRONMENT_NAME='local')
    def test_custom_admin_views_are_marked(self):
        response = self.client.get(reverse('admin:directory_person_import_upload'))
        self.assertContains(response, '--header-bg: #c2410c')
