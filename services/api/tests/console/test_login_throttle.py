from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import AuditEvent


def _login(client, username, password):
    return client.post("/api/auth/login", {"username": username, "password": password}, format="json")


def test_login_rate_limited_after_5_failures(world):
    """AT-46 (rate limit part)."""
    user = get_user_model().objects.create_user(username="sup1", password="correct horse battery 9")
    world.supervisor.user = user
    world.supervisor.save()
    client = APIClient()
    for _ in range(5):
        assert _login(client, "sup1", "wrong").status_code == 400
    locked = _login(client, "sup1", "correct horse battery 9")
    assert locked.status_code == 429 and locked.json()["code"] == "too_many_attempts"
    assert AuditEvent.objects.filter(action="auth.locked").exists()


def test_unknown_user_and_wrong_password_look_identical(world):
    get_user_model().objects.create_user(username="sup2", password="correct horse battery 9")
    client = APIClient()
    a = _login(client, "nobody-here", "x")
    b = _login(client, "sup2", "x")
    assert (a.status_code, a.json()) == (b.status_code, b.json())
