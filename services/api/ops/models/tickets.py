"""Vehicle tickets, guest contact, credentials, evidence and key custody (docs/02)."""

from django.db import models
from django.db.models import Q


class Ticket(models.Model):
    class State(models.TextChoices):
        RECEIVED = "RECEIVED"
        PARKED = "PARKED"
        RETRIEVING = "RETRIEVING"
        READY = "READY"
        DELIVERED = "DELIVERED"
        CANCELLED = "CANCELLED"
        UNCLAIMED = "UNCLAIMED"

    class Contact(models.TextChoices):
        UNCONFIRMED = "UNCONFIRMED"
        CONFIRMED_IN_PERSON = "CONFIRMED_IN_PERSON"
        CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
        ASSISTED_FALLBACK = "ASSISTED_FALLBACK"

    event = models.ForeignKey("ops.Event", on_delete=models.PROTECT, related_name="tickets")
    display_number = models.PositiveIntegerField()
    state = models.CharField(max_length=12, choices=State.choices, default=State.RECEIVED)
    version = models.PositiveIntegerField(default=1)
    contact_state = models.CharField(max_length=20, choices=Contact.choices, default=Contact.UNCONFIRMED)
    guest_language = models.CharField(max_length=2, default="ar")

    class PlateKind(models.TextChoices):
        SAUDI = "SAUDI"   # three letters and 1-4 digits, kept in the script entered (ADR-0013)
        OTHER = "OTHER"   # international, diplomatic, temporary: kept as typed
        NONE = "NONE"     # missing or unreadable: description and reason required

    class LocationSource(models.TextChoices):
        GPS = "gps"       # the browser's geolocation beside the car, with its reported accuracy
        PIN = "pin"       # the valet tapped or dragged the map pin

    vehicle_plate = models.CharField(max_length=40, blank=True)
    plate_kind = models.CharField(max_length=5, choices=PlateKind.choices, blank=True)
    plate_key = models.CharField(max_length=40, blank=True, db_index=True,
                                 help_text="Search key (digits normalised, Saudi letters in Latin); never displayed")
    vehicle_description = models.CharField(max_length=200, blank=True)
    vehicle_raw = models.TextField(blank=True)
    vehicle_exception_reason = models.CharField(max_length=200, blank=True)
    photos_exception_reason = models.CharField(max_length=200, blank=True)

    registered_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="registered_tickets")
    parked_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="parked_tickets"
    )
    delivered_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="delivered_tickets"
    )
    location_zone = models.ForeignKey("ops.ParkingZone", null=True, blank=True, on_delete=models.PROTECT)
    location_detail = models.CharField(max_length=80, blank=True)
    location_floor = models.CharField(max_length=20, blank=True)
    location_note = models.CharField(max_length=120, blank=True, help_text="Short description, e.g. beside pillar 12")
    # A confirmed pin only (ADR-0013): never the venue centre, never invented. Set or cleared with zone and spot.
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_source = models.CharField(max_length=3, choices=LocationSource.choices, blank=True)
    location_accuracy_m = models.FloatField(null=True, blank=True)
    location_device_at = models.DateTimeField(null=True, blank=True, help_text="Capture time reported by the device")
    location_recorded_at = models.DateTimeField(null=True, blank=True, help_text="Server time the pin was saved")

    created_at = models.DateTimeField()
    phone_confirmed_at = models.DateTimeField(null=True, blank=True)
    parking_started_at = models.DateTimeField(null=True, blank=True)
    parked_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_tickets"
    )
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "display_number"], name="uniq_display_number_per_event"),
            models.UniqueConstraint(fields=["event", "id"], name="uniq_ticket_event_id"),
            # A pin is whole or absent: both coordinates and its source together; a GPS fix carries its accuracy.
            models.CheckConstraint(
                condition=(Q(location_lat__isnull=True, location_lng__isnull=True, location_source="")
                           | (Q(location_lat__isnull=False, location_lng__isnull=False)
                              & Q(location_source__in=["gps", "pin"]))),
                name="location_pin_whole"),
            models.CheckConstraint(
                condition=~Q(location_source="gps") | Q(location_accuracy_m__isnull=False),
                name="location_gps_has_accuracy"),
            # Cancellation is only possible before parking starts (ADR-0005 C4).
            models.CheckConstraint(
                condition=~Q(state="CANCELLED") | Q(cancelled_at__isnull=False, parking_started_at__isnull=True),
                name="cancelled_only_before_parking",
            ),
            models.CheckConstraint(
                condition=~Q(state__in=["PARKED", "RETRIEVING", "READY", "DELIVERED"])
                | Q(parked_at__isnull=False, location_zone__isnull=False, parked_by__isnull=False),
                name="parked_states_have_location",
            ),
            models.CheckConstraint(
                condition=~Q(state="DELIVERED") | Q(delivered_at__isnull=False, delivered_by__isnull=False),
                name="delivered_has_actor_time",
            ),
        ]


