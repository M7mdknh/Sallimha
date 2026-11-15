"""Console API: live monitoring, shift operations and exception handling (no routine-dispatch control)."""

from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from console import live
from console.common import (
    IsConsoleStaff,
    actor_of,
    domain_response,
    events_for,
    idempotent_post,
    scoped_event,
    scoped_ticket,
)
from core.audit import audit
from core.errors import DomainError
from ops.models import Alert, Media, Shift, Staff
from ops.permissions import actor_label
from ops.services import custody, intake, retrieval, shifts
from ops.services.media import read_private


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"csrfToken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    from console import auth_flow

    return auth_flow.login_step(request, authenticate, login)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def me(request):
    staff = actor_of(request)
    return Response({"id": staff.id, "name": staff.full_name, "role": staff.role, "language": staff.language})


@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def events(request):
    actor = actor_of(request)
    rows = events_for(actor).select_related("venue").order_by("status", "-starts_at")
    return Response([{"id": e.id, "name": e.name, "venue": e.venue.name, "status": e.status,
                      "starts_at": e.starts_at} for e in rows])


@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def event_live(request, event_id):
    actor = actor_of(request)
    return Response(live.snapshot(scoped_event(actor, event_id), timezone.now()))


class ConsoleCommand(APIView):
    permission_classes = [IsConsoleStaff]


class StartShift(ConsoleCommand):
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        event = scoped_event(actor, event_id)
        staff = Staff.objects.filter(pk=request.data.get("staff_id"), org_id=actor.org_id).first()
        if staff is None:
            raise Http404
        shift = shifts.start_shift(actor, event, staff)
        return Response({"id": shift.id, "staff_id": staff.id})


class EndShift(ConsoleCommand):
    @idempotent_post
    @domain_response
    def post(self, request, shift_id):
        actor = actor_of(request)
        shift = Shift.objects.filter(pk=shift_id).select_related("event").first()
        if shift is None:
            raise Http404
        scoped_event(actor, shift.event_id)
        shifts.end_shift(actor, shift)
        return Response({"id": shift.id, "ended": True})


class AckAlert(ConsoleCommand):
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
        return Response({"id": alert.id, "acknowledged": True})


@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def ticket_detail(request, ticket_id):
    actor = actor_of(request)
    return Response(live.ticket_detail(scoped_ticket(actor, ticket_id), actor))


def _text(request, name, required=True) -> str:
    value = str(request.data.get(name, "") or "").strip()
    if required and not value:
        raise DomainError(f"{name}_required")
    return value


class TicketCommand(ConsoleCommand):
    def run(self, actor, ticket, request) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        actor = actor_of(request)
        ticket = scoped_ticket(actor, ticket_id)
        return Response(self.run(actor, ticket, request))


class CancelTicket(TicketCommand):
    def run(self, actor, ticket, request):
        ticket = intake.cancel_ticket(actor, ticket, _text(request, "reason"),
                                      guest_has_vehicle_and_keys=bool(request.data.get("guest_has_vehicle_and_keys")))
        return {"id": ticket.id, "state": ticket.state}


class WithdrawRequest(TicketCommand):
    def run(self, actor, ticket, request):
        req = retrieval.open_request(ticket)
        if req is None:
            raise DomainError("no_open_request")
        req = retrieval.withdraw_request(actor, req, _text(request, "reason"))
        return {"request_id": req.id, "state": req.state}


class WithdrawWithCustody(TicketCommand):
    def run(self, actor, ticket, request):
        req = retrieval.open_request(ticket)
        if req is None:
            raise DomainError("no_open_request")
        try:
            hook = int(request.data.get("hook_number"))
        except (TypeError, ValueError) as exc:
            raise DomainError("hook_invalid") from exc
        transfer = custody.withdraw_accepted_with_custody_resolution(
            actor, req, zone_code=_text(request, "zone_code"), detail=_text(request, "detail", required=False),
            hook_number=hook, reason=_text(request, "reason"))
        return {"transfer_id": transfer.id, "state": "WITHDRAWN"}


class TransferCustody(TicketCommand):
    def run(self, actor, ticket, request):
        task = ticket.tasks.filter(type="RETRIEVAL", status="ACCEPTED").first()
        to_staff = Staff.objects.filter(pk=request.data.get("to_staff_id"), org_id=actor.org_id).first()
        if task is None or to_staff is None:
            raise DomainError("invalid_state")
        transfer = custody.transfer_custody(actor, task, to_staff, _text(request, "vehicle_location"),
                                            _text(request, "key_location"), _text(request, "reason"))
        return {"transfer_id": transfer.id}


class TransferIntake(TicketCommand):
    def run(self, actor, ticket, request):
        to_staff = Staff.objects.filter(pk=request.data.get("to_staff_id"), org_id=actor.org_id).first()
        if to_staff is None:
            raise DomainError("receiver_unavailable")
        transfer = intake.transfer_intake(actor, ticket, to_staff, _text(request, "reason"))
        return {"transfer_id": transfer.id}


class CorrectPhone(TicketCommand):
    def run(self, actor, ticket, request):
        binding = retrieval.correct_guest_phone(actor, ticket, _text(request, "phone"), _text(request, "reason"))
        return {"masked": binding.phone_masked, "revision": binding.revision}


class ConfirmReceipt(TicketCommand):
    def run(self, actor, ticket, request):
        ticket = intake.confirm_guest_receipt(actor, ticket, bool(request.data.get("received")))
        return {"id": ticket.id, "contact_state": ticket.contact_state}


class ExceptIntake(TicketCommand):
    def run(self, actor, ticket, request):
        ticket = intake.except_intake_requirement(actor, ticket, _text(request, "kind"), _text(request, "reason"))
        return {"id": ticket.id}


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
