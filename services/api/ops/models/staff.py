from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    """Three product roles (ADR-0011). The framework's superuser flag is separate and never used by the product."""

    VALET = "VALET"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


ROLE_RANK = {Role.VALET: 0, Role.SUPERVISOR: 1, Role.ADMIN: 2}


class Staff(models.Model):
    """A person in the unified directory. Everyone signs in to the staff app with their own linked auth user
    (ADR-0011); valets reach only the valet endpoints."""

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
    mfa_last_step = models.BigIntegerField(null=True, blank=True)  # last accepted TOTP time step (no replay)
    mfa_failures = models.PositiveSmallIntegerField(default=0)
    mfa_locked_at = models.DateTimeField(null=True, blank=True)  # locked until an admin re-issues enrolment
    session_epoch = models.PositiveIntegerField(default=0)  # bumped to invalidate every session of this person
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["org", "phone_e164"], name="uniq_staff_phone_per_org")]

    @property
    def rank(self) -> int:
        return ROLE_RANK[self.role]


class AccountSetup(models.Model):
    """One-time code with which a person sets their own password (ADR-0011): issued by an admin, shown once, stored
    only as a keyed hash. Issuing a new code revokes the previous one; it also serves as the password reset."""

    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="account_setups")
    code_hash = models.CharField(max_length=64)
    issued_by = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["staff"], condition=models.Q(used_at__isnull=True, revoked_at__isnull=True),
                                    name="one_live_account_setup_per_person")
        ]


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
    # Staff connectivity loss (ADR-0011): this valet's device is not working, so a supervisor records what they
    # report in person or by radio. Set and cleared by a supervisor, with the reason in the audit trail.
    assisted_since = models.DateTimeField(null=True, blank=True)

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
