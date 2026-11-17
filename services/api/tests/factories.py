"""Plain helper factories for tests. Synthetic data only — never real guest data."""

import itertools
from datetime import timedelta

from django.utils import timezone

from core.crypto import keyed_hash
from ops.models import (
    Event,
    EventAssignment,
    KeyStation,
    Organization,
    ParkingZone,
    Role,
    Shift,
    Staff,
    Ticket,
    Venue,
)

_seq = itertools.count(1)


def make_org(name="Sallimha Test Org"):
    return Organization.objects.create(name=name)


def make_venue(org=None, name="Test Hall"):
    org = org or make_org()
    venue = Venue.objects.create(org=org, name=name)
    ParkingZone.objects.create(venue=venue, code="A", label_ar="المنطقة أ", label_en="Zone A")
    ParkingZone.objects.create(venue=venue, code="B", label_ar="المنطقة ب", label_en="Zone B")
    KeyStation.objects.create(venue=venue, name="Main board", hook_count=200)
    return venue


def make_event(venue=None, name="Test Night", org=None):
    venue = venue or make_venue(org=org)
    return Event.objects.create(org=venue.org, venue=venue, name=name, starts_at=timezone.now() - timedelta(hours=1))


def make_staff(org, role=Role.VALET, name=None, phone=None, **extra):
    n = next(_seq)
    phone = phone or f"+96655{n:07d}"
    return Staff.objects.create(
        org=org,
        full_name=name or f"{role.title()} {n}",
        phone_e164=phone,
        phone_hash=keyed_hash(phone, "phone"),
        role=role,
        **extra,
    )


def assign(event, *staff):
    for s in staff:
        EventAssignment.objects.get_or_create(event=event, staff=s)


def open_shift(event, staff, supervisor=None, available=True, idle_since=None):
    assign(event, staff)
    return Shift.objects.create(
        event=event,
        staff=staff,
        started_at=timezone.now() - timedelta(minutes=30),
        started_by=supervisor or staff,
        availability=Shift.Availability.AVAILABLE if available else Shift.Availability.UNAVAILABLE,
        idle_since=idle_since or (timezone.now() - timedelta(minutes=10)),
    )


def make_ticket(event, registered_by, **fields):
    event.display_seq += 1
    event.save(update_fields=["display_seq"])
    return Ticket.objects.create(
        event=event,
        display_number=event.display_seq,
        registered_by=registered_by,
        created_at=timezone.now(),
        **fields,
    )


def onboard(admin, name, phone, role, password, username=None):
    """A person added by an admin who then set their own password with the one-time setup code (ADR-0011)."""
    from ops.services import staffdir

    staff = staffdir.create_staff(admin, name, phone, role, username=username)
    staffdir.complete_setup(staff.user.username, staffdir.issue_setup_code(admin, staff), password)
    staff.refresh_from_db()
    return staff
