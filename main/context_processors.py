from django.conf import settings


def analytics(request):
    """Expose the analytics tracker config to every template."""
    return {
        "UMAMI_WEBSITE_ID": settings.UMAMI_WEBSITE_ID,
        "UMAMI_SCRIPT_URL": settings.UMAMI_SCRIPT_URL,
    }
