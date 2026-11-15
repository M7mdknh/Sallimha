"""Console API contract. Every endpoint validates input and shapes output with these serializers; the
OpenAPI document (contracts/openapi.yaml) and the web app's TypeScript types are generated from them."""

from rest_framework import serializers

from ops.models import Role

ROLES = Role.values
TICKET_STATES = ["RECEIVED", "PARKED", "RETRIEVING", "READY", "DELIVERED", "CANCELLED", "UNCLAIMED"]
REQUEST_STATES = ["WAITING_FOR_PARKING", "QUEUED", "OFFERED", "ACCEPTED", "COMPLETED", "WITHDRAWN"]
CONTACT_STATES = ["UNCONFIRMED", "CONFIRMED_IN_PERSON", "CORRECTION_REQUIRED", "ASSISTED_FALLBACK"]
EVENT_STATUSES = ["OPEN", "CLOSED"]
TEAM_STATUSES = ["available", "busy", "unavailable"]
INCIDENT_STATUSES = ["OPEN", "IN_REVIEW", "RESOLVED"]


# --- shared ---------------------------------------------------------------------------------------

class ErrorResponse(serializers.Serializer):
    code = serializers.CharField(help_text="Stable refusal code for the UI (e.g. confirmation_required)")
    fields = serializers.DictField(child=serializers.ListField(child=serializers.CharField()), required=False)


class OkResponse(serializers.Serializer):
    ok = serializers.BooleanField()


class IdResponse(serializers.Serializer):
    id = serializers.IntegerField()


# --- auth -----------------------------------------------------------------------------------------

class CsrfResponse(serializers.Serializer):
    csrfToken = serializers.CharField()  # noqa: N815 — wire name


class LoginRequest(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=512, trim_whitespace=False)
    otp = serializers.CharField(max_length=10, required=False, allow_blank=True)


class LoginResponse(serializers.Serializer):
    ok = serializers.BooleanField()
    role = serializers.ChoiceField(choices=ROLES, required=False)
    mfa_required = serializers.BooleanField(required=False)


class MeResponse(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLES)
    language = serializers.CharField()


# --- events and live view -------------------------------------------------------------------------

class EventSummary(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    venue = serializers.CharField()
    status = serializers.ChoiceField(choices=EVENT_STATUSES)
    starts_at = serializers.DateTimeField()


class EventBrief(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=EVENT_STATUSES)
    venue = serializers.CharField()


class Health(serializers.Serializer):
    worker = serializers.ChoiceField(choices=["ok", "stale", "missing", "unknown"])
    whatsapp = serializers.ChoiceField(choices=["simulated", "configured", "not_configured"])


class AttentionItem(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    severity = serializers.ChoiceField(choices=["warning", "critical"])
    created_at = serializers.DateTimeField()
    ticket = serializers.CharField(allow_null=True)
    ticket_id = serializers.IntegerField(allow_null=True)


class LiveRequest(serializers.Serializer):
    request_id = serializers.IntegerField()
    ticket_id = serializers.IntegerField()
    ticket = serializers.CharField()
    vehicle = serializers.CharField()
    state = serializers.ChoiceField(choices=REQUEST_STATES)
    ticket_state = serializers.ChoiceField(choices=TICKET_STATES)
    requested_at = serializers.DateTimeField()
    elapsed_s = serializers.IntegerField()
    assignee = serializers.CharField(allow_null=True)
    location = serializers.CharField(allow_blank=True)
    hook = serializers.IntegerField(allow_null=True)
    failed_offers = serializers.IntegerField()


class TeamTask(serializers.Serializer):
    type = serializers.ChoiceField(choices=["INTAKE", "RETRIEVAL", "RELOCATION"])
    ticket = serializers.CharField()
    ticket_id = serializers.IntegerField()
    status = serializers.CharField()


class TeamMember(serializers.Serializer):
    staff_id = serializers.IntegerField()
    shift_id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLES)
    status = serializers.ChoiceField(choices=TEAM_STATUSES)
    break_pending = serializers.BooleanField()
    task = TeamTask(allow_null=True)
    idle_since = serializers.DateTimeField(allow_null=True)


class StaffBrief(serializers.Serializer):
    staff_id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLES)


class LiveSnapshot(serializers.Serializer):
    event = EventBrief()
    generated_at = serializers.DateTimeField()
    health = Health()
    attention = AttentionItem(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())
    requests = LiveRequest(many=True)
    team = TeamMember(many=True)
    not_started = StaffBrief(many=True)


# --- tickets ---------------------------------------------------------------------------------------

class TicketRequestBrief(serializers.Serializer):
    id = serializers.IntegerField()
    state = serializers.ChoiceField(choices=REQUEST_STATES)
    requested_at = serializers.DateTimeField()


