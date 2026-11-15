from core.context import current_correlation_id
from core.models import AuditEvent


def audit(
    action: str,
    *,
    actor_id: int | None,
    actor_label: str,
    channel: str,
    entity_type: str = "",
    entity_id: int | None = None,
    event_id: int | None = None,
    summary: dict | None = None,
) -> AuditEvent:
    """Append an audit row. Summaries must not contain raw phones, codes or tokens."""
    return AuditEvent.objects.create(
        action=action,
        actor_id=actor_id,
        actor_label=actor_label[:120],
        channel=channel,
        entity_type=entity_type,
        entity_id=entity_id,
        event_id=event_id,
        summary=summary or {},
        correlation_id=current_correlation_id(),
    )
