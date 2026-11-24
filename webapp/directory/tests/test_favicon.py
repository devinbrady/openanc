import struct

from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.urls import reverse

from directory.tests.base import PageRenderingTestCase

SVG = 'directory/img/favicon.svg'
PNG_32 = 'directory/img/favicon-32.png'
APPLE_TOUCH = 'directory/img/apple-touch-icon.png'


def png_size(path):
    """(width, height) from a PNG's IHDR chunk, so the test needs no imaging library."""
    with open(path, 'rb') as f:
        header = f.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n', f'{path} is not a PNG'
    return struct.unpack('>II', header[16:24])


class FaviconFileTests(PageRenderingTestCase):
    def test_svg_icon_exists(self):
        path = finders.find(SVG)
        self.assertIsNotNone(path)
        with open(path) as f:
            self.assertIn('<svg', f.read())

    def test_png_icons_have_expected_sizes(self):
        for name, size in [(PNG_32, (32, 32)), (APPLE_TOUCH, (180, 180))]:
            with self.subTest(name=name):
                path = finders.find(name)
                self.assertIsNotNone(path)
                self.assertEqual(png_size(path), size)


class FaviconLinkTests(PageRenderingTestCase):
    def test_every_page_head_links_the_icons(self):
        html = self.client.get(reverse('directory:about')).content.decode()
        self.assertIn(f'<link rel="icon" href="{static(SVG)}" type="image/svg+xml">', html)
        self.assertIn(f'<link rel="icon" href="{static(PNG_32)}" sizes="32x32" type="image/png">', html)
        self.assertIn(f'<link rel="apple-touch-icon" href="{static(APPLE_TOUCH)}">', html)


class FaviconIcoTests(PageRenderingTestCase):
    def test_favicon_ico_redirects_to_png(self):
        # Browsers and crawlers ask for /favicon.ico regardless of the <link> tags. A temporary
        # redirect, since the target's hashed static URL changes whenever the icon does.
        response = self.client.get('/favicon.ico')
        self.assertRedirects(response, static(PNG_32), status_code=302, fetch_redirect_response=False)
