from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import WorkerHeartbeat


@pytest.mark.django_db
def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_503_without_worker_heartbeat(client):
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["db"] == "ok"
    assert body["worker"] == "missing"


@pytest.mark.django_db
def test_readyz_503_with_stale_heartbeat(client):
    WorkerHeartbeat.objects.create(worker_id="w1", beat_at=timezone.now() - timedelta(seconds=30))
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["worker"] == "stale"


@pytest.mark.django_db
def test_readyz_ok_with_fresh_heartbeat_reports_whatsapp_separately(client):
    WorkerHeartbeat.objects.create(worker_id="w1", beat_at=timezone.now())
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["worker"] == "ok"
    assert body["whatsapp"] == "simulated"
