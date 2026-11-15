from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    VALET = "VALET"
    SUPERVISOR = "SUPERVISOR"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


ROLE_RANK = {Role.VALET: 0, Role.SUPERVISOR: 1, Role.MANAGER: 2, Role.ADMIN: 3, Role.SUPER_ADMIN: 4}


class Staff(models.Model):
    """A person in the unified directory.

    Valets act through WhatsApp; console users also link an auth user.
    """

    org = models.ForeignKey("ops.Organization", on_delete=models.PROTECT, related_name="staff")
    full_name = models.CharField(max_length=120)
    phone_e164 = models.CharField(max_length=20)
    phone_hash = models.CharField(max_length=64, db_index=True)
    wa_user_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.VALET)
    enabled = models.BooleanField(default=True)
    language = models.CharField(max_length=2, default="ar")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="staff"
    )
    mfa_secret_enc = models.TextField(blank=True)
    mfa_enrolled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["org", "phone_e164"], name="uniq_staff_phone_per_org")]

    @property
    def rank(self) -> int:
        return ROLE_RANK[self.role]


class EventAssignment(models.Model):
    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="assignments")
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="assignments")
    assigned_by = models.ForeignKey(Staff, null=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "staff"], name="uniq_assignment")]


class Shift(models.Model):
    """Attendance. One open shift per person across all events (ADR-0003 #2)."""

    class Availability(models.TextChoices):
        AVAILABLE = "AVAILABLE"
        UNAVAILABLE = "UNAVAILABLE"

    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="shifts")
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="shifts")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="+")
    ended_by = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    availability = models.CharField(
        max_length=12, choices=Availability.choices, default=Availability.UNAVAILABLE
    )
    break_pending = models.BooleanField(default=False)
    idle_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["staff"], condition=models.Q(ended_at__isnull=True), name="one_open_shift_per_person"
            )
        ]


class UnavailablePeriod(models.Model):
    """Breaks/unavailable time within a shift, reported separately from worked time."""

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="unavailable_periods")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
