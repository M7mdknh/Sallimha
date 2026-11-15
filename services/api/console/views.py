"""Console API: live monitoring, shift operations and exception handling (no routine-dispatch control).

Every endpoint validates input and shapes output with console.serializers; the OpenAPI document and the
web app's TypeScript types are generated from those serializers (contracts/openapi.yaml)."""

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from console import live
from console import serializers as s
from console.common import (
    IsConsoleStaff,
    actor_of,
    domain_response,
    events_for,
    idempotent_post,
    out,
    scoped_event,
    scoped_ticket,
    validated,
)
from core.audit import audit
from core.errors import DomainError
from ops.models import Alert, Media, Shift, Staff
from ops.permissions import actor_label
from ops.services import custody, intake, retrieval, shifts
from ops.services.media import read_private

IDEMPOTENCY = OpenApiParameter("Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True,
                               description="Unique per intended action; a repeat replays the stored result")
REFUSALS = {400: s.ErrorResponse, 403: s.ErrorResponse, 404: OpenApiResponse(description="Not found or out of scope"),
            409: s.ErrorResponse, 428: s.ErrorResponse}


def command_schema(request, response, **kw):
    return extend_schema(request=request, responses={200: response, **REFUSALS}, parameters=[IDEMPOTENCY], **kw)


@extend_schema(responses={200: s.CsrfResponse}, auth=[])
@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return out(s.CsrfResponse, {"csrfToken": get_token(request)})


def _enforce_csrf(request) -> None:
    """DRF skips CSRF for anonymous requests; sign-in and sign-out must not be forgeable from another site."""
    from rest_framework.authentication import SessionAuthentication

    SessionAuthentication().enforce_csrf(request)


@extend_schema(request=s.LoginRequest, responses={200: s.LoginResponse, 400: s.ErrorResponse, 403: s.ErrorResponse,
                                                   429: s.ErrorResponse}, auth=[])
@api_view(["POST"])
@permission_classes([AllowAny])
@domain_response
def login_view(request):
    from console import auth_flow

    _enforce_csrf(request)
    data = validated(s.LoginRequest, request.data)
    return auth_flow.login_step(request, data, authenticate, login)


@extend_schema(request=None, responses={200: s.OkResponse, 403: s.ErrorResponse})
@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    _enforce_csrf(request)
    logout(request)
    return out(s.OkResponse, {"ok": True})


@extend_schema(responses={200: s.MeResponse})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def me(request):
    staff = actor_of(request)
    return out(s.MeResponse, {"id": staff.id, "name": staff.full_name, "role": staff.role, "language": staff.language,
                              "simulator": settings.SIMULATOR_ENABLED})


@extend_schema(responses={200: s.EventSummary(many=True)})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def events(request):
    actor = actor_of(request)
    rows = events_for(actor).select_related("venue").order_by("status", "-starts_at")
    return out(s.EventSummary, [{"id": e.id, "name": e.name, "venue": e.venue.name, "status": e.status,
                                 "starts_at": e.starts_at} for e in rows])


@extend_schema(responses={200: s.LiveSnapshot, 404: OpenApiResponse(description="Not found or out of scope")})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def event_live(request, event_id):
    actor = actor_of(request)
    return out(s.LiveSnapshot, live.snapshot(scoped_event(actor, event_id), timezone.now()))


class ConsoleCommand(APIView):
    permission_classes = [IsConsoleStaff]


class StartShift(ConsoleCommand):
    @command_schema(s.StartShiftRequest, s.ShiftResponse)
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        event = scoped_event(actor, event_id)
        data = validated(s.StartShiftRequest, request.data)
        staff = Staff.objects.filter(pk=data["staff_id"], org_id=actor.org_id).first()
        if staff is None:
            raise Http404
        shift = shifts.start_shift(actor, event, staff)
        return out(s.ShiftResponse, {"id": shift.id, "staff_id": staff.id})


class EndShift(ConsoleCommand):
    @command_schema(None, s.ShiftResponse)
    @idempotent_post
    @domain_response
    def post(self, request, shift_id):
        actor = actor_of(request)
        shift = Shift.objects.filter(pk=shift_id).select_related("event").first()
        if shift is None:
            raise Http404
        scoped_event(actor, shift.event_id)
        shifts.end_shift(actor, shift)
        return out(s.ShiftResponse, {"id": shift.id, "ended": True})


