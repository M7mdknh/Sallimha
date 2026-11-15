"""Login brute-force protection (AT-46 rate-limit part; Security Guidance findings on f58a19b)."""

import threading
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from console import auth_flow
from core.models import AuditEvent, LoginThrottle

PASSWORD = "correct horse battery 9"


def _login(username, password, ip="10.0.0.1", client=None):
    client = client or APIClient()
    return client.post("/api/auth/login", {"username": username, "password": password}, format="json",
                       REMOTE_ADDR=ip)


@pytest.fixture
def account(world):
    user = get_user_model().objects.create_user(username="sup1", password=PASSWORD)
    world.supervisor.user = user
    world.supervisor.save()
    return user


def test_pair_locked_after_5_failures(account):
    for _ in range(5):
        assert _login("sup1", "wrong").status_code == 400
    locked = _login("sup1", PASSWORD)
    assert locked.status_code == 429 and locked.json() == {"code": "too_many_attempts"}
    assert AuditEvent.objects.filter(action="auth.locked").exists()


def test_attacker_cannot_lock_out_victim_from_another_ip(account):
    """Submitting a known username from one place must not block its owner elsewhere."""
    for _ in range(12):
        _login("sup1", "wrong", ip="203.0.113.9")
    assert _login("sup1", PASSWORD, ip="198.51.100.20").status_code == 200


def test_unknown_user_and_wrong_password_look_identical(account):
    a = _login("nobody-here", "x")
    b = _login("sup1", "x")
    assert (a.status_code, a.json()) == (b.status_code, b.json())
    for _ in range(5):
        _login("nobody-here", "x", ip="10.9.9.9")
        _login("sup1", "x", ip="10.8.8.8")
    assert _login("nobody-here", "x", ip="10.9.9.9").json() == _login("sup1", "x", ip="10.8.8.8").json()


def test_lockout_expires_after_window(account):
    for _ in range(5):
        _login("sup1", "wrong")
    assert _login("sup1", PASSWORD).status_code == 429
    LoginThrottle.objects.update(window_start=timezone.now() - auth_flow.WINDOW - timedelta(seconds=1))
    assert _login("sup1", PASSWORD).status_code == 200


def test_successful_login_resets_pair_counter(account):
    for _ in range(4):
        _login("sup1", "wrong")
    assert _login("sup1", PASSWORD).status_code == 200
    for _ in range(4):
        assert _login("sup1", "wrong").status_code == 400
    assert _login("sup1", PASSWORD).status_code == 200


def test_ip_spraying_limited_across_usernames(account):
    for i in range(auth_flow.IP_MAX_FAILURES):
        _login(f"guess{i}", "wrong", ip="192.0.2.50")
    assert _login("sup1", PASSWORD, ip="192.0.2.50").status_code == 429
    assert _login("sup1", PASSWORD, ip="192.0.2.51").status_code == 200


def test_forwarded_for_ignored_unless_proxy_trusted(account, settings):
    settings.TRUSTED_PROXY_COUNT = 0
    for i in range(5):
        APIClient().post("/api/auth/login", {"username": "sup1", "password": "wrong"}, format="json",
                         REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR=f"1.1.1.{i}")
    assert _login("sup1", PASSWORD, ip="10.0.0.1").status_code == 429


@pytest.mark.django_db(transaction=True)
def test_concurrent_attempts_cannot_exceed_cap():
    """Parallel requests (as from several app workers) never get more than MAX_FAILURES password checks."""
    from ops.models import Role
    from tests.factories import make_org, make_staff

    user = get_user_model().objects.create_user(username="race", password=PASSWORD)
    make_staff(make_org(), Role.SUPERVISOR, user=user)
    n = 12
    barrier = threading.Barrier(n)
    statuses = []
    lock = threading.Lock()

    def attempt():
        try:
            barrier.wait()
            code = _login("race", "wrong", ip="10.1.1.1").status_code
            with lock:
                statuses.append(code)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert statuses.count(400) == auth_flow.MAX_FAILURES
    assert statuses.count(429) == n - auth_flow.MAX_FAILURES
