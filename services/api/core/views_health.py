from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import WorkerHeartbeat


@require_GET
def healthz(request):
    """Liveness: the process is serving requests."""
    return JsonResponse({"status": "ok"})


def _db_status() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return "ok"
    except Exception:  # noqa: BLE001 — any DB failure means not ready
        return "unavailable"


def worker_status(now=None) -> str:
    now = now or timezone.now()
    beat = WorkerHeartbeat.objects.order_by("-beat_at").first()
    if beat is None:
        return "missing"
    if now - beat.beat_at > timedelta(seconds=settings.WORKER_HEARTBEAT_STALE_SECONDS):
        return "stale"
    return "ok"


def whatsapp_status() -> str:
    if settings.WHATSAPP_TRANSPORT == "fake":
        return "simulated"
    if settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID:
        return "configured"
    return "not_configured"


@require_GET
def readyz(request):
    """Readiness: DB reachable and worker heartbeat fresh. WhatsApp reported separately."""
    db = _db_status()
    worker = worker_status() if db == "ok" else "unknown"
    body = {"db": db, "worker": worker, "whatsapp": whatsapp_status()}
    ready = db == "ok" and worker == "ok"
    return JsonResponse(body, status=200 if ready else 503)
