"""Times entered in the console are the venue's wall-clock time (Venue.timezone, default Asia/Riyadh), never the
browser's. Stored values are timezone-aware."""

from datetime import datetime
from zoneinfo import ZoneInfo

from core.errors import DomainError


def venue_zone(event) -> ZoneInfo:
    return ZoneInfo(event.venue.timezone or "Asia/Riyadh")


def parse_local(event, value: str) -> datetime:
    """'2026-11-16T20:30' (no offset) at the event's venue → aware datetime. Offsets are refused so a browser's
    zone can never leak in."""
    try:
        parsed = datetime.fromisoformat((value or "").strip())
    except ValueError as exc:
        raise DomainError("invalid_time") from exc
    if parsed.tzinfo is not None:
        raise DomainError("invalid_time")
    return parsed.replace(tzinfo=venue_zone(event))
