from django.test import SimpleTestCase, override_settings


@override_settings(CANONICAL_HOST='openanc.org', ALLOWED_HOSTS=['openanc.org', 'www.openanc.org', 'openanc.fly.dev'])
class WwwRedirectTests(SimpleTestCase):
    def test_www_redirects_to_apex_keeping_path_and_query(self):
        response = self.client.get('/suggest/?x=1', HTTP_HOST='www.openanc.org')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://openanc.org/suggest/?x=1')

    def test_post_uses_308_so_method_is_preserved(self):
        response = self.client.post('/suggest/', HTTP_HOST='www.openanc.org')
        self.assertEqual(response.status_code, 308)
        self.assertEqual(response['Location'], 'https://openanc.org/suggest/')

    def test_apex_and_fly_host_are_not_redirected(self):
        for host in ('openanc.org', 'openanc.fly.dev'):
            response = self.client.get('/robots.txt', HTTP_HOST=host)
            self.assertNotIn(response.status_code, (301, 308))

    @override_settings(CANONICAL_HOST='')
    def test_disabled_when_canonical_host_unset(self):
        response = self.client.get('/', HTTP_HOST='www.openanc.org')
        self.assertNotIn(response.status_code, (301, 308))