class GuestBinding(models.Model):
    """Who may act for a ticket. A correction creates a new revision and revokes the old one."""

    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="bindings")
    revision = models.PositiveIntegerField(default=1)
    phone_enc = models.TextField()
    phone_hash = models.CharField(max_length=64, db_index=True)
    phone_masked = models.CharField(max_length=32)
    wa_user_id = models.CharField(max_length=128, blank=True, db_index=True)
    matched_via = models.CharField(max_length=20, blank=True)  # phone | context_token
    language = models.CharField(max_length=2, default="ar")
    consent_at = models.DateTimeField()
    confirmed_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    receipt_confirmed = models.BooleanField(null=True, blank=True)
    receipt_answered_by = models.ForeignKey(
        "ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    receipt_answered_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)  # customer-service window
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ticket", "revision"], name="uniq_binding_revision"),
            models.UniqueConstraint(
                fields=["ticket"], condition=Q(revoked_at__isnull=True), name="one_active_binding_per_ticket"
            ),
        ]


class ActionToken(models.Model):
    """Opaque, single-use action reference. Only the keyed hash is stored."""

    token_hash = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=32)
    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    binding = models.ForeignKey(GuestBinding, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    staff = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    task = models.ForeignKey("ops.Task", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    generation = models.PositiveIntegerField(null=True, blank=True)
    data = models.JSONField(default=dict)
    expires_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GuestMessage(models.Model):
    """A customer's free-text WhatsApp message on an active ticket (ADR-0011): kept so the event team can see what
    the customer asked. Not a chat: Sallimha does not send typed replies."""

    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="guest_messages")
    binding = models.ForeignKey(GuestBinding, on_delete=models.PROTECT, related_name="+")
    text = models.CharField(max_length=500)
    received_at = models.DateTimeField()
    provider_message_id = models.CharField(max_length=128, unique=True)


class CollectionCode(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="codes")
    binding = models.ForeignKey(GuestBinding, on_delete=models.PROTECT, related_name="+")
    verifier = models.CharField(max_length=64)
    delivery_enc = models.TextField(blank=True)  # wiped once the ready message is sent
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ticket"],
                condition=Q(consumed_at__isnull=True, revoked_at__isnull=True),
                name="one_live_code_per_ticket",
            )
        ]


class Media(models.Model):
    class Kind(models.TextChoices):
        INTAKE = "INTAKE"
        INCIDENT = "INCIDENT"

    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.PROTECT, related_name="media")
    incident_id = models.BigIntegerField(null=True, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    storage_key = models.CharField(max_length=200, unique=True)
    sha256 = models.CharField(max_length=64)
    content_type = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    received_at = models.DateTimeField()
    capture_time = models.DateTimeField(null=True, blank=True)  # never inferred from upload time
    provider_media_id = models.CharField(max_length=128, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # retention


class KeyOccupancy(models.Model):
    """A key on a venue hook. Survives event closure until explicitly released (ADR-0005 C1)."""

    key_station = models.ForeignKey("ops.KeyStation", on_delete=models.PROTECT, related_name="occupancies")
    hook_number = models.PositiveIntegerField()
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="key_occupancies")
    occupied_at = models.DateTimeField()
    occupied_by = models.ForeignKey("ops.Staff", on_delete=models.PROTECT, related_name="+")
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey("ops.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    release_reason = models.CharField(max_length=40, blank=True)  # delivered | relocated | carryover_release

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key_station", "hook_number"],
                condition=Q(released_at__isnull=True),
                name="one_key_per_hook",
            ),
            models.UniqueConstraint(
                fields=["ticket"], condition=Q(released_at__isnull=True), name="one_key_location_per_ticket"
            ),
            models.CheckConstraint(condition=Q(hook_number__gte=1), name="hook_number_positive"),
        ]
