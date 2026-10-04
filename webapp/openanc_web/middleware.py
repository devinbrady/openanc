from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class WwwRedirectMiddleware:
    """Redirect www.<CANONICAL_HOST> to <CANONICAL_HOST>, keeping path and query string.

    Only the www host is redirected: openanc.fly.dev and the health check's Host header keep
    working. Off when CANONICAL_HOST is empty (local dev and tests).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical = settings.CANONICAL_HOST
        if canonical and request.get_host().split(':')[0] == f'www.{canonical}':
            target = f'https://{canonical}{request.get_full_path()}'
            if request.method in ('GET', 'HEAD'):
                return HttpResponsePermanentRedirect(target)
            # 308 so a POST (e.g. the suggestion form) isn't turned into a GET.
            response = HttpResponsePermanentRedirect(target)
            response.status_code = 308
            return response
        return self.get_response(request)