class AckAlert(ConsoleCommand):
    @command_schema(None, s.AlertAckResponse)
    @idempotent_post
    @domain_response
    def post(self, request, alert_id):
        actor = actor_of(request)
        alert = Alert.objects.filter(pk=alert_id).first()
        if alert is None:
            raise Http404
        scoped_event(actor, alert.event_id)
        if alert.acknowledged_at is None:
            alert.acknowledged_at = timezone.now()
            alert.acknowledged_by = actor
            alert.save(update_fields=["acknowledged_at", "acknowledged_by"])
            audit("alert.ack", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
                  entity_type="alert", entity_id=alert.id, event_id=alert.event_id)
        return out(s.AlertAckResponse, {"id": alert.id, "acknowledged": True})


@extend_schema(parameters=[OpenApiParameter("q", str, required=True, description="Ticket number or part of a plate")],
               responses={200: s.TicketSearchRow(many=True),
                          404: OpenApiResponse(description="Not found or out of scope")})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def ticket_search(request, event_id):
    event = scoped_event(actor_of(request), event_id)
    return out(s.TicketSearchRow, live.search(event, request.query_params.get("q", "")))


@extend_schema(responses={200: s.TicketDetail, 404: OpenApiResponse(description="Not found or out of scope")})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def ticket_detail(request, ticket_id):
    actor = actor_of(request)
    return out(s.TicketDetail, live.ticket_detail(scoped_ticket(actor, ticket_id), actor))


class TicketCommand(ConsoleCommand):
    request_serializer = None
    response_serializer = None

    def run(self, actor, ticket, data) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        actor = actor_of(request)
        ticket = scoped_ticket(actor, ticket_id)
        data = validated(self.request_serializer, request.data) if self.request_serializer else {}
        return out(self.response_serializer, self.run(actor, ticket, data))


def ticket_command(request_serializer, response_serializer):
    """Class decorator: binds the contract serializers and documents the endpoint."""

    def decorate(cls):
        cls.request_serializer = request_serializer
        cls.response_serializer = response_serializer
        cls.post = command_schema(request_serializer, response_serializer)(TicketCommand.post)
        return cls

    return decorate


@ticket_command(s.CancelRequest, s.TicketStateResponse)
class CancelTicket(TicketCommand):
    def run(self, actor, ticket, data):
        ticket = intake.cancel_ticket(actor, ticket, data["reason"],
                                      guest_has_vehicle_and_keys=data["guest_has_vehicle_and_keys"])
        return {"id": ticket.id, "state": ticket.state}


@ticket_command(s.ReasonRequest, s.RequestStateResponse)
class WithdrawRequest(TicketCommand):
    def run(self, actor, ticket, data):
        req = retrieval.open_request(ticket)
        if req is None:
            raise DomainError("no_open_request")
        req = retrieval.withdraw_request(actor, req, data["reason"])
        return {"request_id": req.id, "state": req.state}


@ticket_command(s.WithdrawWithCustodyRequest, s.TransferResponse)
class WithdrawWithCustody(TicketCommand):
    def run(self, actor, ticket, data):
        req = retrieval.open_request(ticket)
        if req is None:
            raise DomainError("no_open_request")
        transfer = custody.withdraw_accepted_with_custody_resolution(
            actor, req, zone_code=data["zone_code"], detail=data.get("detail", ""), hook_number=data["hook_number"],
            reason=data["reason"])
        return {"transfer_id": transfer.id, "state": "WITHDRAWN"}


@ticket_command(s.CustodyTransferRequest, s.TransferResponse)
class TransferCustody(TicketCommand):
    def run(self, actor, ticket, data):
        task = ticket.tasks.filter(type="RETRIEVAL", status="ACCEPTED").first()
        to_staff = Staff.objects.filter(pk=data["to_staff_id"], org_id=actor.org_id).first()
        if task is None or to_staff is None:
            raise DomainError("invalid_state")
        transfer = custody.transfer_custody(actor, task, to_staff, data["vehicle_location"], data["key_location"],
                                            data["reason"])
        return {"transfer_id": transfer.id}


@ticket_command(s.IntakeTransferRequest, s.TransferResponse)
class TransferIntake(TicketCommand):
    def run(self, actor, ticket, data):
        to_staff = Staff.objects.filter(pk=data["to_staff_id"], org_id=actor.org_id).first()
        if to_staff is None:
            raise DomainError("receiver_unavailable")
        return {"transfer_id": intake.transfer_intake(actor, ticket, to_staff, data["reason"]).id}


@ticket_command(s.CorrectPhoneRequest, s.CorrectPhoneResponse)
class CorrectPhone(TicketCommand):
    def run(self, actor, ticket, data):
        binding = retrieval.correct_guest_phone(actor, ticket, data["phone"], data["reason"])
        return {"masked": binding.phone_masked, "revision": binding.revision}


