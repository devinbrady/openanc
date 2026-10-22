import time
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from directory.forms import SuggestionForm, make_form_token
from directory.models import Suggestion
from directory.tests.base import PageRenderingTestCase
from directory.tests.factories import make_district


def human_token():
    """A form token from a page loaded a minute ago, as a real user's submission would carry."""
    return make_form_token(time.time() - 60)


class SuggestionFormTests(TestCase):
    def test_valid_submission_is_not_spam(self):
        form = SuggestionForm(data={'name': 'Jane', 'email': '', 'message': 'Please update this.',
                                    'form_token': human_token()})
        self.assertTrue(form.is_valid())
        self.assertFalse(form.is_spam())

    def test_honeypot_filled_in_marks_spam(self):
        form = SuggestionForm(data={'message': 'Buy now', 'website': 'http://spam.example',
                                    'form_token': human_token()})
        self.assertTrue(form.is_valid())
        self.assertTrue(form.is_spam())

    def test_missing_form_token_marks_spam(self):
        form = SuggestionForm(data={'message': 'Buy now'})
        self.assertTrue(form.is_valid())
        self.assertTrue(form.is_spam())

    def test_tampered_form_token_marks_spam(self):
        form = SuggestionForm(data={'message': 'Buy now', 'form_token': human_token() + 'x'})
        self.assertTrue(form.is_valid())
        self.assertTrue(form.is_spam())

    def test_submitting_right_after_page_load_marks_spam(self):
        form = SuggestionForm(data={'message': 'Buy now', 'form_token': make_form_token()})
        self.assertTrue(form.is_valid())
        self.assertTrue(form.is_spam())

    def test_expired_form_token_is_an_error_not_spam(self):
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        form = SuggestionForm(data={'message': 'Please update this.', 'form_token': make_form_token(two_days_ago)})
        self.assertFalse(form.is_valid())
        self.assertIn('open for a long time', form.non_field_errors()[0])

    def test_link_is_optional_but_must_be_a_url(self):
        form = SuggestionForm(data={'message': 'Please update this.', 'link': 'not a url',
                                    'form_token': human_token()})
        self.assertFalse(form.is_valid())
        self.assertIn('link', form.errors)

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
            'form_token': human_token(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(district), mail.outbox[0].body)

    def test_submitted_link_is_saved_and_included_in_notification(self):
        response = self.client.post(reverse('directory:suggest_edit'), {
            'message': 'This commissioner resigned.',
            'link': 'https://news.example.com/resigns',
            'form_token': human_token(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.get().link, 'https://news.example.com/resigns')
        self.assertIn('Link: https://news.example.com/resigns', mail.outbox[0].body)

    def test_mail_failure_still_saves_suggestion_and_logs_error(self):
        with patch('directory.views.send_mail', side_effect=SMTPException('auth failed')), \
                self.assertLogs('directory.views', level='ERROR') as logs:
            response = self.client.post(reverse('directory:suggest_edit'), {
                'message': 'There is a new write-in candidate for this district.',
                'form_token': human_token(),
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 1)
        self.assertIn('Failed to send notification email', logs.output[0])

    def test_honeypot_submission_is_silently_dropped(self):
        response = self.client.post(reverse('directory:suggest_edit'), {
            'message': 'Buy cheap watches',
            'website': 'http://spam.example',
            'form_token': human_token(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_post_without_loading_the_form_is_silently_dropped(self):
        response = self.client.post(reverse('directory:suggest_edit'), {'message': 'Buy cheap watches'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Suggestion.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_expired_token_rerenders_form_with_message_and_fresh_token(self):
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        response = self.client.post(reverse('directory:suggest_edit'), {
            'message': 'There is a new write-in candidate for this district.',
            'form_token': make_form_token(two_days_ago),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Suggestion.objects.count(), 0)
        self.assertContains(response, 'open for a long time')
        self.assertContains(response, 'There is a new write-in candidate for this district.')
        self.assertContains(response, response.context['form'].fresh_form_token)

    def test_form_page_renders_token_and_hidden_honeypot(self):
        response = self.client.get(reverse('directory:suggest_edit'))
        self.assertContains(response, 'name="form_token"')
        self.assertContains(response, 'class="form-honeypot"')

    def test_district_query_param_prefills_the_form(self):
        district = make_district()
        response = self.client.get(reverse('directory:suggest_edit'), {'district': district.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial.get('district'), str(district.id))
