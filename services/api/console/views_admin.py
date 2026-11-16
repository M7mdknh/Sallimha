"""Phase 2 console endpoints: incidents, directory, events, reports/exports, configuration, operations and
integrations. Roles are enforced in the domain services; out-of-scope objects are 404."""

import csv
import io

from django.conf import settings
from django.db.models import Prefetch, Sum
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView

from console import serializers as s
from console.common import IsConsoleStaff, actor_of, domain_response, idempotent_post, out, scoped_event, validated
from console.views import REFUSALS, command_schema
from core.audit import audit
from core.views_health import whatsapp_status
from ops.models import Incident, KeyOccupancy, Role, Staff, Venue
from ops.permissions import actor_label, require
from ops.services import carryover, config, events, incidents, opening, reports, retention, staffdir
from ops.services.localtime import parse_local_at

READ_REFUSALS = {403: s.ErrorResponse, 404: OpenApiResponse(description="Not found or out of scope")}


def _t(ticket) -> str | None:
    return f"#{ticket.display_number:03d}" if ticket else None


def _incident(actor, incident_id) -> Incident:
    incident = Incident.objects.filter(pk=incident_id).select_related("ticket", "event").first()
    if incident is None:
        raise Http404
    scoped_event(actor, incident.event_id)
    return incident


def _incident_summary(i: Incident) -> dict:
    return {"id": i.id, "category": i.category, "status": i.status, "description": i.description,
            "ticket": _t(i.ticket), "ticket_id": i.ticket_id, "created_at": i.created_at}


class Command(APIView):
    permission_classes = [IsConsoleStaff]


# --- incidents ----------------------------------------------------------------------------------

@extend_schema(responses={200: s.IncidentSummary(many=True), **READ_REFUSALS})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def event_incidents(request, event_id):
    event = scoped_event(actor_of(request), event_id)
    rows = event.incidents.select_related("ticket").order_by("status", "-created_at")
    return out(s.IncidentSummary, [_incident_summary(i) for i in rows])


@extend_schema(responses={200: s.IncidentDetail, **READ_REFUSALS})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def incident_detail(request, incident_id):
    i = _incident(actor_of(request), incident_id)
    return out(s.IncidentDetail, {**_incident_summary(i), "resolution": i.resolution,
                                  "resolved_by": i.resolved_by.full_name if i.resolved_by_id else None,
                                  "resolved_at": i.resolved_at,
                                  "notes": [{"author": n.author.full_name, "text": n.text, "created_at": n.created_at}
                                            for n in i.notes.select_related("author").order_by("id")]})


class IncidentNote(Command):
    @command_schema(s.NoteRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, incident_id):
        actor = actor_of(request)
        note = incidents.annotate(actor, _incident(actor, incident_id), validated(s.NoteRequest, request.data)["text"])
        return out(s.IdResponse, {"id": note.id})


class IncidentResolve(Command):
    @command_schema(s.ResolveRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, incident_id):
        actor = actor_of(request)
        data = validated(s.ResolveRequest, request.data)
        return out(s.IdResponse, {"id": incidents.resolve(actor, _incident(actor, incident_id), data["outcome"]).id})


# --- directory ----------------------------------------------------------------------------------

def _staff(actor, staff_id) -> Staff:
    staff = Staff.objects.filter(pk=staff_id, org_id=actor.org_id).first()
    if staff is None:
        raise Http404
    return staff


def _masked(phone: str) -> str:
    return f"{phone[:4]}••••{phone[-3:]}" if len(phone) > 7 else "•••"


