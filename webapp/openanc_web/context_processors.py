from django.conf import settings
from django.templatetags.static import static
from django.utils.functional import lazy


def environment(request):
    """Expose which environment this is, so templates can mark non-production pages."""
    return {'is_production': settings.ENVIRONMENT_NAME == 'production'}


def social_meta(request):
    """Absolute URLs for base.html's link-preview tags, which sites like Bluesky require. Uses the
    canonical https host when set, so shares from www. or the fly.dev host point at the real site."""
    if settings.CANONICAL_HOST:
        origin = f'https://{settings.CANONICAL_HOST}'
    else:
        origin = f'{request.scheme}://{request.get_host()}'
    # Lazy: this runs for every template rendered with a request (admin pages included), and
    # resolving a static URL needs the collectstatic manifest, so only do it when a page uses it.
    return {
        'og_url': origin + request.path,
        'og_image': lazy(lambda: origin + static('directory/img/share.png'), str)(),
    }
