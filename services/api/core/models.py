from django.db import models


class WorkerHeartbeat(models.Model):
    worker_id = models.CharField(max_length=64, unique=True)
    beat_at = models.DateTimeField()


class AuditEvent(models.Model):
    """Application-append-only audit trail (UPDATE/DELETE blocked by trigger; see ADR-0003)."""

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True)
    actor_label = models.CharField(max_length=120)
    channel = models.CharField(max_length=20)  # console | whatsapp | worker | system
    event_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    entity_type = models.CharField(max_length=40, blank=True)
    entity_id = models.BigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=80)
    summary = models.JSONField(default=dict)
    correlation_id = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=["entity_type", "entity_id"])]


class IdempotencyRecord(models.Model):
    scope = models.CharField(max_length=80)
    key = models.CharField(max_length=128)
    # SHA-256 of the canonical request body: a key reused for a different body is refused, not replayed.
    fingerprint = models.CharField(max_length=64, blank=True, default="")
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "key"], name="uniq_idempotency_scope_key")]


class LoginThrottle(models.Model):
    """Atomic per-key failure counters for console login (keyed hashes only; no usernames or IPs in clear).

    Keys: (IP, username) pair — hard limit; IP alone — password-spraying limit. There is deliberately no
    username-only hard lock, so nobody can lock an account out by submitting its username from elsewhere.
    """

    key_hash = models.CharField(max_length=64, unique=True)
    window_start = models.DateTimeField()
    failures = models.PositiveIntegerField(default=0)


class LoginKnownNetwork(models.Model):
    """(account, network) pairs with a recent successful login; they keep the normal limit under attack."""

    key_hash = models.CharField(max_length=64, unique=True)
    last_success_at = models.DateTimeField()
