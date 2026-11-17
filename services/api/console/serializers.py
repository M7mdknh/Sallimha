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
CARRYOVER_STATUSES = ["PROPOSED", "APPROVED", "RELEASED"]
WHATSAPP_STATUSES = ["simulated", "configured", "not_configured", "degraded"]
OUTBOX_ATTENTION_STATUSES = ["DEAD", "DELIVERY_UNKNOWN"]


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
    simulator = serializers.BooleanField(help_text="True only in local/test builds; the UI hides it otherwise")


# --- events and live view -------------------------------------------------------------------------

class EventSummary(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    venue = serializers.CharField()
    status = serializers.ChoiceField(choices=EVENT_STATUSES)
    starts_at = serializers.DateTimeField()
    time_zone = serializers.CharField(help_text="The venue's IANA time zone; console times are shown in it")


class EventBrief(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=EVENT_STATUSES)
    venue = serializers.CharField()
    time_zone = serializers.CharField()


class Health(serializers.Serializer):
    worker = serializers.ChoiceField(choices=["ok", "stale", "missing", "unknown"])
    whatsapp = serializers.ChoiceField(choices=WHATSAPP_STATUSES)


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
    assisted = serializers.BooleanField(help_text="Device not working: a supervisor records their actions")
    done = serializers.IntegerField(help_text="Tasks completed in this shift")


class StaffBrief(serializers.Serializer):
    staff_id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLES)


class OutageBrief(serializers.Serializer):
    id = serializers.IntegerField()
    since = serializers.DateTimeField()
    declared_by = serializers.CharField()
    reason = serializers.CharField()


class LiveSnapshot(serializers.Serializer):
    event = EventBrief()
    outage = OutageBrief(allow_null=True, help_text="Declared customer WhatsApp outage")
    generated_at = serializers.DateTimeField()
    health = Health()
    attention = AttentionItem(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())
    requests = LiveRequest(many=True)
    team = TeamMember(many=True)
    not_started = StaffBrief(many=True)
    addable = StaffBrief(many=True, help_text="Organisation valets not yet on this event who can start a shift")


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


class MoveBrief(serializers.Serializer):
    status = serializers.ChoiceField(choices=["OFFERED", "ACCEPTED"])
    valet = serializers.CharField()


class GuestMessageOut(serializers.Serializer):
    text = serializers.CharField()
    received_at = serializers.DateTimeField()


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
    move = MoveBrief(allow_null=True, help_text="A supervisor-initiated relocation in progress")
    offered_to = serializers.CharField(allow_null=True, help_text="Valet the system offered the open task to")
    timeline = TimelineEntry(many=True)
    allowed_actions = serializers.ListField(child=serializers.CharField(),
                                            help_text="Exception actions the server will accept now")
    primary_action = serializers.CharField(allow_null=True, help_text="The one action to offer first, if any")
    guest_messages = GuestMessageOut(many=True, help_text="What the customer wrote on WhatsApp (stored here)")
    can_contact = serializers.BooleanField(help_text="A number exists and may be opened (audited)")


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


# --- Phase 2: exceptions, incidents, directory, configuration, reports -----------------------------

INCIDENT_CATEGORIES = ["missing_vehicle", "key_issue", "damage", "identity_dispute", "notification_failure",
                       "operational_delay", "complaint"]


class OpenIncidentRequest(serializers.Serializer):
    category = serializers.ChoiceField(choices=INCIDENT_CATEGORIES)
    description = serializers.CharField(max_length=2000)


class PlaceHoldRequest(ReasonRequest):
    blocks_dispatch = serializers.BooleanField()
    blocks_handover = serializers.BooleanField()


class ClearHoldRequest(ReasonRequest):
    hold_id = serializers.IntegerField()


class AssistedHandoverRequest(ReasonRequest):
    method = serializers.ChoiceField(choices=["in_person_check", "known_guest", "other"])


class RelocateStartRequest(ReasonRequest):
    to_staff_id = serializers.IntegerField()


class RelocateCompleteRequest(serializers.Serializer):
    zone_code = serializers.CharField(max_length=20)
    detail = serializers.CharField(max_length=80, required=False, allow_blank=True)
    hook_number = serializers.IntegerField(min_value=1)
    confirmed_via = serializers.ChoiceField(choices=["in_person", "radio"],
                                            help_text="How the supervisor confirmed the completed move")


class RelocateCancelRequest(ReasonRequest):
    car_returned = serializers.BooleanField(
        help_text="Required true once a valet accepted: car and key are back at the recorded location and hook")


