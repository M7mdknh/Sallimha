"""`manage.py deploy_check`: the release gate run on a staging/production host before traffic (ADR-0004)."""

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from core.models import WorkerHeartbeat
from ops.services import media


def _staging_like(settings):
    settings.ENVIRONMENT, settings.IS_DEV, settings.DEBUG = "staging", False, False
    settings.SIMULATOR_ENABLED, settings.WHATSAPP_TRANSPORT = False, "cloud"
    settings.ALLOWED_HOSTS, settings.CSRF_TRUSTED_ORIGINS = ["staging.sallimha.test"], ["https://staging.sallimha.test"]
    settings.SECRET_KEY = "staging-placeholder-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJ"
    settings.HASH_KEY = "h" * 40
    settings.SECURE_SSL_REDIRECT, settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE = True, True, True
    settings.SECURE_HSTS_SECONDS = 3600
    settings.WHATSAPP_ACCESS_TOKEN = settings.WHATSAPP_PHONE_NUMBER_ID = settings.WHATSAPP_VERIFY_TOKEN = ""


def test_refuses_a_local_or_test_environment(db):
    with pytest.raises(CommandError) as err:
        call_command("deploy_check")
    assert "FAIL environment" in str(err.value)


def test_staging_passes_except_external_inputs_marked_blocked(settings, db, tmp_path, monkeypatch):
    _staging_like(settings)
    from moto import mock_aws

    for name, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                        "AWS_DEFAULT_REGION": "eu-central-1"}.items():
        monkeypatch.setenv(name, value)
    settings.MEDIA_STORAGE, settings.MEDIA_S3_BUCKET, settings.MEDIA_S3_REGION = "s3", "staging-media", "eu-central-1"
    settings.MEDIA_S3_ENDPOINT_URL = ""
    WorkerHeartbeat.objects.create(worker_id="w1", beat_at=timezone.now())
    with mock_aws():
        import boto3

        boto3.client("s3", region_name="eu-central-1").create_bucket(
            Bucket="staging-media", CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
        media.reset_storage()
        with pytest.raises(CommandError) as err:
            call_command("deploy_check")
        report = str(err.value)
        assert "BLOCKED whatsapp" in report and "FAIL" not in report
        assert "PASS media" in call_command("deploy_check", "--allow-blocked")
    media.reset_storage()


def test_local_media_and_stale_worker_fail_on_staging(settings, db):
    _staging_like(settings)
    settings.MEDIA_STORAGE = "local"
    media.reset_storage()
    with pytest.raises(CommandError) as err:
        call_command("deploy_check", "--allow-blocked")
    report = str(err.value)
    assert "FAIL media" in report and "FAIL worker" in report
    media.reset_storage()
