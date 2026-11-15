"""Incidents, safety holds and assisted verification (docs/01 §6–§7, docs/02). Incidents never change the
vehicle state; only an explicit hold can block dispatch or handover."""

from django.db import models
from django.db.models import Q


class Incident(models.Model):
    class Category(models.TextChoices):
        MISSING_VEHICLE = "missing_vehicle"
        KEY_ISSUE = "key_issue"
        DAMAGE = "damage"
        IDENTITY_DISPUTE = "identity_dispute"
        NOTIFICATION_FAILURE = "notification_failure"
        OPERATIONAL_DELAY = "operational_delay"
        COMPLAINT = "complaint"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        IN_REVIEW = "IN_REVIEW"
        RESOLVED = "RESOLVED"

    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="incidents")
    ticket = models.ForeignKey("ops.Ticket", null=True, blank=True, on_delete=models.PROTECT, related_name="incidents")
    category = models.CharField(max_length=24, choices=Category.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    description = models.TextField()
    created_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    resolution = models.TextField(blank=True)
    resolved_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="RESOLVED") | (Q(resolved_at__isnull=False) & ~Q(resolution="")),
                name="resolved_incident_has_outcome",
            )
        ]


class IncidentNote(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="notes")
    author = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class SafetyHold(models.Model):
    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="holds")
    ticket = models.ForeignKey("ops.Ticket", on_delete=models.PROTECT, related_name="holds")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.PROTECT, related_name="holds")
    reason = models.CharField(max_length=200)
    blocks_dispatch = models.BooleanField(default=True)
    blocks_handover = models.BooleanField(default=True)
    created_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    cleared_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cleared_at = models.DateTimeField(null=True, blank=True)
    clear_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(blocks_dispatch=True) | Q(blocks_handover=True),
                                   name="hold_blocks_something"),
        ]


class AssistedVerification(models.Model):
    """Supervisor-conducted ownership verification when the guest cannot use the code (docs/01 §6)."""

    class Method(models.TextChoices):
        IN_PERSON_CHECK = "in_person_check"
        KNOWN_GUEST = "known_guest"
        OTHER = "other"

    ticket = models.ForeignKey("ops.Ticket", on_delete=models.PROTECT, related_name="assisted_verifications")
    verified_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    method = models.CharField(max_length=20, choices=Method.choices)
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
