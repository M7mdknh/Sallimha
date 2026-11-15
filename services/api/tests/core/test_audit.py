import pytest
from django.db import DatabaseError, transaction

from core.audit import audit
from core.models import AuditEvent


@pytest.mark.django_db
def test_audit_records_actor_channel_and_summary():
    event = audit("ticket.cancel", actor_id=7, actor_label="Supervisor A", channel="console",
                  entity_type="ticket", entity_id=42, event_id=3, summary={"reason": "guest left"})
    stored = AuditEvent.objects.get(pk=event.pk)
    assert (stored.action, stored.actor_id) == ("ticket.cancel", 7)
    assert (stored.channel, stored.event_id) == ("console", 3)
    assert stored.summary == {"reason": "guest left"}


@pytest.mark.django_db
def test_audit_update_blocked_by_trigger():
    event = audit("x", actor_id=None, actor_label="system", channel="worker")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")


@pytest.mark.django_db
def test_audit_delete_blocked_by_trigger():
    event = audit("x", actor_id=None, actor_label="system", channel="worker")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()
