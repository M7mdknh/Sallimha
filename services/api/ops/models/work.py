"""Tasks, retrieval requests, offers, custody, ratings and alerts (docs/02, docs/03)."""

from django.db import models
from django.db.models import Q

LIVE_TASK_STATUSES = ("RESERVED", "OFFERED", "ACCEPTED")
OPEN_REQUEST_STATES = ("WAITING_FOR_PARKING", "QUEUED", "OFFERED", "ACCEPTED")


class Task(models.Model):
    class Type(models.TextChoices):
        INTAKE = "INTAKE"
        RETRIEVAL = "RETRIEVAL"
        RELOCATION = "RELOCATION"

    class Status(models.TextChoices):
        RESERVED = "RESERVED"
        OFFERED = "OFFERED"
        ACCEPTED = "ACCEPTED"
        COMPLETED = "COMPLETED"
        RELEASED = "RELEASED"  # unaccepted offer expired/declined/superseded, or custody resolved
        CANCELLED = "CANCELLED"

    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="tasks")
    ticket = models.ForeignKey("ops.Ticket", on_delete=models.PROTECT, related_name="tasks")
    type = models.CharField(max_length=10, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    assignee = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="tasks")
    generation = models.PositiveIntegerField(default=1)
    request = models.ForeignKey(
        "ops.RetrievalRequest", null=True, blank=True, on_delete=models.PROTECT, related_name="tasks"
    )
    reserved_at = models.DateTimeField()
    offer_sent_at = models.DateTimeField(null=True, blank=True)
    offer_deadline = models.DateTimeField(null=True, blank=True)
    hard_deadline = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            # ADR-0003 #3: one live capacity-consuming task per valet (offers count).
            models.UniqueConstraint(
                fields=["assignee"], condition=Q(status__in=LIVE_TASK_STATUSES), name="one_live_task_per_staff"
            ),
            # ADR-0003 #4: one live movement task per vehicle.
            models.UniqueConstraint(
                fields=["ticket"], condition=Q(status__in=LIVE_TASK_STATUSES), name="one_live_task_per_ticket"
            ),
        ]


class RetrievalRequest(models.Model):
    class State(models.TextChoices):
        WAITING_FOR_PARKING = "WAITING_FOR_PARKING"
        QUEUED = "QUEUED"
        OFFERED = "OFFERED"
        ACCEPTED = "ACCEPTED"
        COMPLETED = "COMPLETED"
        WITHDRAWN = "WITHDRAWN"

    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="requests")
    ticket = models.ForeignKey("ops.Ticket", on_delete=models.PROTECT, related_name="requests")
    binding = models.ForeignKey("ops.GuestBinding", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=20, choices=State.choices)
    requested_at = models.DateTimeField()  # original time; never reset by reassignment
    eligible_at = models.DateTimeField(null=True, blank=True)
    requested_via = models.CharField(max_length=20)  # guest_whatsapp | assisted
    assisted_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    failed_offers = models.PositiveIntegerField(default=0)
    current_task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    withdraw_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            # ADR-0003 #5: at most one open retrieval request per ticket.
            models.UniqueConstraint(
                fields=["ticket"], condition=Q(state__in=OPEN_REQUEST_STATES), name="one_open_request_per_ticket"
            ),
            models.CheckConstraint(
                condition=~Q(state="WITHDRAWN") | Q(withdrawn_at__isnull=False),
                name="withdrawn_has_time",
            ),
        ]


class AssignmentAttempt(models.Model):
    class Outcome(models.TextChoices):
        PENDING = "PENDING"
        ACCEPTED = "ACCEPTED"
        DECLINED = "DECLINED"
        EXPIRED = "EXPIRED"
        SEND_FAILED = "SEND_FAILED"
        SUPERSEDED = "SUPERSEDED"

    request = models.ForeignKey(RetrievalRequest, on_delete=models.PROTECT, related_name="attempts")
    task = models.OneToOneField(Task, on_delete=models.PROTECT, related_name="attempt")
    candidate = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    generation = models.PositiveIntegerField()
    offered_at = models.DateTimeField()
    outcome = models.CharField(max_length=12, choices=Outcome.choices, default=Outcome.PENDING)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "generation"], name="uniq_attempt_generation")
        ]


class CustodyTransfer(models.Model):
    class Kind(models.TextChoices):
        INTAKE_HANDOFF = "INTAKE_HANDOFF"
        RETRIEVAL_TRANSFER = "RETRIEVAL_TRANSFER"
        WITHDRAWAL_RESOLUTION = "WITHDRAWAL_RESOLUTION"

    ticket = models.ForeignKey("ops.Ticket", on_delete=models.PROTECT, related_name="custody_transfers")
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    from_staff = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_staff = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    vehicle_location = models.CharField(max_length=160)
    key_location = models.CharField(max_length=160)
    reason = models.CharField(max_length=200)
    initiated_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    acknowledged_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Rating(models.Model):
    class Value(models.TextChoices):
        EXCELLENT = "EXCELLENT"
        OKAY = "OKAY"
        POOR = "POOR"

    ticket = models.OneToOneField("ops.Ticket", on_delete=models.PROTECT, related_name="rating")
    delivering_valet = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="ratings")
    value = models.CharField(max_length=10, choices=Value.choices)
    source_message_id = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Alert(models.Model):
    """Supervisor attention item. `dedupe_key` makes raising idempotent."""

    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="alerts")
    kind = models.CharField(max_length=40)
    severity = models.CharField(max_length=10, default="warning")  # warning | critical
    ticket = models.ForeignKey("ops.Ticket", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    detail = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