class ProposeUnclaimedRequest(serializers.Serializer):
    custodian = serializers.CharField(max_length=160)
    plan = serializers.CharField(max_length=2000)


class ReleaseCarryoverRequest(serializers.Serializer):
    method = serializers.ChoiceField(choices=["collected_verified", "moved_to_storage", "other"])
    note = serializers.CharField(max_length=2000)


class IncidentSummary(serializers.Serializer):
    id = serializers.IntegerField()
    category = serializers.ChoiceField(choices=INCIDENT_CATEGORIES)
    status = serializers.ChoiceField(choices=INCIDENT_STATUSES)
    description = serializers.CharField()
    ticket = serializers.CharField(allow_null=True)
    ticket_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()


class IncidentNoteOut(serializers.Serializer):
    author = serializers.CharField()
    text = serializers.CharField()
    created_at = serializers.DateTimeField()


class IncidentDetail(IncidentSummary):
    notes = IncidentNoteOut(many=True)
    resolution = serializers.CharField(allow_blank=True)
    resolved_by = serializers.CharField(allow_null=True)
    resolved_at = serializers.DateTimeField(allow_null=True)


class NoteRequest(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class ResolveRequest(serializers.Serializer):
    outcome = serializers.CharField(max_length=2000)


class AdminAccessRecord(serializers.Serializer):
    """The last time an admin's sign-in was set up or recovered by the controlled procedure, from the server."""

    at = serializers.DateTimeField()
    requested_by = serializers.CharField(allow_null=True)
    approved_by = serializers.CharField(allow_null=True)
    first_admin = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)


class StaffRow(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    phone_masked = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLES)
    enabled = serializers.BooleanField()
    username = serializers.CharField(allow_null=True)
    mfa_enrolled = serializers.BooleanField()
    mfa_locked = serializers.BooleanField()
    can_sign_in = serializers.BooleanField(help_text="The person has set their own password")
    setup_pending = serializers.BooleanField(help_text="A one-time setup code is waiting to be used")
    event_ids = serializers.ListField(child=serializers.IntegerField(), help_text="Operations they are on")
    admin_access = AdminAccessRecord(allow_null=True, help_text="Admins: the last controlled access (ADR-0012)")


class CreateStaffRequest(serializers.Serializer):
    """No password: the person sets their own with a one-time setup code (ADR-0011)."""

    full_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=40)
    role = serializers.ChoiceField(choices=ROLES)
    username = serializers.CharField(max_length=150, required=False, allow_blank=True,
                                     help_text="Sign-in name; the mobile number when left empty")
    event_id = serializers.IntegerField(required=False, allow_null=True, help_text="Also put them on this team")


class RoleRequest(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLES)


class VenueRow(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    time_zone = serializers.CharField()
    zones = serializers.ListField(child=serializers.CharField())
    key_hooks = serializers.IntegerField()


class CreateEventRequest(serializers.Serializer):
    venue_id = serializers.IntegerField()
    name = serializers.CharField(max_length=160)
    starts_at_local = serializers.CharField(max_length=32,
                                            help_text="Venue wall-clock time without an offset, e.g. 2026-12-01T19:00")


class StageStat(serializers.Serializer):
    count = serializers.IntegerField()
    median_s = serializers.IntegerField(allow_null=True)
    p95_s = serializers.IntegerField(allow_null=True)


class Stages(serializers.Serializer):
    request_to_accept = StageStat()
    accept_to_ready = StageStat()
    ready_to_delivered = StageStat()
    received_to_parked = StageStat()


class HoursRow(serializers.Serializer):
    staff_id = serializers.IntegerField()
    name = serializers.CharField()
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    worked_s = serializers.IntegerField(allow_null=True)
    break_s = serializers.IntegerField()


class EventReport(serializers.Serializer):
    event_id = serializers.IntegerField()
    outcomes = serializers.DictField(child=serializers.IntegerField())
    stages = Stages()
    oldest_queued_at = serializers.DateTimeField(allow_null=True)
    unresolved_incidents = serializers.IntegerField()
    ratings = serializers.DictField(child=serializers.IntegerField())
    hours = HoursRow(many=True)


class OpeningCheck(serializers.Serializer):
    ok = serializers.BooleanField()
    causes = serializers.ListField(child=serializers.CharField())
    worker = serializers.CharField()
    whatsapp = serializers.CharField()
    zones = serializers.IntegerField()
    key_hooks = serializers.IntegerField()
    assigned_not_started = serializers.IntegerField()
    carryover_unresolved = serializers.IntegerField()
    dead_letters = serializers.IntegerField()


class DeadLetter(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=OUTBOX_ATTENTION_STATUSES,
                                     help_text="DELIVERY_UNKNOWN: the recipient may already have it")
    kind = serializers.CharField()
    recipient = serializers.CharField()
    ticket = serializers.CharField(allow_null=True)
    failure_class = serializers.CharField(allow_blank=True)
    last_error = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class CarryoverRow(serializers.Serializer):
    id = serializers.IntegerField()
    ticket = serializers.CharField()
    ticket_id = serializers.IntegerField()
    event = serializers.CharField()
    event_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=CARRYOVER_STATUSES)
    custodian = serializers.CharField()
    plan = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    hook = serializers.IntegerField(allow_null=True)
    proposed_at = serializers.DateTimeField()


