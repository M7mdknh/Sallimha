"""Seed a synthetic local demo (never real people or guest data). Local/test environments only.

Demo console accounts (local only, documented in README "Local demo"):
  manager / sallimha-demo-manager      supervisor / sallimha-demo-supervisor
Manager accounts will require TOTP enrolment once MFA is enabled (Task 2.3).
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
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
    Venue,
)

DEMO_PASSWORDS = {"manager": "sallimha-demo-manager", "supervisor": "sallimha-demo-supervisor",
                  "admin": "sallimha-demo-admin"}
VALETS = [("ماجد (تجريبي)", "+966550000101"), ("سارة (تجريبي)", "+966550000102"),
          ("فهد (تجريبي)", "+966550000103")]


class Command(BaseCommand):
    help = "Create a synthetic demo organization, venue, event, staff and open valet shifts (local/test only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="flush the database first")

    def handle(self, *args, reset=False, **options):
        if not settings.IS_DEV:
            raise CommandError("seed_demo is only allowed in local/test environments")
        if reset:
            call_command("flush", "--noinput", verbosity=0)
        org = Organization.objects.create(name="Sallimha demo (synthetic)")
        venue = Venue.objects.create(org=org, name="قاعة العرض التجريبية", pickup_point_ar="المدخل الرئيسي",
                                     pickup_point_en="the main entrance")
        for code, ar, en in (("A", "المنطقة أ", "Zone A"), ("B", "المنطقة ب", "Zone B"), ("C", "المنطقة ج", "Zone C")):
            ParkingZone.objects.create(venue=venue, code=code, label_ar=ar, label_en=en)
        KeyStation.objects.create(venue=venue, name="Key board", hook_count=300)
        event = Event.objects.create(org=org, venue=venue, name="ليلة العرض (تجريبي)",
                                     starts_at=timezone.now() - timedelta(hours=1))
        users = get_user_model()
        people = {}
        for username, role, name, phone in (
            ("manager", Role.MANAGER, "مدير العرض (تجريبي)", "+966550000001"),
            ("supervisor", Role.SUPERVISOR, "مشرفة الليلة (تجريبي)", "+966550000002"),
            ("admin", Role.ADMIN, "مسؤول النظام (تجريبي)", "+966550000003"),
        ):
            user = users.objects.create_user(username=username, password=DEMO_PASSWORDS[username])
            people[username] = Staff.objects.create(org=org, full_name=name, phone_e164=phone,
                                                    phone_hash=keyed_hash(phone, "phone"), role=role, user=user)
        supervisor = people["supervisor"]
        EventAssignment.objects.create(event=event, staff=supervisor, assigned_by=people["manager"])
        for name, phone in VALETS:
            valet = Staff.objects.create(org=org, full_name=name, phone_e164=phone,
                                         phone_hash=keyed_hash(phone, "phone"), role=Role.VALET)
            EventAssignment.objects.create(event=event, staff=valet, assigned_by=supervisor)
            Shift.objects.create(event=event, staff=valet, started_at=timezone.now(), started_by=supervisor,
                                 availability=Shift.Availability.AVAILABLE, idle_since=timezone.now())
        self.stdout.write(self.style.SUCCESS(f"Seeded synthetic demo event {event.id} with {len(VALETS)} valets."))