@ticket_command(s.ConfirmReceiptRequest, s.ContactStateResponse)
class ConfirmReceipt(TicketCommand):
    def run(self, actor, ticket, data):
        ticket = intake.confirm_guest_receipt(actor, ticket, data["received"])
        return {"id": ticket.id, "contact_state": ticket.contact_state}


@ticket_command(s.ExceptIntakeRequest, s.IdResponse)
class ExceptIntake(TicketCommand):
    def run(self, actor, ticket, data):
        return {"id": intake.except_intake_requirement(actor, ticket, data["kind"], data["reason"]).id}


@extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY,
                          404: OpenApiResponse(description="Not found or out of scope")})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def media_file(request, media_id):
    """Private evidence, streamed only after scope checks; never a public URL."""
    actor = actor_of(request)
    media = Media.objects.filter(pk=media_id, deleted_at__isnull=True).select_related("ticket").first()
    if media is None or media.ticket is None:
        raise Http404
    scoped_ticket(actor, media.ticket_id)
    audit("media.view", actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="media",
          entity_id=media.id, event_id=media.ticket.event_id)
    response = FileResponse(iter([read_private(media.storage_key)]), content_type=media.content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --- Phase 2 ticket exception actions ------------------------------------------------------------

@ticket_command(s.OpenIncidentRequest, s.IdResponse)
class OpenIncident(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import incidents

        return {"id": incidents.open_incident(actor, ticket.event, data["category"], data["description"],
                                              ticket=ticket).id}


@ticket_command(s.PlaceHoldRequest, s.IdResponse)
class PlaceHold(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import holds

        return {"id": holds.place_hold(actor, ticket, data["reason"], blocks_dispatch=data["blocks_dispatch"],
                                       blocks_handover=data["blocks_handover"]).id}


@ticket_command(s.ClearHoldRequest, s.IdResponse)
class ClearHold(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.models import SafetyHold
        from ops.services import holds

        hold = SafetyHold.objects.filter(pk=data["hold_id"], ticket=ticket).first()
        if hold is None:
            raise DomainError("invalid_state")
        return {"id": holds.clear_hold(actor, hold, data["reason"]).id}


@ticket_command(s.ReasonRequest, s.RequestStateResponse)
class AssistedRequest(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.models import Role
        from ops.permissions import require

        require(actor, Role.SUPERVISOR, ticket.event)
        req, _created = retrieval.request_retrieval(None, ticket, via="assisted", actor=actor,
                                                    reason=data["reason"])
        return {"request_id": req.id, "state": req.state}


@ticket_command(s.AssistedHandoverRequest, s.TicketStateResponse)
class AssistedHandover(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import handover

        handover.assisted_handover(actor, ticket, data["method"], data["reason"])
        ticket.refresh_from_db()
        return {"id": ticket.id, "state": ticket.state}


@ticket_command(s.RelocateStartRequest, s.IdResponse)
class RelocateStart(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import relocation

        valet = Staff.objects.filter(pk=data["to_staff_id"], org_id=actor.org_id).first()
        if valet is None:
            raise DomainError("receiver_unavailable")
        return {"id": relocation.start_relocation(actor, ticket, valet, data["reason"]).id}


@ticket_command(s.RelocateCompleteRequest, s.TicketStateResponse)
class RelocateComplete(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import relocation

        task = ticket.tasks.filter(type="RELOCATION", status__in=["RESERVED", "OFFERED", "ACCEPTED"]).first()
        if task is None:
            raise DomainError("invalid_state")
        ticket = relocation.complete_relocation(actor, task, zone_code=data["zone_code"],
                                                detail=data.get("detail", ""), hook_number=data["hook_number"])
        return {"id": ticket.id, "state": ticket.state}


@ticket_command(s.ProposeUnclaimedRequest, s.IdResponse)
class ProposeUnclaimed(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import carryover

        return {"id": carryover.propose_unclaimed(actor, ticket, custodian=data["custodian"], plan=data["plan"]).id}


def _open_case(ticket):
    case = ticket.carryover_cases.exclude(status="RELEASED").first()
    if case is None:
        raise DomainError("invalid_state")
    return case


@ticket_command(None, s.IdResponse)
class ApproveUnclaimed(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import carryover

        return {"id": carryover.approve_unclaimed(actor, _open_case(ticket)).id}


@ticket_command(s.ReleaseCarryoverRequest, s.IdResponse)
class ReleaseCarryover(TicketCommand):
    def run(self, actor, ticket, data):
        from ops.services import carryover

        return {"id": carryover.release_carryover(actor, _open_case(ticket), data["method"], data["note"]).id}
