"""Opening check and dead-letter operations (docs/01 §1, docs/03). Never present a healthy status while the
worker or the notification integration is down."""

from django.db import transaction

from core.audit import audit
from core.views_health import whatsapp_status, worker_status
from messaging import outbox
from messaging.models import MessageOutbox
from ops.models import EventAssignment, KeyStation, ParkingZone, Role, Shift
from ops.permissions import actor_label, require
from ops.services import carryover


def opening_check(event) -> dict:
    worker = worker_status()
    whatsapp = whatsapp_status()
    zones = ParkingZone.objects.filter(venue=event.venue, active=True).count()
    hooks = sum(KeyStation.objects.filter(venue=event.venue).values_list("hook_count", flat=True))
    on_shift = set(Shift.objects.filter(event=event, ended_at__isnull=True).values_list("staff_id", flat=True))
    not_started = EventAssignment.objects.filter(event=event, staff__enabled=True).exclude(
        staff_id__in=on_shift).count()
    carryovers = carryover.register(event.org).filter(ticket__event__venue=event.venue).count()
    dead = MessageOutbox.objects.filter(status=MessageOutbox.Status.DEAD).count()
    causes = []
    if worker != "ok":
        causes.append("worker")
    if whatsapp != "configured":
        causes.append("whatsapp")  # "simulated" is not a production-ready integration
    if zones == 0:
        causes.append("zones")
    if hooks == 0:
        causes.append("key_hooks")
    return {"ok": not causes, "causes": causes, "worker": worker, "whatsapp": whatsapp, "zones": zones,
            "key_hooks": hooks, "assigned_not_started": not_started, "carryover_unresolved": carryovers,
            "dead_letters": dead}


def dead_letters(org):
    return (MessageOutbox.objects.filter(status=MessageOutbox.Status.DEAD)
            .filter(staff__org=org) | MessageOutbox.objects.filter(status=MessageOutbox.Status.DEAD,
                                                                   ticket__event__org=org)).distinct().order_by("id")


def replay_dead_letter(actor, row) -> bool:
    require(actor, Role.ADMIN)
    with transaction.atomic():
        replayed = outbox.replay(row.id)
        audit("outbox.replay", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
              entity_type="outbox", entity_id=row.id, summary={"replayed": replayed, "kind": row.kind})
    return replayed
