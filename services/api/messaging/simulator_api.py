"""Development-only WhatsApp simulator API (SIMULATOR_ENABLED). Everything here is SIMULATED: payloads go
through the real signature check, inbox and worker, but nothing reaches a real phone."""

import uuid

from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import api_view, permission_classes

from console import serializers as cs
from console.common import IsConsoleStaff, actor_of, domain_response, out, validated
from core.errors import DomainError
from messaging.models import SimulatedMedia, SimulatedMessage, SimulatorControl
from messaging.simulator import build_message_payload, post_inbound
from ops.models import Shift

# A tiny valid JPEG header + filler: a synthetic stand-in for a vehicle photo.
_SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0" + b"SALLIMHA-SIMULATED-PHOTO" * 8


def _guard():
    if not settings.SIMULATOR_ENABLED:
        raise Http404


@extend_schema(responses={200: cs.SimPhone(many=True)}, tags=["dev-simulator"])
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def phones(request):
    _guard()
    actor = actor_of(request)
    from core.context import staff_app

    rows = []
    if not staff_app():  # staff work in the app (ADR-0011): the simulator stands in for customers' phones only
        for shift in Shift.objects.filter(ended_at__isnull=True, staff__org_id=actor.org_id).select_related("staff"):
            rows.append({"phone": shift.staff.phone_e164, "label": shift.staff.full_name, "role": shift.staff.role})
    staff_phones = {r["phone"] for r in rows}
    for phone in (SimulatedMessage.objects.exclude(phone__in=staff_phones).values_list("phone", flat=True)
                  .distinct()):
        rows.append({"phone": phone, "label": "Guest (simulated)", "role": "GUEST"})
    return out(cs.SimPhone, rows)


@extend_schema(parameters=[OpenApiParameter("phone", str, required=True)], responses={200: cs.SimMessage(many=True)},
               tags=["dev-simulator"])
@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def messages(request):
    _guard()
    phone = request.query_params.get("phone", "")
    rows = SimulatedMessage.objects.filter(phone=phone).order_by("id")[:200]
    return out(cs.SimMessage, [{"id": m.id, "direction": m.direction, "body": m.body, "buttons": m.buttons,
                                "kind": m.kind, "provider_message_id": m.provider_message_id,
                                "created_at": m.created_at} for m in rows])


@extend_schema(request=cs.SimSendRequest, responses={200: cs.SimSendResponse, 400: cs.ErrorResponse},
               tags=["dev-simulator"])
@api_view(["POST"])
@permission_classes([IsConsoleStaff])
@domain_response
def send(request):
    _guard()
    data = validated(cs.SimSendRequest, request.data)
    if SimulatorControl.outage_active():
        raise DomainError("simulated_outage")  # the simulated provider delivers no webhooks while it is down
    phone = data["phone"]
    media_id = None
    if data.get("photo"):
        media_id = f"SIMMEDIA.{uuid.uuid4().hex}"
        SimulatedMedia.objects.create(media_id=media_id, content=_SYNTHETIC_JPEG, content_type="image/jpeg")
    payload = build_message_payload(from_phone=phone, text=data.get("text"), button_payload=data.get("button_payload"),
                                    image_id=media_id, context_id=data.get("context_id"))
    post_inbound(payload)
    label = "[photo]" if media_id else (data.get("text") or data.get("button_title") or "[button]")
    SimulatedMessage.objects.create(direction="in", phone=phone, kind="photo" if media_id else "text", body=label,
                                    media_id=media_id or "")
    return out(cs.SimSendResponse, {"ok": True, "simulated": True})


@extend_schema(request=cs.SimOutageRequest, responses={200: cs.SimOutage}, tags=["dev-simulator"])
@api_view(["GET", "POST"])
@permission_classes([IsConsoleStaff])
@domain_response
def outage_mode(request):
    """Simulated provider outage: every send fails and inbound stops until it is switched off (SIMULATED)."""
    _guard()
    if request.method == "POST":
        SimulatorControl.set_outage(validated(cs.SimOutageRequest, request.data)["down"])
    return out(cs.SimOutage, {"down": SimulatorControl.outage_active()})