class MediaBrief(serializers.Serializer):
    id = serializers.IntegerField()
    received_at = serializers.DateTimeField()
    kind = serializers.ChoiceField(choices=["INTAKE", "INCIDENT"])


class TimelineEntry(serializers.Serializer):
    at = serializers.DateTimeField()
    action = serializers.CharField()
    actor = serializers.CharField()


class HoldBrief(serializers.Serializer):
    id = serializers.IntegerField()
    reason = serializers.CharField()
    blocks_dispatch = serializers.BooleanField()
    blocks_handover = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class IncidentBrief(serializers.Serializer):
    id = serializers.IntegerField()
    category = serializers.CharField()
    status = serializers.ChoiceField(choices=INCIDENT_STATUSES)
    created_at = serializers.DateTimeField()


class TicketDetail(serializers.Serializer):
    id = serializers.IntegerField()
    ticket = serializers.CharField()
    event_id = serializers.IntegerField()
    state = serializers.ChoiceField(choices=TICKET_STATES)
    contact_state = serializers.ChoiceField(choices=CONTACT_STATES)
    phone_masked = serializers.CharField(allow_null=True)
    vehicle = serializers.CharField()
    plate = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    hook = serializers.IntegerField(allow_null=True)
    registered_by = serializers.CharField()
    parked_by = serializers.CharField(allow_null=True)
    assignee = serializers.CharField(allow_null=True)
    parking_started = serializers.BooleanField()
    request = TicketRequestBrief(allow_null=True)
    media = MediaBrief(many=True)
    holds = HoldBrief(many=True)
    incidents = IncidentBrief(many=True)
    timeline = TimelineEntry(many=True)
    allowed_actions = serializers.ListField(child=serializers.CharField(),
                                            help_text="Exception actions the server will accept now")


class StartShiftRequest(serializers.Serializer):
    staff_id = serializers.IntegerField()


class ShiftResponse(serializers.Serializer):
    id = serializers.IntegerField()
    staff_id = serializers.IntegerField(required=False)
    ended = serializers.BooleanField(required=False)


class AlertAckResponse(serializers.Serializer):
    id = serializers.IntegerField()
    acknowledged = serializers.BooleanField()


class ReasonRequest(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class CancelRequest(ReasonRequest):
    guest_has_vehicle_and_keys = serializers.BooleanField()


class TicketStateResponse(serializers.Serializer):
    id = serializers.IntegerField()
    state = serializers.ChoiceField(choices=TICKET_STATES)


class RequestStateResponse(serializers.Serializer):
    request_id = serializers.IntegerField()
    state = serializers.ChoiceField(choices=REQUEST_STATES)


class WithdrawWithCustodyRequest(ReasonRequest):
    zone_code = serializers.CharField(max_length=20)
    detail = serializers.CharField(max_length=80, required=False, allow_blank=True)
    hook_number = serializers.IntegerField(min_value=1)


class TransferResponse(serializers.Serializer):
    transfer_id = serializers.IntegerField()
    state = serializers.CharField(required=False)


class CustodyTransferRequest(ReasonRequest):
    to_staff_id = serializers.IntegerField()
    vehicle_location = serializers.CharField(max_length=160)
    key_location = serializers.CharField(max_length=160)


class IntakeTransferRequest(ReasonRequest):
    to_staff_id = serializers.IntegerField()


class CorrectPhoneRequest(ReasonRequest):
    phone = serializers.CharField(max_length=40)


class CorrectPhoneResponse(serializers.Serializer):
    masked = serializers.CharField()
    revision = serializers.IntegerField()


class ConfirmReceiptRequest(serializers.Serializer):
    received = serializers.BooleanField()


class ContactStateResponse(serializers.Serializer):
    id = serializers.IntegerField()
    contact_state = serializers.ChoiceField(choices=CONTACT_STATES)


class ExceptIntakeRequest(ReasonRequest):
    kind = serializers.ChoiceField(choices=["photos", "vehicle"])


# --- development simulator --------------------------------------------------------------------------

class SimPhone(serializers.Serializer):
    phone = serializers.CharField()
    label = serializers.CharField()
    role = serializers.CharField()


class SimButton(serializers.ListField):
    child = serializers.CharField()


class SimMessage(serializers.Serializer):
    id = serializers.IntegerField()
    direction = serializers.ChoiceField(choices=["in", "out"])
    body = serializers.CharField(allow_blank=True)
    buttons = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    kind = serializers.CharField()
    provider_message_id = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class SimSendRequest(serializers.Serializer):
    phone = serializers.RegexField(r"^\+\d{8,15}$")
    text = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    button_payload = serializers.CharField(required=False, max_length=256)
    button_title = serializers.CharField(required=False, max_length=40)
    context_id = serializers.CharField(required=False, max_length=128)
    photo = serializers.BooleanField(required=False)


class SimSendResponse(serializers.Serializer):
    ok = serializers.BooleanField()
    simulated = serializers.BooleanField()
