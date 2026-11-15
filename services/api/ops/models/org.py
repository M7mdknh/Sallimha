from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=120)


class Venue(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="venues")
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="Asia/Riyadh")
    pickup_point_ar = models.CharField(max_length=120, default="نقطة التسليم")
    pickup_point_en = models.CharField(max_length=120, default="the pickup point")


class ParkingZone(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="zones")
    code = models.CharField(max_length=20)
    label_ar = models.CharField(max_length=80)
    label_en = models.CharField(max_length=80)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["venue", "code"], name="uniq_zone_code_per_venue")]


class KeyStation(models.Model):
    """Physical key board at a venue. Hooks belong to the venue, not to an event (ADR-0005 C1)."""

    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="key_stations")
    name = models.CharField(max_length=80)
    hook_count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(hook_count__gte=1), name="key_station_has_hooks")
        ]


class Event(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        CLOSED = "CLOSED"

    org = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="events")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="events")
    name = models.CharField(max_length=160)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    display_seq = models.PositiveIntegerField(default=0)
    timings = models.JSONField(default=dict)  # snapshot of OperatingConfig timings at creation
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="closed_events"
    )


class OperatingConfig(models.Model):
    """Admin-managed settings per organization (docs/01 Preserved capabilities). Changes are audited; issued
    offers keep their deadlines. Retention 0 means never delete (preserved original meaning)."""

    org = models.OneToOneField(Organization, on_delete=models.PROTECT, related_name="config")
    timings = models.JSONField(default=dict)
    retention_days = models.JSONField(default=dict)  # guest_contact | intake_photos | incident_evidence
    template_overrides = models.JSONField(default=dict)  # template key -> {"ar": ..., "en": ...}
    updated_at = models.DateTimeField(auto_now=True)
