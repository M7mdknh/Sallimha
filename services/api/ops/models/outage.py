"""Outage records (ADR-0008): declared WhatsApp outages and recorded whole-system outages, and the controlled
reconciliation of what happened during a whole-system outage."""

from django.db import models
from django.db.models import F, Q


class OutageWindow(models.Model):
    class Kind(models.TextChoices):
        WHATSAPP = "WHATSAPP"  # declared live by a supervisor; enables relayed actions while open
        SYSTEM = "SYSTEM"  # recorded afterwards by a manager (start and end); enables reconciliation

    org = models.ForeignKey("ops.Organization", on_delete=models.PROTECT, related_name="outages")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=200)
    declared_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    declared_at = models.DateTimeField(auto_now_add=True)  # entry time, separate from the outage times
    ended_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    end_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org"], condition=Q(kind="WHATSAPP", ended_at__isnull=True),
                                    name="one_open_whatsapp_outage_per_org"),
            models.CheckConstraint(condition=Q(ended_at__isnull=True) | Q(ended_at__gt=F("started_at")),
                                   name="outage_ends_after_it_starts"),
            models.CheckConstraint(condition=~Q(kind="SYSTEM") | Q(ended_at__isnull=False),
                                   name="system_outage_recorded_with_end"),
        ]


class Reconciliation(models.Model):
    """What happened during a whole-system outage, entered afterwards. `occurred_at` is when it actually happened;
    `recorded_at` is when it was entered. One record per ticket and kind: completion is never recorded twice."""

    class Kind(models.TextChoices):
        HANDOVER = "HANDOVER"
        INTAKE = "INTAKE"

    ticket = models.ForeignKey("ops.Ticket", on_delete=models.PROTECT, related_name="reconciliations")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    outage = models.ForeignKey(OutageWindow, on_delete=models.PROTECT, related_name="reconciliations")
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    responsible = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    verified_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    method = models.CharField(max_length=20, blank=True)  # AssistedVerification.Method for handovers
    evidence = models.TextField()
    reason = models.CharField(max_length=200)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ticket", "kind"], name="one_reconciliation_per_ticket_kind")]
