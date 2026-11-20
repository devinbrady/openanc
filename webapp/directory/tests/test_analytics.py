"""Server-side GoatCounter counting for the JSON API and /llms.txt, which never load the
GoatCounter script. Hits are sent in the background, and never include the client's IP, user
agent or the coordinates they looked up: only the path, and a title naming the kind of client."""
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from directory.analytics import agent_label
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import make_district

COUNT_URL = 'https://openanc.goatcounter.com/api/v0/count'
LOOKUP_1A01 = '/api/lookup/?lat=38.9258&lng=-77.0347'


def run_now(fn, *args):
    fn(*args)


class AgentLabelTests(SimpleTestCase):
    def test_known_assistants(self):
        cases = {
            'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot': 'ChatGPT-User',
            'Mozilla/5.0 (compatible; Claude-User/1.0; +Claude-User@anthropic.com)': 'Claude-User',
            'Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)': 'ClaudeBot',
            'Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)': 'PerplexityBot',
            'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)': 'Googlebot',
            'curl/8.7.1': 'curl',
            'python-requests/2.32.3': 'python-requests',
        }
        for user_agent, label in cases.items():
            self.assertEqual(agent_label(user_agent), label, user_agent)

    def test_browsers_and_unknowns(self):
        self.assertEqual(agent_label('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15'), 'Browser')
        self.assertEqual(agent_label('SomethingNew/0.1'), 'Other')
        self.assertEqual(agent_label(''), 'Other')


@override_settings(GOATCOUNTER_API_TOKEN='test-token', GOATCOUNTER_COUNT_URL=COUNT_URL)
@patch('directory.analytics._run_in_background', side_effect=run_now)
@patch('directory.analytics.requests.post', return_value=Mock(status_code=202))
class CountingTests(PageRenderingTestCase):
    def setUp(self):
        make_district()

    def _hit(self, post):
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], COUNT_URL)
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-token')
        self.assertTrue(kwargs['json']['no_sessions'])
        [hit] = kwargs['json']['hits']
        return hit

    def test_lookup_is_counted_without_coordinates_ip_or_user_agent(self, post, _):
        self.client.get(LOOKUP_1A01, HTTP_USER_AGENT='Mozilla/5.0 (compatible; ChatGPT-User/1.0)', REMOTE_ADDR='203.0.113.9')
        hit = self._hit(post)
        self.assertEqual(hit, {'path': '/api/lookup/', 'title': 'API lookup · ChatGPT-User'})

    def test_error_status_goes_in_the_title(self, post, _):
        self.client.get('/api/lookup/?lat=abc&lng=-77', HTTP_USER_AGENT='curl/8.7.1')
        self.assertEqual(self._hit(post)['title'], 'API lookup (400) · curl')

    def test_district_json_and_llms_txt_are_counted(self, post, _):
        self.client.get(reverse('directory:api_district', kwargs={'year': 2022, 'designator': '1A01'}))
        self.assertEqual(self._hit(post), {'path': '/api/districts/2022/1A01/', 'title': 'API district · Other'})
        post.reset_mock()
        self.client.get('/llms.txt', HTTP_USER_AGENT='Mozilla/5.0 (compatible; ClaudeBot/1.0)')
        self.assertEqual(self._hit(post), {'path': '/llms.txt', 'title': 'llms.txt · ClaudeBot'})

    def test_html_pages_are_left_to_the_script(self, post, _):
        self.client.get(reverse('directory:district_list'))
        post.assert_not_called()

    def test_goatcounter_errors_never_reach_the_visitor(self, post, _):
        for failure in (Mock(side_effect=requests.ConnectionError('down')), Mock(return_value=Mock(status_code=401, text='unknown token'))):
            post.side_effect = failure.side_effect
            post.return_value = failure.return_value
            with self.assertLogs('directory.analytics', level='WARNING'):
                response = self.client.get(LOOKUP_1A01)
            self.assertEqual(response.status_code, 200)


@patch('directory.analytics.requests.post')
class CountingDisabledTests(PageRenderingTestCase):
    @override_settings(GOATCOUNTER_API_TOKEN='')
    def test_nothing_is_sent_without_a_token(self, post):
        make_district()
        self.client.get(LOOKUP_1A01)
        post.assert_not_called()

    @override_settings(GOATCOUNTER_API_TOKEN='test-token')
    def test_head_requests_are_not_counted(self, post):
        with patch('directory.analytics._run_in_background') as background:
            self.client.head('/llms.txt')
        background.assert_not_called()


class BackgroundThreadTests(SimpleTestCase):
    def test_runs_the_function_on_a_daemon_thread(self):
        from directory.analytics import _run_in_background

        with patch('directory.analytics.threading.Thread') as thread:
            _run_in_background(print, 'x')
        thread.assert_called_once_with(target=print, args=('x',), daemon=True)
        thread.return_value.start.assert_called_once()
