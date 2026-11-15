"""Development-only WhatsApp simulator API (SIMULATOR_ENABLED). Everything here is SIMULATED: payloads go
through the real signature check, inbox and worker, but nothing reaches a real phone."""

import uuid

from django.conf import settings
from django.http import Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from console.common import IsConsoleStaff, actor_of
from messaging.models import SimulatedMedia, SimulatedMessage
from messaging.simulator import build_message_payload, post_inbound
from ops.models import Shift

# A tiny valid JPEG header + filler: a synthetic stand-in for a vehicle photo.
_SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0" + b"SALLIMHA-SIMULATED-PHOTO" * 8


def _guard():
    if not settings.SIMULATOR_ENABLED:
        raise Http404


@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def phones(request):
    _guard()
    actor = actor_of(request)
    rows = []
    for shift in Shift.objects.filter(ended_at__isnull=True, staff__org_id=actor.org_id).select_related("staff"):
        rows.append({"phone": shift.staff.phone_e164, "label": shift.staff.full_name, "role": shift.staff.role})
    staff_phones = {r["phone"] for r in rows}
    for phone in (SimulatedMessage.objects.exclude(phone__in=staff_phones).values_list("phone", flat=True)
                  .distinct()):
        rows.append({"phone": phone, "label": "Guest (simulated)", "role": "GUEST"})
    return Response(rows)


@api_view(["GET"])
@permission_classes([IsConsoleStaff])
def messages(request):
    _guard()
    phone = request.query_params.get("phone", "")
    rows = SimulatedMessage.objects.filter(phone=phone).order_by("id")[:200]
    return Response([{"id": m.id, "direction": m.direction, "body": m.body, "buttons": m.buttons, "kind": m.kind,
                      "provider_message_id": m.provider_message_id, "created_at": m.created_at} for m in rows])


@api_view(["POST"])
@permission_classes([IsConsoleStaff])
def send(request):
    _guard()
    phone = str(request.data.get("phone", "")).strip()
    if not phone.startswith("+"):
        return Response({"code": "phone_required"}, status=400)
    text = request.data.get("text")
    button = request.data.get("button_payload")
    context_id = request.data.get("context_id") or None
    media_id = None
    if request.data.get("photo"):
        media_id = f"SIMMEDIA.{uuid.uuid4().hex}"
        SimulatedMedia.objects.create(media_id=media_id, content=_SYNTHETIC_JPEG, content_type="image/jpeg")
    payload = build_message_payload(from_phone=phone, text=text, button_payload=button, image_id=media_id,
                                    context_id=context_id)
    post_inbound(payload)
    label = text or (str(request.data.get("button_title", "")) or "[button]") if not media_id else "[photo]"
    SimulatedMessage.objects.create(direction="in", phone=phone, kind="photo" if media_id else "text", body=label,
                                    media_id=media_id or "")
    return Response({"ok": True, "simulated": True})
