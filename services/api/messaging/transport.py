"""WhatsApp transport adapter. Business code never sees provider payloads.

FakeTransport (local simulator) results are SIMULATED. CloudApiTransport builds requests in the
documented Cloud API shapes (docs/11) but has NOT been run against a real provider: BLOCKED
until a staging sender, token and approved templates exist.
"""

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field

from django.conf import settings


@dataclass(frozen=True)
class OutboundPayload:
    outbox_id: int
    to_phone: str
    mode: str  # session | template
    template: str
    language: str
    text: str
    params: dict = field(default_factory=dict)
    buttons: list[tuple[str, str]] = field(default_factory=list)  # (payload, title)


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str


class TransientSendError(Exception):
    pass


class PermanentSendError(Exception):
    pass


class UnknownSendOutcome(Exception):
    """The provider may have accepted the message; never assume either way."""


class FakeTransport:
    name = "fake"

    def send(self, payload: OutboundPayload) -> SendResult:
        from messaging.models import SimulatedMessage, SimulatorControl

        injected = SimulatorControl.take()
        if injected == "transient":
            raise TransientSendError("simulated transient failure")
        if injected == "permanent":
            raise PermanentSendError("simulated permanent failure")
        message_id = f"wamid.SIM.{uuid.uuid4().hex}"
        SimulatedMessage.objects.create(
            direction="out", phone=payload.to_phone, kind=payload.mode, body=payload.text,
            buttons=[list(b) for b in payload.buttons], provider_message_id=message_id, outbox_id=payload.outbox_id,
        )
        if injected == "unknown":
            raise UnknownSendOutcome("simulated lost response after provider acceptance")
        return SendResult(provider_message_id=message_id)

    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        from messaging.models import SimulatedMedia

        media = SimulatedMedia.objects.filter(media_id=media_id).first()
        if media is None:
            raise PermanentSendError("unknown simulated media")
        return bytes(media.content), media.content_type


def build_cloud_request(payload: OutboundPayload, template_name: str | None = None) -> dict:
    """Cloud API request body (shapes per docs/11). Interactive replies: ≤3 buttons, titles ≤20 chars."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": payload.to_phone.lstrip("+")}
    if payload.mode == "template":
        components = [{"type": "body", "parameters": [{"type": "text", "text": str(v)}
                                                      for v in payload.params.values()]}]
        components += [
            {"type": "button", "sub_type": "quick_reply", "index": str(i),
             "parameters": [{"type": "payload", "payload": button_payload}]}
            for i, (button_payload, _title) in enumerate(payload.buttons)
        ]
        return base | {"type": "template", "template": {
            "name": template_name or payload.template.replace(".", "_"),
            "language": {"code": payload.language}, "components": components}}
    if payload.buttons:
        return base | {"type": "interactive", "interactive": {
            "type": "button", "body": {"text": payload.text},
            "action": {"buttons": [{"type": "reply", "reply": {"id": p, "title": t[:20]}}
                                   for p, t in payload.buttons[:3]]}}}
    return base | {"type": "text", "text": {"body": payload.text}}


class CloudApiTransport:
    name = "cloud"
    graph_version = "v24.0"

    def send(self, payload: OutboundPayload) -> SendResult:
        if not (settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID):
            raise PermanentSendError("WhatsApp Cloud API is not configured")
        url = f"https://graph.facebook.com/{self.graph_version}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        request = urllib.request.Request(  # noqa: S310 — fixed https Graph API host
            url, data=json.dumps(build_cloud_request(payload)).encode(), method="POST",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise TransientSendError(f"http {exc.code}") from exc
            raise PermanentSendError(f"http {exc.code}") from exc
        except TimeoutError as exc:
            raise UnknownSendOutcome("timeout after request") from exc
        except urllib.error.URLError as exc:
            raise TransientSendError("network") from exc
        return SendResult(provider_message_id=body["messages"][0]["id"])

    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        raise PermanentSendError("Cloud media download not implemented until staging (BLOCKED)")


def get_transport():
    return FakeTransport() if settings.WHATSAPP_TRANSPORT == "fake" else CloudApiTransport()
