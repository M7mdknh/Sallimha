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


def test_ipv6_spraying_counter_is_bucketed_by_64(account):
    for i in range(1, auth_flow.IP_MAX_FAILURES + 1):
        _login(f"guess{i}", "wrong", ip=f"2001:db8:1:2::{i:x}")
    assert _login("sup1", PASSWORD, ip="2001:db8:1:2::ffff").status_code == 429
    assert _login("sup1", PASSWORD, ip="2001:db8:1:3::1").status_code == 200


def test_ipv4_mapped_ipv6_clients_are_not_grouped_together(account):
    for i in range(auth_flow.IP_MAX_FAILURES + 1):
        _login(f"guess{i}", "wrong", ip="::ffff:10.0.0.1")
    assert _login("sup1", PASSWORD, ip="::ffff:10.0.0.2").status_code == 200
    assert auth_flow.ip_bucket("::ffff:10.0.0.2") == "10.0.0.2"
    assert auth_flow.ip_bucket("64:ff9b::a00:2") == "10.0.0.2"


def test_known_network_keeps_normal_limit_while_account_under_attack(account):
    home = "198.51.100.77"
    assert _login("sup1", PASSWORD, ip=home).status_code == 200
    for i in range(auth_flow.ACCOUNT_ALERT_THRESHOLD + 2):
        _login("sup1", "wrong", ip=f"198.18.0.{i + 1}")
    for _ in range(auth_flow.MAX_FAILURES - 1):
        assert _login("sup1", "typo", ip=home).status_code == 400
    assert _login("sup1", PASSWORD, ip=home).status_code == 200


def test_account_under_distributed_attack_tightens_but_never_locks_owner(account):
    for i in range(auth_flow.ACCOUNT_ALERT_THRESHOLD + 1):
        _login("sup1", "wrong", ip=f"198.18.0.{i + 1}")
    assert AuditEvent.objects.filter(action="auth.account_under_attack").exists()
    attacker_ip = "198.18.1.200"
    for _ in range(auth_flow.UNDER_ATTACK_PAIR_MAX):
        assert _login("sup1", "wrong", ip=attacker_ip).status_code == 400
    assert _login("sup1", "wrong", ip=attacker_ip).status_code == 429
    assert _login("sup1", PASSWORD, ip="198.18.2.7").status_code == 200


def test_non_dev_requires_explicit_proxy_setting():
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SIMULATOR", "WHATSAPP", "SALLIMHA", "TRUSTED"))}
    env.update({"SALLIMHA_ENV": "production", "DJANGO_SECRET_KEY": "x" * 50, "HASH_KEY": "h",
                "FIELD_ENCRYPTION_KEY": "ZGV2LW9ubHktZmllbGQta2V5LTMyLWJ5dGVzLWxvbmc=", "WHATSAPP_APP_SECRET": "s",
                "DATABASE_URL": "postgres://u:p@127.0.0.1:5432/x"})
    missing = subprocess.run([sys.executable, "-c", "import sallimha.settings"], env=env, capture_output=True,
                             text=True, check=False)
    assert missing.returncode != 0 and "TRUSTED_PROXY_COUNT" in missing.stderr
    ok = subprocess.run([sys.executable, "-c", "import sallimha.settings"], env={**env, "TRUSTED_PROXY_COUNT": "1"},
                        capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr


def test_rotating_ipv6_within_64_shares_the_pair_limit(account):
    for i in range(1, auth_flow.MAX_FAILURES + 1):
        assert _login("sup1", "wrong", ip=f"2001:db8:9:9::{i:x}").status_code == 400
    assert _login("sup1", "wrong", ip="2001:db8:9:9::abcd").status_code == 429
