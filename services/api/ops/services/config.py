"""Operating configuration (admin+): timings, message copy and retention. Every change is audited with its
before/after values. Issued offers keep their stored deadlines; new offers use the new values (docs/03)."""

import string

from django.db import transaction

from core.audit import audit
from core.errors import DomainError
from ops.models import OperatingConfig, Role
from ops.permissions import actor_label, require

TIMING_BOUNDS = {
    "offer_window_s": (10, 600), "hard_limit_s": (20, 1200), "send_pending_warning_s": (5, 300),
    "attempts_before_alert": (1, 10), "cooldown_s": (0, 3600), "wait_warning_s": (30, 7200),
    "wait_critical_s": (60, 14400), "accepted_warning_s": (30, 7200), "ready_warning_s": (30, 7200),
}
RETENTION_KEYS = ("guest_contact", "intake_photos", "incident_evidence")


def get_config(org) -> OperatingConfig:
    cfg, _ = OperatingConfig.objects.get_or_create(org=org)
    return cfg


def current_timings(org) -> dict:
    from ops.services.dispatch import DEFAULT_TIMINGS

    return {**DEFAULT_TIMINGS, **get_config(org).timings}


def retention_days(org) -> dict:
    return {key: int(get_config(org).retention_days.get(key, 0)) for key in RETENTION_KEYS}


def _audit(action, actor, org, before, after):
    audit(action, actor_id=actor.id, actor_label=actor_label(actor), channel="console", entity_type="org",
          entity_id=org.id, summary={"before": before, "after": after})


def update_timings(actor, org, changes: dict) -> dict:
    require(actor, Role.ADMIN)
    if actor.org_id != org.id:
        raise DomainError("forbidden")
    for key, value in changes.items():
        if key not in TIMING_BOUNDS or not isinstance(value, int) or isinstance(value, bool):
            raise DomainError("invalid_setting")
        low, high = TIMING_BOUNDS[key]
        if not low <= value <= high:
            raise DomainError("invalid_setting")
    with transaction.atomic():
        cfg = OperatingConfig.objects.select_for_update(no_key=True).get(pk=get_config(org).pk)
        before = current_timings(org)
        cfg.timings = {**cfg.timings, **changes}
        cfg.save(update_fields=["timings", "updated_at"])
        after = {**before, **changes}
        if after["offer_window_s"] > after["hard_limit_s"]:
            raise DomainError("invalid_setting")
        _audit("config.timings", actor, org, before, after)
    return after


def _fields(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}


def update_templates(actor, org, overrides: dict) -> dict:
    """Wording only: placeholders must match the catalogue, and buttons keep their actions (AT-47)."""
    from messaging.catalogue import MESSAGES

    require(actor, Role.ADMIN)
    if actor.org_id != org.id:
        raise DomainError("forbidden")
    for key, copy in overrides.items():
        if key not in MESSAGES or set(copy) != {"ar", "en"}:
            raise DomainError("invalid_setting")
        for lang in ("ar", "en"):
            if not str(copy[lang]).strip() or _fields(copy[lang]) != _fields(MESSAGES[key][lang]):
                raise DomainError("placeholders_mismatch")
    with transaction.atomic():
        cfg = OperatingConfig.objects.select_for_update(no_key=True).get(pk=get_config(org).pk)
        before = {k: cfg.template_overrides.get(k) for k in overrides}
        cfg.template_overrides = {**cfg.template_overrides, **overrides}
        cfg.save(update_fields=["template_overrides", "updated_at"])
        _audit("config.templates", actor, org, before, overrides)
    return cfg.template_overrides


def update_retention(actor, org, days: dict) -> dict:
    require(actor, Role.ADMIN)
    if actor.org_id != org.id:
        raise DomainError("forbidden")
    for key, value in days.items():
        if key not in RETENTION_KEYS or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DomainError("invalid_setting")
    with transaction.atomic():
        cfg = OperatingConfig.objects.select_for_update(no_key=True).get(pk=get_config(org).pk)
        before = retention_days(org)
        cfg.retention_days = {**cfg.retention_days, **days}
        cfg.save(update_fields=["retention_days", "updated_at"])
        _audit("config.retention", actor, org, before, {**before, **days})
    return retention_days(org)


def template_overrides(org) -> dict:
    return get_config(org).template_overrides
