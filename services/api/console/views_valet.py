"""The valet app's API (ADR-0011). Every command calls the same ops.services function the WhatsApp conversation
called; these views only authenticate the valet, find their own task or ticket, and translate outcomes.

A valet reaches nothing here that is not theirs: tickets and tasks are looked up through their own live task, and
anything else is 404. Commands need an Idempotency-Key, so a double tap or a retry after a lost reply never
repeats an action."""

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

from console import serializers as s
from console import valet as read
from console.common import IsValet, actor_of, domain_response, idempotent_post, out, validated
from console.views import IDEMPOTENCY, REFUSALS, command_schema
from core.errors import DomainError
from ops.models import LIVE_TASK_STATUSES, CustodyTransfer, Task, Ticket
from ops.services import custody, dispatch, handover, intake, relocation, shifts


def _own_ticket(staff, ticket_id) -> Ticket:
    """The ticket of this valet's own live task — never another valet's, never a finished one."""
    task = Task.objects.filter(assignee=staff, ticket_id=ticket_id, status__in=LIVE_TASK_STATUSES).first()
    if task is None:
        raise Http404
    return Ticket.objects.select_related("event").get(pk=ticket_id)


def _own_task(staff, task_id) -> Task:
    """Finished tasks stay reachable so a repeated tap gets a calm answer instead of 'not found'."""
    task = Task.objects.filter(pk=task_id, assignee=staff).select_related("ticket", "event").first()
    if task is None:
        raise Http404
    return task


def _settle(outcome: str, ok: tuple[str, ...], refusals: dict | None = None) -> dict:
    """Outcomes that changed (or already had changed) the state succeed; anything else is a refusal the app shows."""
    if outcome in ok:
        return {"outcome": outcome}
    raise DomainError((refusals or {}).get(outcome, outcome))


@extend_schema(responses={200: s.ValetWork})
@api_view(["GET"])
@permission_classes([IsValet])
def work(request):
    """Polled by the app. A read only: it never changes anything, including an offer's deadline (ADR-0012)."""
    staff = actor_of(request)
    return out(s.ValetWork, read.work(staff, timezone.now()))


class ValetCommand(APIView):
    permission_classes = [IsValet]


