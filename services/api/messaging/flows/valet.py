"""Valet WhatsApp conversation (ADR-0006). Implemented in Task 1.4."""

from core.crypto import keyed_hash
from ops.models import Staff


def find_staff(inb):
    if inb.from_phone:
        staff = Staff.objects.filter(phone_hash=keyed_hash(inb.from_phone, "phone"), enabled=True).first()
        if staff:
            return staff
    if inb.from_user_id:
        return Staff.objects.filter(wa_user_id=inb.from_user_id, enabled=True).first()
    return None


def handle(staff, inb) -> None:
    raise NotImplementedError("valet flow arrives in Task 1.4")
