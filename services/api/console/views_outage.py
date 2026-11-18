"""Outage workflow endpoints (ADR-0008). Roles, scope, outage state and conflicts are enforced in
ops.services.outage; these views only translate venue-local times and look up objects in scope."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

from console import serializers as s
from console.common import (
    IsConsoleStaff,
    actor_of,
    domain_response,
    idempotent_post,
    out,
    scoped_event,
    scoped_ticket,
    validated,
)
from console.views import IDEMPOTENCY, REFUSALS, TicketCommand, command_schema, ticket_command
from console.views_valet import vehicle_from
from core.errors import DomainError
from ops.models import CustodyTransfer, EventAssignment, OutageWindow, Role, Staff, Task
from ops.permissions import can_access_event
from ops.services import outage
from ops.services.localtime import parse_local

RECENT = timedelta(days=30)


def _brief(window) -> dict | None:
    return {"id": window.id, "since": window.started_at, "declared_by": window.declared_by.full_name,
            "reason": window.reason} if window else None


def _staff(actor, staff_id) -> Staff:
    person = Staff.objects.filter(pk=staff_id, org_id=actor.org_id).first()
    if person is None:
        raise DomainError("receiver_unavailable")
    return person


class Command(APIView):
    permission_classes = [IsConsoleStaff]


@extend_schema(responses={200: s.OutageStatus})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def outage_status(request):
    actor = actor_of(request)
    windows = (OutageWindow.objects.filter(org_id=actor.org_id, started_at__gte=timezone.now() - RECENT)
               .select_related("declared_by").annotate(n=Count("reconciliations")).order_by("-started_at"))
    venue = actor.org.venues.order_by("id").first()
    return out(s.OutageStatus, {
        "whatsapp": _brief(outage.active_whatsapp_outage(actor.org)),
        "windows": [{"id": w.id, "kind": w.kind, "started_at": w.started_at, "ended_at": w.ended_at,
                     "reason": w.reason, "declared_by": w.declared_by.full_name, "reconciliations": w.n}
                    for w in windows],
        "time_zone": venue.timezone if venue else "Asia/Riyadh"})


class DeclareWhatsAppOutage(Command):
    @command_schema(s.ReasonRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        reason = validated(s.ReasonRequest, request.data)["reason"]
        return out(s.IdResponse, {"id": outage.declare_whatsapp_outage(actor, actor.org, reason).id})


class EndWhatsAppOutage(Command):
    @command_schema(s.ReasonRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        reason = validated(s.ReasonRequest, request.data)["reason"]
        return out(s.IdResponse, {"id": outage.end_whatsapp_outage(actor, actor.org, reason).id})


class ReportWhatsAppOutage(Command):
    @command_schema(s.ReasonRequest, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        reason = validated(s.ReasonRequest, request.data)["reason"]
        outage.report_whatsapp_outage(actor, scoped_event(actor, event_id), reason)
        return out(s.OkResponse, {"ok": True})


class RecordSystemOutage(Command):
    @command_schema(s.SystemOutageRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        event = scoped_event(actor, event_id)
        data = validated(s.SystemOutageRequest, request.data)
        window = outage.record_system_outage(actor, actor.org, started_at=parse_local(event, data["started_at_local"]),
                                             ended_at=parse_local(event, data["ended_at_local"]),
                                             reason=data["reason"])
        return out(s.IdResponse, {"id": window.id})


@extend_schema(responses={200: s.PersonRow(many=True), 404: OpenApiResponse(description="Not found or out of scope")})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def event_people(request, event_id):
    """Valets assigned to the event and supervisors and above who can act on it (for console selects)."""
    actor = actor_of(request)
    event = scoped_event(actor, event_id)
    valet_ids = EventAssignment.objects.filter(event=event).values_list("staff_id", flat=True)
    rows = []
    for person in Staff.objects.filter(org_id=event.org_id, enabled=True).order_by("role", "full_name"):
        if person.role == Role.VALET and person.id in set(valet_ids):
            rows.append(person)
        elif person.role != Role.VALET and can_access_event(person, event):
            rows.append(person)
    return out(s.PersonRow, [{"id": p.id, "name": p.full_name, "role": p.role} for p in rows])


def _intake_args(actor, data):
    return dict(valet=_staff(actor, data["valet_id"]), guest_phone=data["guest_phone"], plate=data["plate"],
                description=data.get("description", ""), zone_code=data["zone_code"], detail=data.get("detail", ""),
                hook_number=data["hook_number"], reason=data["reason"], region=data.get("guest_region") or "SA")


class IntakeOnBehalf(Command):
    @command_schema(s.IntakeOnBehalfRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        event = scoped_event(actor, event_id)
        data = validated(s.IntakeOnBehalfRequest, request.data)
        ticket = outage.start_intake(actor, event, valet=_staff(actor, data["valet_id"]),
                                     guest_phone=data["guest_phone"], entry=vehicle_from(data),
                                     confirmed_via=data["confirmed_via"], reason=data["reason"],
                                     region=data.get("guest_region") or "SA",
                                     confirm_duplicate=data.get("confirm_duplicate", False))
        return out(s.IdResponse, {"id": ticket.id})


class RelayIntakePhoto(Command):
    """Multipart upload. Under the idempotency layer the stored fingerprint covers the form fields and the file name;
    a retry with the same key replays, a new key stores another photo (the console keeps its key until success)."""

    parser_classes = [MultiPartParser]

    @extend_schema(request={"multipart/form-data": s.RelayPhotoRequest}, responses={200: s.OkResponse, **REFUSALS},
                   parameters=[IDEMPOTENCY])
    @idempotent_post
    @domain_response
    def post(self, request, ticket_id):
        actor = actor_of(request)
        ticket = scoped_ticket(actor, ticket_id)
        data = validated(s.RelayPhotoRequest, request.data)
        upload = data["photo"]
        if upload.size > settings.MEDIA_MAX_BYTES:  # refuse before reading the file into memory
            raise DomainError("media_too_large")
        outage.relay_intake_photo(actor, ticket, upload.read(settings.MEDIA_MAX_BYTES + 1),
                                  upload.content_type or "", confirmed_via=data["confirmed_via"])
        return out(s.OkResponse, {"ok": True})


def _window_at(actor, moment) -> OutageWindow:
    window = OutageWindow.objects.filter(org_id=actor.org_id, kind=OutageWindow.Kind.SYSTEM, started_at__lte=moment,
                                         ended_at__gte=moment).first()
    if window is None:
        raise DomainError("outside_outage_window")
    return window


class ReconcileIntake(Command):
    @command_schema(s.ReconcileIntakeRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        event = scoped_event(actor, event_id)
        data = validated(s.ReconcileIntakeRequest, request.data)
        received, parked = parse_local(event, data["received_at_local"]), parse_local(event, data["parked_at_local"])
        ticket = outage.record_intake(actor, event, outage=_window_at(actor, received), received_at=received,
                                      parked_at=parked, evidence=data["evidence"], **_intake_args(actor, data))
        return out(s.IdResponse, {"id": ticket.id})


def _open_task(ticket, status, kinds=("RETRIEVAL", "RELOCATION")) -> Task:
    task = ticket.tasks.filter(status=status, type__in=kinds).order_by("-id").first()
    if task is None:
        raise DomainError("stale")
    return task


@ticket_command(s.RelayRequest, s.OkResponse)
class RelayAccept(TicketCommand):
    def run(self, actor, ticket, data):
        outage.relay_accept(actor, _open_task(ticket, "OFFERED"), confirmed_via=data["confirmed_via"])
        return {"ok": True}


@ticket_command(s.RelayRequest, s.OkResponse)
class RelayReady(TicketCommand):
    def run(self, actor, ticket, data):
        outage.relay_ready(actor, _open_task(ticket, "ACCEPTED", ("RETRIEVAL",)), confirmed_via=data["confirmed_via"])
        return {"ok": True}


@ticket_command(s.RelayRequest, s.OkResponse)
class RelayCustodyAck(TicketCommand):
    def run(self, actor, ticket, data):
        transfer = ticket.custody_transfers.filter(kind=CustodyTransfer.Kind.RETRIEVAL_TRANSFER,
                                                   acknowledged_at__isnull=True).order_by("-id").first()
        if transfer is None:
            raise DomainError("stale")
        outage.relay_custody_ack(actor, transfer, confirmed_via=data["confirmed_via"])
        return {"ok": True}


@ticket_command(s.RelayParkedRequest, s.TicketStateResponse)
class RelayParked(TicketCommand):
    def run(self, actor, ticket, data):
        ticket = outage.relay_parked(actor, ticket, valet=_staff(actor, data["valet_id"]), zone_code=data["zone_code"],
                                     detail=data.get("detail", ""), hook_number=data["hook_number"],
                                     confirmed_via=data["confirmed_via"])
        return {"id": ticket.id, "state": ticket.state}


@ticket_command(s.ReconcileHandoverRequest, s.IdResponse)
class ReconcileHandover(TicketCommand):
    def run(self, actor, ticket, data):
        occurred = parse_local(ticket.event, data["occurred_at_local"])
        record = outage.reconcile_handover(
            actor, ticket, outage=_window_at(actor, occurred), occurred_at=occurred,
            delivered_by=_staff(actor, data["delivered_by_id"]), verified_by=_staff(actor, data["verified_by_id"]),
            method=data["method"], evidence=data["evidence"], reason=data["reason"])
        return {"id": record.id}