class RetentionCategory(serializers.Serializer):
    days = serializers.IntegerField()
    eligible = serializers.IntegerField()


class RetentionPreview(serializers.Serializer):
    guest_contact = RetentionCategory()
    intake_photos = RetentionCategory()
    incident_evidence = RetentionCategory()


class RetentionResult(serializers.Serializer):
    guest_contact = serializers.IntegerField()
    intake_photos = serializers.IntegerField()
    incident_evidence = serializers.IntegerField()


class TemplateCopy(serializers.Serializer):
    ar = serializers.CharField(max_length=1000)
    en = serializers.CharField(max_length=1000)


class ConfigResponse(serializers.Serializer):
    version = serializers.IntegerField()
    timings = serializers.DictField(child=serializers.IntegerField())
    retention_days = serializers.DictField(child=serializers.IntegerField())
    template_overrides = serializers.DictField(child=TemplateCopy())
    catalogue = serializers.DictField(child=TemplateCopy())
    retention_preview = RetentionPreview()


class SettingsVersion(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, help_text="The settings version this change was based on")


class TimingsRequest(SettingsVersion):
    timings = serializers.DictField(child=serializers.IntegerField())


class RetentionRequest(SettingsVersion):
    retention_days = serializers.DictField(child=serializers.IntegerField(min_value=0))


class TemplatesRequest(SettingsVersion):
    overrides = serializers.DictField(child=TemplateCopy(allow_null=True),
                                      help_text="null restores the catalogue wording for that message")


class WhatsAppIntegration(serializers.Serializer):
    status = serializers.ChoiceField(choices=WHATSAPP_STATUSES)
    transport = serializers.CharField()
    sender_ready = serializers.BooleanField()
    signature_secret_set = serializers.BooleanField()
    webhook_verification_set = serializers.BooleanField()


class TicketSearchRow(serializers.Serializer):
    id = serializers.IntegerField()
    ticket = serializers.CharField()
    state = serializers.ChoiceField(choices=TICKET_STATES)
    vehicle = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    hook = serializers.IntegerField(allow_null=True)


# --- outages (ADR-0008) ------------------------------------------------------------------------------------

CONFIRMED_VIA = ["in_person", "radio"]


class OutageRow(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["WHATSAPP", "SYSTEM"])
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    reason = serializers.CharField()
    declared_by = serializers.CharField()
    reconciliations = serializers.IntegerField()


class OutageStatus(serializers.Serializer):
    whatsapp = OutageBrief(allow_null=True)
    windows = OutageRow(many=True)
    time_zone = serializers.CharField(help_text="Zone the console's local times are entered in")


class SystemOutageRequest(ReasonRequest):
    started_at_local = serializers.CharField(max_length=32, help_text="Venue wall-clock time, e.g. 2026-11-16T20:30")
    ended_at_local = serializers.CharField(max_length=32)


class RelayRequest(serializers.Serializer):
    confirmed_via = serializers.ChoiceField(choices=CONFIRMED_VIA)


class ReconcileHandoverRequest(ReasonRequest):
    occurred_at_local = serializers.CharField(max_length=32, help_text="When the handover actually happened")
    delivered_by_id = serializers.IntegerField()
    verified_by_id = serializers.IntegerField()
    method = serializers.ChoiceField(choices=["in_person_check", "known_guest", "other"])
    evidence = serializers.CharField(max_length=2000)


class IntakeOnBehalfRequest(ReasonRequest):
    """Registers the car in the valet's custody (RECEIVED). Parking is confirmed separately (relay-parked)."""
    valet_id = serializers.IntegerField()
    guest_phone = serializers.CharField(max_length=40)
    plate = serializers.CharField(max_length=40)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    confirmed_via = serializers.ChoiceField(choices=CONFIRMED_VIA)


