import pytest

from core.idempotency import idempotent
from core.models import AuditEvent


@pytest.mark.django_db
def test_idempotent_replays_result_without_second_effect():
    calls = []

    def effect():
        calls.append(1)
        AuditEvent.objects.create(action="effect", actor_label="t", channel="console")
        return {"ok": True, "n": len(calls)}

    first, replayed1 = idempotent("staff:1", "key-1", effect)
    second, replayed2 = idempotent("staff:1", "key-1", effect)
    assert first == second == {"ok": True, "n": 1}
    assert (replayed1, replayed2) == (False, True)
    assert AuditEvent.objects.filter(action="effect").count() == 1


@pytest.mark.django_db
def test_idempotency_key_is_scoped_per_actor():
    a, _ = idempotent("staff:1", "same", lambda: {"who": 1})
    b, _ = idempotent("staff:2", "same", lambda: {"who": 2})
    assert (a, b) == ({"who": 1}, {"who": 2})
