from django.conf import settings


def environment(request):
    """Expose which environment this is, so templates can mark non-production pages."""
    return {'is_production': settings.ENVIRONMENT_NAME == 'production'}