class RelayPhotoRequest(serializers.Serializer):
    photo = serializers.FileField(help_text="JPEG, PNG or WebP intake photo (size and content are checked)")
    confirmed_via = serializers.ChoiceField(choices=CONFIRMED_VIA)


class RelayParkedRequest(serializers.Serializer):
    valet_id = serializers.IntegerField(help_text="The responsible valet: must be the one holding the intake")
    zone_code = serializers.CharField(max_length=20)
    detail = serializers.CharField(max_length=80, required=False, allow_blank=True)
    hook_number = serializers.IntegerField(min_value=1)
    confirmed_via = serializers.ChoiceField(choices=CONFIRMED_VIA)


class ReconcileIntakeRequest(ReasonRequest):
    valet_id = serializers.IntegerField()
    guest_phone = serializers.CharField(max_length=40)
    plate = serializers.CharField(max_length=40)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    zone_code = serializers.CharField(max_length=20)
    detail = serializers.CharField(max_length=80, required=False, allow_blank=True)
    hook_number = serializers.IntegerField(min_value=1)
    received_at_local = serializers.CharField(max_length=32)
    parked_at_local = serializers.CharField(max_length=32)
    evidence = serializers.CharField(max_length=2000)


class PersonRow(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLES)


class SimOutageRequest(serializers.Serializer):
    down = serializers.BooleanField()


class SimOutage(serializers.Serializer):
    down = serializers.BooleanField(help_text="SIMULATED provider outage in progress")


# --- staff app (ADR-0011) -------------------------------------------------------------------------------

AVAILABILITY = ["available", "unavailable", "break_pending"]
TASK_TYPES = ["INTAKE", "RETRIEVAL", "RELOCATION"]
VALET_STEPS = ["photos", "receipt", "start_parking", "park", "offer", "custody_ack", "bring", "code", "deliver", "move"]


class SetupRequest(serializers.Serializer):
    username = serializers.CharField(max_length=150, help_text="Mobile number or username")
    code = serializers.CharField(max_length=20, help_text="One-time setup code issued by an admin")
    password = serializers.CharField(max_length=512, trim_whitespace=False)


class SetupCodeResponse(serializers.Serializer):
    setup_code = serializers.CharField(help_text="Shown once; only its hash is stored")
    sign_in_name = serializers.CharField()
    expires_at = serializers.DateTimeField()


class TeamMembershipRequest(serializers.Serializer):
    event_id = serializers.IntegerField()
    member = serializers.BooleanField(help_text="On this operation's team or not")


class AssistRequest(serializers.Serializer):
    on = serializers.BooleanField()
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ContactResponse(serializers.Serializer):
    phone = serializers.CharField(help_text="E.164; opened on request and audited. Contact happens outside Sallimha")


