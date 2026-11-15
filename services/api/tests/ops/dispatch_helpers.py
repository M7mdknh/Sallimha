from datetime import timedelta

from django.utils import timezone

from ops.models import Shift
from ops.services import retrieval
from tests.ops.intake_helpers import park

_phones = iter(range(1000000, 9999999))


def parked_with_request(valet, event, requested_at=None):
    ticket = park(valet, event, phone=f"+96650{next(_phones):07d}")
    binding = ticket.bindings.get()
    req, _ = retrieval.request_retrieval(binding, ticket, now=requested_at or timezone.now())
    return ticket, req


def set_idle(staff, minutes_ago):
    Shift.objects.filter(staff=staff, ended_at__isnull=True).update(
        idle_since=timezone.now() - timedelta(minutes=minutes_ago))


def make_busy(staff, available=False):
    Shift.objects.filter(staff=staff, ended_at__isnull=True).update(
        availability="AVAILABLE" if available else "UNAVAILABLE")
