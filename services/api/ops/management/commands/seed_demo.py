"""Seed a synthetic local demo (never real people or guest data). Local/test environments only.

Three roles (ADR-0011): one admin (second factor: `manage.py demo_totp admin`), one supervisor and three valets.
Valets sign in with their mobile number. Every account here is synthetic and its password is in DEMO_PASSWORDS;
real people set their own password with a one-time setup code instead.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.crypto import encrypt_text, keyed_hash
from ops.models import (
    Event,
    EventAssignment,
    KeyStation,
    Organization,
    ParkingZone,
    Role,
    Shift,
    Staff,
    Venue,
)

# Synthetic TOTP secret for the local demo only (admins must use a second factor).
# `manage.py demo_totp admin` prints the current code. Never use this outside local/test.
DEMO_TOTP_SECRETS = {"admin": "SALLIMHADEMOADMINXX23456"}
VALETS = [("ماجد (تجريبي)", "+966550000101"), ("سارة (تجريبي)", "+966550000102"),
          ("فهد (تجريبي)", "+966550000103")]
DEMO_PASSWORDS = {"admin": "sallimha-demo-admin", "supervisor": "sallimha-demo-supervisor",
                  **{phone: f"sallimha-demo-valet-{phone[-3:]}" for _name, phone in VALETS}}


class Command(BaseCommand):
    help = "Create a synthetic demo organization, venue, event, staff and open valet shifts (local/test only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="flush the database first")
        parser.add_argument("--with-activity", action="store_true",
                            help="also create a synthetic mid-event state (offers, an accepted retrieval, alerts)")

    def handle(self, *args, reset=False, with_activity=False, **options):
        if not settings.IS_DEV:
            raise CommandError("seed_demo is only allowed in local/test environments")
        if reset:
            call_command("flush", "--noinput", verbosity=0)
        org = Organization.objects.create(name="Sallimha demo (synthetic)")
        venue = Venue.objects.create(org=org, name="قاعة العرض التجريبية", pickup_point_ar="المدخل الرئيسي",
                                     pickup_point_en="the main entrance",
                                     latitude="24.764600", longitude="46.640200")  # synthetic: central Riyadh
        for code, ar, en in (("A", "المنطقة أ", "Zone A"), ("B", "المنطقة ب", "Zone B"), ("C", "المنطقة ج", "Zone C")):
            ParkingZone.objects.create(venue=venue, code=code, label_ar=ar, label_en=en)
        KeyStation.objects.create(venue=venue, name="Key board", hook_count=300)
        event = Event.objects.create(org=org, venue=venue, name="ليلة العرض (تجريبي)",
                                     starts_at=timezone.now() - timedelta(hours=1))
        users = get_user_model()
        people = {}
        for username, role, name, phone in (
            ("admin", Role.ADMIN, "مسؤول النظام (تجريبي)", "+966550000003"),
            ("supervisor", Role.SUPERVISOR, "مشرفة الليلة (تجريبي)", "+966550000002"),
        ):
            user = users.objects.create_user(username=username, password=DEMO_PASSWORDS[username])
            people[username] = Staff.objects.create(
                org=org, full_name=name, phone_e164=phone, phone_hash=keyed_hash(phone, "phone"), role=role,
                user=user, mfa_secret_enc=encrypt_text(DEMO_TOTP_SECRETS[username]) if username in DEMO_TOTP_SECRETS
                else "")
        supervisor = people["supervisor"]
        EventAssignment.objects.create(event=event, staff=supervisor, assigned_by=people["admin"])
        for name, phone in VALETS:
            user = users.objects.create_user(username=phone, password=DEMO_PASSWORDS[phone])  # sign-in: the mobile
            valet = Staff.objects.create(org=org, full_name=name, phone_e164=phone,
                                         phone_hash=keyed_hash(phone, "phone"), role=Role.VALET, user=user)
            EventAssignment.objects.create(event=event, staff=valet, assigned_by=supervisor)
            Shift.objects.create(event=event, staff=valet, started_at=timezone.now(), started_by=supervisor,
                                 availability=Shift.Availability.AVAILABLE, idle_since=timezone.now())
        if with_activity:
            _activity(event)
        self.stdout.write(self.style.SUCCESS(f"Seeded synthetic demo event {event.id} with {len(VALETS)} valets."))


SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0" + b"SALLIMHA-SYNTHETIC-PHOTO" * 8


def _activity(event):
    """Mid-event state built through the real services (all synthetic, guest numbers are fictional)."""
    from ops.models import RetrievalRequest, Ticket
    from ops.services import dispatch, intake, retrieval

    v1, v2, v3 = Staff.objects.filter(role=Role.VALET, org=event.org).order_by("id")

    def park(valet, phone, plate, zone, spot, hook):
        ticket = intake.register_vehicle(valet)
        intake.confirm_guest_phone(valet, ticket, phone)
        intake.record_vehicle(valet, ticket, plate)
        for _ in range(4):
            intake.attach_intake_media(valet, ticket, SYNTHETIC_JPEG, "image/jpeg")
        intake.start_parking(valet, ticket)
        intake.record_location(valet, ticket, zone, spot)
        return intake.complete_parking(valet, ticket, hook)

    a = park(v1, "+966500000201", "KSA 4821 لكزس رمادية", "A", "7", 11)
    b = park(v3, "+966500000202", "RJA 1190 تاهو سوداء", "B", "3", 12)
    retrieval.request_retrieval(a.bindings.get(), a, now=timezone.now() - timedelta(minutes=5))
    retrieval.request_retrieval(b.bindings.get(), b)
    for task in dispatch.dispatch_event(event.id):
        if task.assignee == v3:
            dispatch.accept_offer(v3, task.id)  # as the valet would in the app
    c = intake.register_vehicle(v2)
    intake.confirm_guest_phone(v2, c, "+966500000203")
    # Synthetic history for the dashboard's hourly chart: the two parked cars arrived earlier in the evening.
    Ticket.objects.filter(pk=a.pk).update(created_at=timezone.now() - timedelta(hours=3, minutes=10))
    Ticket.objects.filter(pk=b.pk).update(created_at=timezone.now() - timedelta(hours=2, minutes=5))
    dispatch.raise_alerts(timezone.now())
    assert RetrievalRequest.objects.filter(event=event).count() == 2
