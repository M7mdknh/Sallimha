"""Same-origin console (ADR-0004): client-side routes return the built console's index.html. Built assets under
/assets and /brand are served by WhiteNoise (WHITENOISE_ROOT = CONSOLE_DIST)."""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def console_index(request, path: str = ""):
    index = Path(settings.CONSOLE_DIST) / "index.html"
    if not index.is_file():
        raise Http404
    response = HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"  # always pick up the asset names of the deployed build
    return response
