import contextvars
import uuid

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def current_correlation_id() -> str:
    value = correlation_id.get()
    if not value:
        value = uuid.uuid4().hex
        correlation_id.set(value)
    return value
