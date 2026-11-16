from django.db import models
from django.db.models import Q


class WebhookInbox(models.Model):
    """Durable receipt of provider webhooks, stored before acknowledgement (docs/03)."""

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED"
        PROCESSING = "PROCESSING"
        PROCESSED = "PROCESSED"
        DEAD = "DEAD"

    provider = models.CharField(max_length=20, default="whatsapp")
    event_key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=10)  # message | status
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "received_at"])]


class MessageOutbox(models.Model):
    """Transactional outbox. A queued message is not a delivered message."""

    class Status(models.TextChoices):
        PENDING = "PENDING"
        SENDING = "SENDING"
        SENT = "SENT"
        DELIVERED = "DELIVERED"
        READ = "READ"
        FAILED = "FAILED"
        DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
        DEAD = "DEAD"
        OBSOLETE = "OBSOLETE"  # no longer true when it would be sent (e.g. an expired offer); never delivered

    kind = models.CharField(max_length=40)
    staff = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    binding = models.ForeignKey("ops.GuestBinding", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    ticket = models.ForeignKey("ops.Ticket", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    task = models.ForeignKey("ops.Task", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_phone_enc = models.TextField(blank=True)  # replies to senders with no binding (no personal data shared)
    to_phone_hash = models.CharField(max_length=64, blank=True)
    template = models.CharField(max_length=60)
    params = models.JSONField(default=dict)
    buttons = models.JSONField(default=list)  # [[payload, catalogue button key], ...]
    language = models.CharField(max_length=2, default="ar")
    dedupe_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    failure_class = models.CharField(max_length=20, blank=True)  # permanent | exhausted
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    lease_until = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_via = models.CharField(max_length=10, blank=True)  # template | session
    provider_message_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(staff__isnull=False) | Q(binding__isnull=False) | ~Q(to_phone_enc=""),
                name="outbox_has_recipient",
            )
        ]


class MessageStatusEvent(models.Model):
    outbox = models.ForeignKey(MessageOutbox, null=True, on_delete=models.PROTECT, related_name="status_events")
    provider_message_id = models.CharField(max_length=128)
    status = models.CharField(max_length=20)
    provider_timestamp = models.BigIntegerField()
    errors = models.JSONField(default=list)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider_message_id", "status", "provider_timestamp"], name="uniq_status_transition"
            )
        ]


class Conversation(models.Model):
    """Explicit interaction context per WhatsApp party (staff or guest phone)."""

    party_key = models.CharField(max_length=80, unique=True)  # staff:<id> | guest:<phone hash or bsuid>
    step = models.CharField(max_length=40, default="idle")
    ticket = models.ForeignKey("ops.Ticket", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    data = models.JSONField(default=dict)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SimulatedMessage(models.Model):
    """Local simulator inbox/outbox. Synthetic only; results labelled SIMULATED."""

    direction = models.CharField(max_length=3)  # in | out
    phone = models.CharField(max_length=20)
    kind = models.CharField(max_length=20)
    body = models.TextField(blank=True)
    buttons = models.JSONField(default=list)  # [[payload, title], ...]
    provider_message_id = models.CharField(max_length=128, blank=True)
    outbox_id = models.BigIntegerField(null=True, blank=True)
    media_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SimulatedMedia(models.Model):
    media_id = models.CharField(max_length=64, unique=True)
    content = models.BinaryField()
    content_type = models.CharField(max_length=40)


class SimulatorControl(models.Model):
    """Failure injection for the fake transport (tests and demo only).

    One-shot modes (transient | permanent | unknown) apply to the next send. The persistent "down" mode simulates a
    provider outage: every send fails transiently and simulated inbound messages are refused until it is cleared."""

    mode = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def set_next(cls, mode: str) -> None:
        cls.objects.create(mode=mode)

    @classmethod
    def set_outage(cls, active: bool) -> None:
        if active and not cls.outage_active():
            cls.objects.create(mode="down")
        elif not active:
            cls.objects.filter(mode="down").delete()

    @classmethod
    def outage_active(cls) -> bool:
        return cls.objects.filter(mode="down").exists()

    @classmethod
    def take(cls) -> str | None:
        from django.db import transaction

        with transaction.atomic():
            row = (cls.objects.select_for_update(skip_locked=True, no_key=True).exclude(mode="down")
                   .order_by("id").first())
            if row is None:
                return None
            mode = row.mode
            row.delete()
            return mode
