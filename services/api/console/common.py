"""Shared console API plumbing: actor resolution, scoping, idempotency and error mapping."""

import functools
import hashlib
import json

from django.http import Http404
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from core.errors import DomainError
from core.idempotency import IdempotencyMismatch, idempotent
from ops.models import ROLE_RANK, Event, EventAssignment, Role, Ticket
from ops.permissions import can_access_event


class PreconditionRequired(APIException):
    status_code = 428
    default_detail = "Idempotency-Key header is required"
    default_code = "idempotency_key_required"


def actor_of(request):
    user = request.user
    staff = getattr(user, "staff", None) if user and user.is_authenticated else None
    if staff is None or not staff.enabled:
        raise PermissionDenied("no console access")
    return staff


def session_staff(request):
    """The signed-in, enabled person behind a session that is still valid for their current role, else None."""
    user = request.user
    staff = getattr(user, "staff", None) if user and user.is_authenticated else None
    if not (staff and staff.enabled):
        return None
    if request.session.get("epoch") != staff.session_epoch:
        return None  # role changed, deactivated, password or second factor reset since this session signed in
    if staff.role == Role.ADMIN and request.session.get("mfa_ok") is not True:
        return None
    return staff


class IsSignedInStaff(BasePermission):
    """Any role: only for what every signed-in person needs (who am I)."""

    def has_permission(self, request, view):
        return session_staff(request) is not None


class IsConsoleStaff(BasePermission):
    """Supervisors and admins. A valet account never passes: valets use the valet endpoints only (ADR-0011)."""

    def has_permission(self, request, view):
        staff = session_staff(request)
        return staff is not None and ROLE_RANK[staff.role] >= ROLE_RANK[Role.SUPERVISOR]


class IsValet(BasePermission):
    """The valet app: valets only, so a console account cannot quietly take a valet's task."""

    def has_permission(self, request, view):
        staff = session_staff(request)
        return staff is not None and staff.role == Role.VALET


def events_for(actor):
    qs = Event.objects.filter(org_id=actor.org_id)
    if ROLE_RANK[actor.role] >= ROLE_RANK[Role.ADMIN]:
        return qs
    return qs.filter(id__in=EventAssignment.objects.filter(staff=actor).values("event_id"))


def scoped_event(actor, event_id) -> Event:
    event = events_for(actor).filter(pk=event_id).first()
    if event is None:
        raise Http404
    return event


def scoped_ticket(actor, ticket_id) -> Ticket:
    ticket = Ticket.objects.filter(pk=ticket_id, event__in=events_for(actor)).select_related("event").first()
    if ticket is None or not can_access_event(actor, ticket.event):
        raise Http404
    return ticket


class InvalidInput(Exception):
    def __init__(self, errors):
        super().__init__("invalid_input")
        self.errors = errors


def validated(serializer_class, data) -> dict:
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        raise InvalidInput(serializer.errors)
    return serializer.validated_data


def out(serializer_class, payload, status: int = 200) -> Response:
    """Shape a response through its contract serializer, so the wire format always matches the schema."""
    many = isinstance(payload, list)
    return Response(serializer_class(payload, many=many).data, status=status)


def domain_response(fn):
    """Map DomainError to 409 (forbidden → 403) and invalid input to 400, each with a stable code."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except InvalidInput as err:
            return Response({"code": "invalid_input", "fields": err.errors}, status=400)
        except DomainError as err:
            status = 403 if err.code == "forbidden" else 409
            return Response({"code": err.code}, status=status)

    return wrapper


def idempotent_post(fn):
    """Requires an Idempotency-Key; replays the stored result for a repeated key (AT-34)."""

    @functools.wraps(fn)
    def wrapper(view, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 128:
            raise PreconditionRequired()
        actor = actor_of(request)
        scope = f"staff:{actor.id}:{request.path}"
        body = json.dumps(request.data, sort_keys=True, separators=(",", ":"), default=str)
        fingerprint = hashlib.sha256(body.encode()).hexdigest()

        def run() -> dict:
            response = fn(view, request, *args, **kwargs)
            if response.status_code >= 400:
                raise _Refused(response)
            return {"status": response.status_code, "data": response.data}

        try:
            stored, _replayed = idempotent(scope, key, run, fingerprint=fingerprint)
        except _Refused as refused:
            return refused.response
        except IdempotencyMismatch:
            return Response({"code": "idempotency_mismatch"}, status=409)
        return Response(stored["data"], status=stored["status"])

    return wrapper


class _Refused(Exception):
    """A refused command is not stored, so the client may correct the input and retry with the same key."""

    def __init__(self, response):
        super().__init__("refused")
        self.response = response
