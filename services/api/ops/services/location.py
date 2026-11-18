"""Where a parked car is (ADR-0013): zone and spot (required), floor and a short description, and optionally one
confirmed pin. A pin is the browser's geolocation beside the car (with its reported accuracy) or a place the valet
tapped or dragged on the map. The venue centre is never a pin; nothing is invented. Every writer of zone and spot
sets or clears the pin through `apply_place`, so an old pin never outlives its place."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from core.errors import DomainError

MAX_GPS_ACCURACY_M = 150.0  # proposed default: a coarser fix is not saved unless the valet places the pin
_STEP = Decimal("0.000001")


@dataclass(frozen=True)
class Pin:
    lat: Decimal
    lng: Decimal
    source: str               # gps | pin
    accuracy_m: float | None  # gps only, as the browser reported it
    device_at: datetime | None  # capture time reported by the device (untrusted; the server time is kept too)


def _coordinate(value, bound: int) -> Decimal:
    try:
        number = Decimal(str(value)).quantize(_STEP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DomainError("location_out_of_range") from exc
    if not -bound <= number <= bound:
        raise DomainError("location_out_of_range")
    return number


def pin_from(lat=None, lng=None, source: str = "", accuracy_m=None, device_at=None) -> Pin | None:
    if lat is None and lng is None and not source:
        return None
    if lat is None or lng is None:
        raise DomainError("location_pin_incomplete")
    if source not in ("gps", "pin"):
        raise DomainError("location_source_invalid")  # the venue centre or anything unconfirmed is never saved
    if source == "gps":
        if accuracy_m is None or float(accuracy_m) <= 0:
            raise DomainError("location_accuracy_required")
        if float(accuracy_m) > MAX_GPS_ACCURACY_M:
            raise DomainError("location_inaccurate")
        accuracy = round(float(accuracy_m), 1)
    else:
        accuracy = None
    return Pin(lat=_coordinate(lat, 90), lng=_coordinate(lng, 180), source=source, accuracy_m=accuracy,
               device_at=device_at)


PLACE_FIELDS = ["location_zone", "location_detail", "location_floor", "location_note", "location_lat", "location_lng",
                "location_source", "location_accuracy_m", "location_device_at", "location_recorded_at"]


def apply_place(ticket, *, zone, spot: str, floor: str = "", note: str = "", pin: Pin | None = None, now) -> None:
    """Sets the whole place at once. Without a pin, any earlier pin is cleared."""
    ticket.location_zone = zone
    ticket.location_detail = (spot or "").strip()[:80]
    ticket.location_floor = (floor or "").strip()[:20]
    ticket.location_note = (note or "").strip()[:120]
    ticket.location_lat = pin.lat if pin else None
    ticket.location_lng = pin.lng if pin else None
    ticket.location_source = pin.source if pin else ""
    ticket.location_accuracy_m = pin.accuracy_m if pin else None
    ticket.location_device_at = pin.device_at if pin else None
    ticket.location_recorded_at = now if pin else None


def describe(ticket) -> dict:
    """The place as staff read it, plus the pin if one was confirmed."""
    zone = ticket.location_zone
    pin = None
    if ticket.location_lat is not None:
        pin = {"lat": float(ticket.location_lat), "lng": float(ticket.location_lng), "source": ticket.location_source,
               "accuracy_m": ticket.location_accuracy_m, "recorded_at": ticket.location_recorded_at}
    return {"zone": zone.code if zone else "", "spot": ticket.location_detail, "floor": ticket.location_floor,
            "note": ticket.location_note, "pin": pin}
