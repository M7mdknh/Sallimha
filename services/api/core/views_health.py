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
    """configured / not_configured / simulated, or "degraded" while sends keep failing (ADR-0010): a message has
    failed at least twice and nothing has been sent since it was queued."""
    from messaging.models import MessageOutbox, SimulatorControl

    failing = (MessageOutbox.objects.filter(status=MessageOutbox.Status.PENDING, attempts__gte=2)
               .order_by("created_at").first())
    if failing is not None and not MessageOutbox.objects.filter(sent_at__gte=failing.created_at).exists():
        return "degraded"
    if settings.WHATSAPP_TRANSPORT == "fake":
        if SimulatorControl.outage_active():
            return "degraded"
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