class OfferShown(ValetCommand):
    """The app acknowledges that a retrieval offer is on screen; that starts its response window, once (ADR-0012).
    Repeating it (a refresh, another tab, a retry after a lost reply) never moves the deadline."""

    @command_schema(None, s.OfferShownResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        outcome = dispatch.offer_seen(staff, task.id, timezone.now())
        if outcome == "stale":
            raise DomainError("stale")
        task.refresh_from_db()
        return out(s.OfferShownResponse, {"outcome": outcome, "deadline": min(task.offer_deadline,
                                                                              task.hard_deadline)})


class Availability(ValetCommand):
    @command_schema(s.AvailabilityRequest, s.AvailabilityResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        staff = actor_of(request)
        result = shifts.set_availability(staff, validated(s.AvailabilityRequest, request.data)["available"])
        if result == "no_shift":
            raise DomainError("not_on_shift")
        return out(s.AvailabilityResponse, {"availability": result})


class Intake(ValetCommand):
    @command_schema(s.ValetIntakeRequest, s.ValetIntakeResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        staff = actor_of(request)
        data = validated(s.ValetIntakeRequest, request.data)
        ticket = intake.register_with_guest(staff, data["guest_phone"], data["vehicle"], data.get("language", "ar"))
        return out(s.ValetIntakeResponse, {"id": ticket.id, "ticket": f"#{ticket.display_number:03d}"})


class Photo(ValetCommand):
    """Multipart upload straight from the phone's camera; nothing passes through WhatsApp."""

    parser_classes = [MultiPartParser]

    @extend_schema(request={"multipart/form-data": s.ValetPhotoRequest},
                   responses={200: s.PhotoCountResponse, **REFUSALS}, parameters=[IDEMPOTENCY])
    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        staff = actor_of(request)
        ticket = _own_ticket(staff, ticket_id)
        upload = validated(s.ValetPhotoRequest, request.data)["photo"]
        if upload.size > settings.MEDIA_MAX_BYTES:  # refuse before reading the file into memory
            raise DomainError("media_too_large")
        intake.attach_intake_media(staff, ticket, upload.read(settings.MEDIA_MAX_BYTES + 1), upload.content_type or "")
        return out(s.PhotoCountResponse, {"count": intake.intake_photo_count(ticket),
                                          "required": intake.REQUIRED_PHOTOS})


class Receipt(ValetCommand):
    @command_schema(s.ReceiptRequest, s.ContactStateResponse)
    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        staff = actor_of(request)
        ticket = intake.confirm_guest_receipt(staff, _own_ticket(staff, ticket_id),
                                              validated(s.ReceiptRequest, request.data)["received"])
        return out(s.ContactStateResponse, {"id": ticket.id, "contact_state": ticket.contact_state})


class StartParking(ValetCommand):
    @command_schema(None, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        staff = actor_of(request)
        intake.start_parking(staff, _own_ticket(staff, ticket_id))
        return out(s.OkResponse, {"ok": True})


class Park(ValetCommand):
    @command_schema(s.ParkRequest, s.TicketStateResponse)
    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        staff = actor_of(request)
        data = validated(s.ParkRequest, request.data)
        ticket = intake.park(staff, _own_ticket(staff, ticket_id), data["zone_code"], data.get("detail", ""),
                             data["hook_number"])
        return out(s.TicketStateResponse, {"id": ticket.id, "state": ticket.state})


class Accept(ValetCommand):
    @command_schema(None, s.OutcomeResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        accept = relocation.accept_move if task.type == Task.Type.RELOCATION else dispatch.accept_offer
        return out(s.OutcomeResponse, _settle(accept(staff, task.id), ("accepted", "duplicate")))


class Decline(ValetCommand):
    @command_schema(None, s.OutcomeResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        decline = relocation.decline_move if task.type == Task.Type.RELOCATION else dispatch.decline_offer
        return out(s.OutcomeResponse, _settle(decline(staff, task.id), ("declined",)))


class Ready(ValetCommand):
    @command_schema(None, s.OutcomeResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        return out(s.OutcomeResponse, _settle(handover.mark_ready_by(staff, task.id), ("ready", "duplicate")))


class Code(ValetCommand):
    """A wrong code is a recorded answer, not a refusal: it is stored under its key, so a repeated tap never uses
    up a second attempt."""

    @command_schema(s.CodeRequest, s.CodeResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        outcome, remaining = handover.verify_collection(staff, task.ticket,
                                                        validated(s.CodeRequest, request.data)["code"])
        if outcome == "stale":
            raise DomainError("stale")
        return out(s.CodeResponse, {"outcome": outcome, "remaining": remaining})


class Deliver(ValetCommand):
    @command_schema(None, s.OutcomeResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        return out(s.OutcomeResponse, _settle(handover.deliver(staff, task.id), ("delivered", "duplicate"),
                                              {"blocked": "handover_blocked", "unverified": "code_required"}))


class CustodyAck(ValetCommand):
    @command_schema(None, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        kind = (CustodyTransfer.Kind.INTAKE_HANDOFF if task.type == Task.Type.INTAKE
                else CustodyTransfer.Kind.RETRIEVAL_TRANSFER)
        transfer = (CustodyTransfer.objects.filter(ticket_id=task.ticket_id, kind=kind, to_staff=staff)
                    .order_by("-id").first())
        if transfer is None:
            raise DomainError("stale")
        if kind == CustodyTransfer.Kind.INTAKE_HANDOFF:
            intake.acknowledge_intake_transfer(staff, transfer)
        else:
            custody.acknowledge_custody(staff, transfer)
        return out(s.OkResponse, {"ok": True})


class Moved(ValetCommand):
    @command_schema(s.ParkRequest, s.TicketStateResponse)
    @idempotent_post
    @domain_response
    def post(self, request, task_id):
        staff = actor_of(request)
        task = _own_task(staff, task_id)
        if task.type != Task.Type.RELOCATION:
            raise DomainError("invalid_state")
        data = validated(s.ParkRequest, request.data)
        with transaction.atomic():
            ticket = relocation.complete_relocation(staff, task, zone_code=data["zone_code"],
                                                    detail=data.get("detail", ""), hook_number=data["hook_number"])
        return out(s.TicketStateResponse, {"id": ticket.id, "state": ticket.state})
