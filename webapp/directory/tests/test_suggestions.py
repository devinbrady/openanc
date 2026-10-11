from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from directory.forms import SuggestionForm
from directory.models import Suggestion
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import make_district


class SuggestionFormTests(TestCase):
    def test_valid_submission_is_not_spam(self):
        form = SuggestionForm(data={'name': 'Jane', 'email': '', 'message': 'Please update this.'})
        self.assertTrue(form.is_valid())
        self.assertFalse(form.is_spam())

    def test_honeypot_filled_in_marks_spam(self):
        form = SuggestionForm(data={'message': 'Buy now', 'website': 'http://spam.example'})
        self.assertTrue(form.is_valid())
        self.assertTrue(form.is_spam())

    def test_message_is_required(self):
        form = SuggestionForm(data={'name': 'Jane'})
        self.assertFalse(form.is_valid())


class SuggestionCreateViewTests(PageRenderingTestCase):
    def test_valid_post_creates_suggestion_and_sends_notification(self):
        district = make_district()
        response = self.client.post(reverse('directory:suggest_edit'), {
            'name': 'Jane',
            'email': 'jane@example.com',
            'district': district.id,
            'message': 'There is a new write-in candidate for this district.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(district), mail.outbox[0].body)

    def test_mail_failure_still_saves_suggestion_and_logs_error(self):
        with patch('directory.views.send_mail', side_effect=SMTPException('auth failed')), \
                self.assertLogs('directory.views', level='ERROR') as logs:
            response = self.client.post(reverse('directory:suggest_edit'), {
                'message': 'There is a new write-in candidate for this district.',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 1)
        self.assertIn('Failed to send notification email', logs.output[0])

    def test_honeypot_submission_is_silently_dropped(self):
        response = self.client.post(reverse('directory:suggest_edit'), {
            'message': 'Buy cheap watches',
            'website': 'http://spam.example',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_district_query_param_prefills_the_form(self):
        district = make_district()
        response = self.client.get(reverse('directory:suggest_edit'), {'district': district.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial.get('district'), str(district.id))