class ValetEventBrief(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    venue = serializers.CharField()


class ValetShift(serializers.Serializer):
    id = serializers.IntegerField()
    availability = serializers.ChoiceField(choices=AVAILABILITY)
    assisted = serializers.BooleanField(help_text="A supervisor records this valet's actions (device not working)")
    event = ValetEventBrief()


class ValetAssigned(serializers.Serializer):
    event = serializers.CharField()
    venue = serializers.CharField()


class ZoneOut(serializers.Serializer):
    code = serializers.CharField()
    label_ar = serializers.CharField(allow_blank=True)
    label_en = serializers.CharField(allow_blank=True)


class ValetVenue(serializers.Serializer):
    zones = ZoneOut(many=True)
    hook_count = serializers.IntegerField()


class ValetTicket(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    vehicle = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    hook = serializers.IntegerField(allow_null=True)
    phone_masked = serializers.CharField(allow_null=True, help_text="Never the full number")
    photos = serializers.IntegerField()
    photos_required = serializers.IntegerField()
    contact_state = serializers.ChoiceField(choices=CONTACT_STATES)
    state = serializers.ChoiceField(choices=TICKET_STATES)
    early_request = serializers.BooleanField(help_text="The customer already asked for the car")
    handover_blocked = serializers.BooleanField()


class ValetCode(serializers.Serializer):
    verified = serializers.BooleanField()
    locked = serializers.BooleanField()
    remaining = serializers.IntegerField()


class ValetCustody(serializers.Serializer):
    transfer_id = serializers.IntegerField()
    vehicle_location = serializers.CharField()
    key_location = serializers.CharField()
    from_name = serializers.CharField(allow_blank=True)


class ValetTask(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=TASK_TYPES)
    status = serializers.ChoiceField(choices=["RESERVED", "OFFERED", "ACCEPTED"])
    step = serializers.ChoiceField(choices=VALET_STEPS, help_text="The valet's next action")
    deadline = serializers.DateTimeField(allow_null=True, help_text="When an offer lapses")
    shown = serializers.BooleanField(help_text="A retrieval offer's window has started: the app acknowledged it")
    reason = serializers.CharField(allow_blank=True)
    ticket = ValetTicket()
    code = ValetCode(allow_null=True)
    custody = ValetCustody(allow_null=True)


class OfferShownResponse(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["shown", "already_shown"])
    deadline = serializers.DateTimeField(help_text="When the offer lapses; the same for every repeat")


class ValetRecent(serializers.Serializer):
    ticket = serializers.CharField()
    type = serializers.ChoiceField(choices=TASK_TYPES)
    at = serializers.DateTimeField()


class ValetMe(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ValetWork(serializers.Serializer):
    server_time = serializers.DateTimeField()
    me = ValetMe()
    shift = ValetShift(allow_null=True)
    assigned = ValetAssigned(allow_null=True)
    venue = ValetVenue(allow_null=True)
    customer_messages = serializers.ChoiceField(choices=["ok", "delayed"])
    task = ValetTask(allow_null=True)
    recent = ValetRecent(many=True)


class AvailabilityRequest(serializers.Serializer):
    available = serializers.BooleanField()


class AvailabilityResponse(serializers.Serializer):
    availability = serializers.ChoiceField(choices=AVAILABILITY)


class ValetIntakeRequest(serializers.Serializer):
    guest_phone = serializers.CharField(max_length=30)
    vehicle = serializers.CharField(max_length=200, help_text="Plate and/or a short description")
    language = serializers.ChoiceField(choices=["ar", "en"], required=False, default="ar")


class ValetIntakeResponse(serializers.Serializer):
    id = serializers.IntegerField()
    ticket = serializers.CharField()


class ValetPhotoRequest(serializers.Serializer):
    photo = serializers.FileField()


class PhotoCountResponse(serializers.Serializer):
    count = serializers.IntegerField()
    required = serializers.IntegerField()


class ReceiptRequest(serializers.Serializer):
    received = serializers.BooleanField()


class ParkRequest(serializers.Serializer):
    zone_code = serializers.CharField(max_length=20)
    detail = serializers.CharField(max_length=80, required=False, allow_blank=True)
    hook_number = serializers.IntegerField(min_value=1)


class OutcomeResponse(serializers.Serializer):
    outcome = serializers.CharField()


class CodeRequest(serializers.Serializer):
    code = serializers.CharField(max_length=12)


class CodeResponse(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["ok", "wrong", "locked"])
    remaining = serializers.IntegerField()


class DashboardCars(serializers.Serializer):
    receiving = serializers.IntegerField()
    parked = serializers.IntegerField()
    retrieving = serializers.IntegerField()
    ready = serializers.IntegerField()
    delivered = serializers.IntegerField()


class DashboardProblems(serializers.Serializer):
    alerts = serializers.IntegerField(help_text="Items needing attention that nobody has acknowledged")
    critical = serializers.IntegerField()
    incidents = serializers.IntegerField(help_text="Incidents not yet resolved")
    holds = serializers.IntegerField(help_text="Active safety holds")


class DashboardMember(serializers.Serializer):
    staff_id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=TEAM_STATUSES)
    task = serializers.CharField(allow_null=True)
    parked = serializers.IntegerField()
    delivered = serializers.IntegerField()


class DashboardTeam(serializers.Serializer):
    available = serializers.IntegerField()
    busy = serializers.IntegerField()
    unavailable = serializers.IntegerField()
    not_started = serializers.IntegerField()
    members = DashboardMember(many=True)


class Dashboard(serializers.Serializer):
    event = EventBrief()
    generated_at = serializers.DateTimeField()
    cars = DashboardCars()
    waiting_requests = serializers.IntegerField(help_text="Requested and not yet accepted by a valet")
    delayed_requests = serializers.IntegerField(help_text="Waiting longer than delay_threshold_s")
    delay_threshold_s = serializers.IntegerField()
    oldest_wait_s = serializers.IntegerField(allow_null=True)
    request_to_ready = StageStat(help_text="From the customer's request to the car ready at the pickup point")
    problems = DashboardProblems()
    team = DashboardTeam()