class StaffDirectory(Command):
    @extend_schema(responses={200: s.StaffRow(many=True), **READ_REFUSALS})
    @domain_response
    def get(self, request):
        actor = actor_of(request)
        require(actor, Role.MANAGER)
        rows = Staff.objects.filter(org_id=actor.org_id).select_related("user").order_by("-enabled", "full_name")
        return out(s.StaffRow, [{"id": p.id, "full_name": p.full_name, "phone_masked": _masked(p.phone_e164),
                                 "role": p.role, "enabled": p.enabled,
                                 "username": p.user.username if p.user_id else None,
                                 "mfa_enrolled": p.mfa_enrolled_at is not None,
                                 "mfa_locked": p.mfa_locked_at is not None} for p in rows])

    @command_schema(s.CreateStaffRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        data = validated(s.CreateStaffRequest, request.data)
        staff = staffdir.create_staff(actor, data["full_name"], data["phone"], data["role"],
                                      username=data.get("username") or None, password=data.get("password") or None)
        return out(s.IdResponse, {"id": staff.id})


class StaffRole(Command):
    @command_schema(s.RoleRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, staff_id):
        actor = actor_of(request)
        staff = staffdir.change_role(actor, _staff(actor, staff_id), validated(s.RoleRequest, request.data)["role"])
        return out(s.IdResponse, {"id": staff.id})


class StaffDeactivate(Command):
    @command_schema(s.ReasonRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, staff_id):
        actor = actor_of(request)
        reason = validated(s.ReasonRequest, request.data)["reason"]
        return out(s.IdResponse, {"id": staffdir.deactivate(actor, _staff(actor, staff_id), reason).id})


class StaffReactivate(Command):
    @command_schema(None, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, staff_id):
        actor = actor_of(request)
        return out(s.IdResponse, {"id": staffdir.reactivate(actor, _staff(actor, staff_id)).id})


class StaffMfa(Command):
    """Issues TOTP enrolment. Deliberately not replay-stored: the URI is a secret and is shown only once."""

    @extend_schema(request=None, responses={200: s.MfaIssueResponse, **REFUSALS})
    @domain_response
    def post(self, request, staff_id):
        actor = actor_of(request)
        return out(s.MfaIssueResponse, {"otpauth_uri": staffdir.issue_mfa_enrolment(actor, _staff(actor, staff_id))})


# --- events -------------------------------------------------------------------------------------

class Venues(Command):
    @extend_schema(responses={200: s.VenueRow(many=True), **READ_REFUSALS})
    @domain_response
    def get(self, request):
        actor = actor_of(request)
        require(actor, Role.MANAGER)
        venues = (Venue.objects.filter(org_id=actor.org_id).prefetch_related("zones")
                  .annotate(hooks=Coalesce(Sum("key_stations__hook_count"), 0)).order_by("name"))
        return out(s.VenueRow, [{"id": v.id, "name": v.name, "time_zone": v.timezone, "key_hooks": v.hooks,
                                 "zones": [z.code for z in v.zones.all() if z.active]} for v in venues])


class CreateEvent(Command):
    @command_schema(s.CreateEventRequest, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        data = validated(s.CreateEventRequest, request.data)
        venue = Venue.objects.filter(pk=data["venue_id"], org_id=actor.org_id).first()
        if venue is None:
            raise Http404
        starts_at = parse_local_at(venue, data["starts_at_local"])
        return out(s.IdResponse, {"id": events.create_event(actor, venue, data["name"], starts_at).id})


class CloseEvent(Command):
    @command_schema(None, s.IdResponse)
    @idempotent_post
    @domain_response
    def post(self, request, event_id):
        actor = actor_of(request)
        return out(s.IdResponse, {"id": events.close_event(actor, scoped_event(actor, event_id)).id})


# --- reports and exports --------------------------------------------------------------------------

@extend_schema(responses={200: s.EventReport, **READ_REFUSALS})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
@domain_response
def event_report(request, event_id):
    actor = actor_of(request)
    return out(s.EventReport, reports.event_report(actor, scoped_event(actor, event_id)))


def _cell(value) -> str:
    """CSV formula-injection guard: cells starting with = + - @ (or tab/CR) are prefixed with a quote."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _csv(rows: list[dict], filename: str) -> HttpResponse:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(v) for k, v in row.items()})
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


CSV_RESPONSE = {(200, "text/csv"): OpenApiTypes.STR, **READ_REFUSALS}


@extend_schema(parameters=[OpenApiParameter("state", str, required=False)], responses=CSV_RESPONSE)
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
@domain_response
def export_tickets(request, event_id):
    actor = actor_of(request)
    event = scoped_event(actor, event_id)
    rows = reports.ticket_rows(actor, event, state=request.query_params.get("state") or None)
    return _csv(rows, f"tickets-event-{event.id}.csv")


@extend_schema(responses=CSV_RESPONSE)
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
@domain_response
def export_guest_phones(request, event_id):
    actor = actor_of(request)
    event = scoped_event(actor, event_id)
    return _csv(reports.guest_phone_rows(actor, event), f"guest-phones-event-{event.id}.csv")


# --- operations -----------------------------------------------------------------------------------

@extend_schema(responses={200: s.OpeningCheck, **READ_REFUSALS})
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def opening_check(request, event_id):
    return out(s.OpeningCheck, opening.opening_check(scoped_event(actor_of(request), event_id)))


class DeadLetters(Command):
    @extend_schema(responses={200: s.DeadLetter(many=True), **READ_REFUSALS})
    @domain_response
    def get(self, request):
        actor = actor_of(request)
        require(actor, Role.ADMIN)
        rows = opening.dead_letters(actor.org).select_related("staff", "ticket")
        return out(s.DeadLetter, [{"id": r.id, "status": r.status, "kind": r.kind,
                                   "recipient": r.staff.full_name if r.staff_id else "guest", "ticket": _t(r.ticket),
                                   "failure_class": r.failure_class, "last_error": r.last_error,
                                   "created_at": r.created_at} for r in rows])


class ReplayDeadLetter(Command):
    @command_schema(None, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request, outbox_id):
        actor = actor_of(request)
        row = opening.dead_letters(actor.org).filter(pk=outbox_id).first()
        if row is None:
            raise Http404
        return out(s.OkResponse, {"ok": opening.replay_dead_letter(actor, row)})


class CarryoverRegister(Command):
    @extend_schema(responses={200: s.CarryoverRow(many=True), **READ_REFUSALS})
    @domain_response
    def get(self, request):
        actor = actor_of(request)
        require(actor, Role.MANAGER)
        rows = []
        held = Prefetch("ticket__key_occupancies", queryset=KeyOccupancy.objects.filter(released_at__isnull=True),
                        to_attr="held_keys")
        for case in carryover.register(actor.org).prefetch_related(held):
            ticket = case.ticket
            occ = ticket.held_keys[0] if ticket.held_keys else None
            rows.append({"id": case.id, "ticket": _t(ticket), "ticket_id": ticket.id, "event": ticket.event.name,
                         "event_id": ticket.event_id,
                         "status": case.status, "custodian": case.custodian, "plan": case.plan,
                         "location": f"{ticket.location_zone.code} {ticket.location_detail}".strip()
                         if ticket.location_zone_id else "", "hook": occ.hook_number if occ else None,
                         "proposed_at": case.proposed_at})
        return out(s.CarryoverRow, rows)


# --- configuration --------------------------------------------------------------------------------

class Config(Command):
    @extend_schema(responses={200: s.ConfigResponse, **READ_REFUSALS})
    @domain_response
    def get(self, request):
        from messaging.catalogue import MESSAGES

        actor = actor_of(request)
        require(actor, Role.ADMIN)
        return out(s.ConfigResponse, {"version": config.get_config(actor.org).version,
                                      "timings": config.current_timings(actor.org),
                                      "retention_days": config.retention_days(actor.org),
                                      "template_overrides": config.template_overrides(actor.org),
                                      "catalogue": MESSAGES, "retention_preview": retention.preview(actor.org)})


class ConfigTimings(Command):
    @command_schema(s.TimingsRequest, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        data = validated(s.TimingsRequest, request.data)
        config.update_timings(actor, actor.org, data["timings"], expected_version=data["version"])
        return out(s.OkResponse, {"ok": True})


class ConfigRetention(Command):
    @command_schema(s.RetentionRequest, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        data = validated(s.RetentionRequest, request.data)
        config.update_retention(actor, actor.org, data["retention_days"], expected_version=data["version"])
        return out(s.OkResponse, {"ok": True})


class ConfigTemplates(Command):
    @command_schema(s.TemplatesRequest, s.OkResponse)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        data = validated(s.TemplatesRequest, request.data)
        config.update_templates(actor, actor.org, {k: dict(v) if v is not None else None
                                                   for k, v in data["overrides"].items()},
                                expected_version=data["version"])
        return out(s.OkResponse, {"ok": True})


class ApplyRetention(Command):
    @command_schema(None, s.RetentionResult)
    @idempotent_post
    @domain_response
    def post(self, request):
        actor = actor_of(request)
        return out(s.RetentionResult, retention.apply(actor, actor.org))


# --- integrations ---------------------------------------------------------------------------------

class WhatsAppIntegrationView(Command):
    """Super admin only. Shows readiness flags, never credential values; credentials live in the secret store."""

    @extend_schema(responses={200: s.WhatsAppIntegration, **READ_REFUSALS})
    @domain_response
    def get(self, request):
        actor = actor_of(request)
        require(actor, Role.SUPER_ADMIN)
        audit("integration.view", actor_id=actor.id, actor_label=actor_label(actor), channel="console",
              entity_type="integration", summary={"name": "whatsapp"})
        return out(s.WhatsAppIntegration, {
            "status": whatsapp_status(), "transport": settings.WHATSAPP_TRANSPORT,
            "sender_ready": bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID),
            "signature_secret_set": bool(settings.WHATSAPP_APP_SECRET) and settings.WHATSAPP_TRANSPORT != "fake",
            "webhook_verification_set": bool(getattr(settings, "WHATSAPP_VERIFY_TOKEN", ""))})
