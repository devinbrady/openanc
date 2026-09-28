from django.test import TestCase, override_settings

# The test runner forces DEBUG=False, which makes whitenoise's ManifestStaticFilesStorage
# require a collectstatic-built manifest (normally skipped in dev). Tests that render a
# full page (anything extending base.html, which loads site.css) need a plain storage
# backend instead, so they don't depend on collectstatic having been run first.
TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=TEST_STORAGES)
class PageRenderingTestCase(TestCase):
    pass
