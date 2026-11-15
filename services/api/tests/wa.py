"""Drive the system through simulated WhatsApp traffic (SIMULATED)."""

import uuid

from django.utils import timezone

from messaging import inbound
from messaging.models import MessageOutbox, SimulatedMedia
from messaging.simulator import build_message_payload, post_inbound
from tests.ops.intake_helpers import JPEG


def say(phone, text):
    post_inbound(build_message_payload(from_phone=phone, text=text))
    inbound.process_inbox(timezone.now())


def tap(phone, payload, context_id=None, from_user_id=None):
    post_inbound(build_message_payload(from_phone=phone, button_payload=payload, context_id=context_id,
                                       from_user_id=from_user_id))
    inbound.process_inbox(timezone.now())


def photo(phone):
    media_id = f"SIMMEDIA.{uuid.uuid4().hex}"
    SimulatedMedia.objects.create(media_id=media_id, content=JPEG, content_type="image/jpeg")
    post_inbound(build_message_payload(from_phone=phone, image_id=media_id))
    inbound.process_inbox(timezone.now())


def last(staff=None, binding=None, kind=None):
    qs = MessageOutbox.objects.order_by("-id")
    qs = qs.filter(staff=staff) if staff is not None else qs.filter(binding=binding)
    if kind:
        qs = qs.filter(kind=kind)
    return qs.first()


def button(row, key):
    return next(b[0] for b in row.buttons if b[1] == key)
