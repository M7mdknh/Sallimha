"""Operating configuration (admin): timings, message copy overrides and retention. Filled in by Task 2.4."""

from ops.services.dispatch import DEFAULT_TIMINGS


def current_timings(org) -> dict:
    return dict(DEFAULT_TIMINGS)
