import contextvars
import uuid

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def current_correlation_id() -> str:
    value = correlation_id.get()
    if not value:
        value = uuid.uuid4().hex
        correlation_id.set(value)
    return value


def staff_channel() -> str:
    """Where staff act and are told about work: "app" (ADR-0011) or the retired "whatsapp" flow."""
    from django.conf import settings

    return settings.STAFF_CHANNEL


def staff_app() -> bool:
    return staff_channel() == "app"
