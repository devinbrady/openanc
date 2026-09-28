from django.test import SimpleTestCase

from directory.templatetags.directory_extras import as_percentage


class AsPercentageTests(SimpleTestCase):
    def test_converts_fraction_to_percentage(self):
        self.assertAlmostEqual(as_percentage(0.5865), 58.65)

    def test_zero(self):
        self.assertEqual(as_percentage(0), 0)
