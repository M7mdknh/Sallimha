"""Private media on S3-compatible storage (ADR-0004): server-side encrypted objects, read only through the
authorised API. Exercised against moto's S3 emulator; a real bucket is BLOCKED until staging exists."""

import pytest

from core.errors import DomainError
from ops.services import media
from tests.console.conftest import login_as
from tests.factories import open_shift
from tests.ops.intake_helpers import JPEG, park

BUCKET = "sallimha-media-test"


@pytest.fixture
def s3(settings, monkeypatch):
    from moto import mock_aws

    for name, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                        "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": "eu-central-1"}.items():
        monkeypatch.setenv(name, value)
    settings.MEDIA_STORAGE, settings.MEDIA_S3_BUCKET, settings.MEDIA_S3_REGION = "s3", BUCKET, "eu-central-1"
    settings.MEDIA_S3_ENDPOINT_URL, settings.MEDIA_S3_SSE = "", "AES256"
    with mock_aws():
        import boto3

        client = boto3.client("s3", region_name="eu-central-1")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
        media.reset_storage()
        yield client
    media.reset_storage()


def test_objects_are_private_encrypted_and_round_trip(s3):
    key, digest = media.store_private(JPEG, "image/jpeg", "intake/1/2")
    head = s3.head_object(Bucket=BUCKET, Key=key)
    assert head["ServerSideEncryption"] == "AES256" and head["ContentType"] == "image/jpeg"
    acl = s3.get_object_acl(Bucket=BUCKET, Key=key)
    assert all("AllUsers" not in str(g["Grantee"]) for g in acl["Grants"])  # never public
    assert media.read_private(key) == JPEG and len(digest) == 64
    media.delete_private(key)
    with pytest.raises(DomainError):
        media.read_private(key)


def test_storage_round_trip_check(s3):
    assert media.storage_check() == "ok"


def test_console_streams_s3_media_only_within_scope(s3, world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    ticket = park(world.valets[0], world.event)
    item = ticket.media.first()
    assert s3.head_object(Bucket=BUCKET, Key=item.storage_key)["ContentLength"] == len(JPEG)
    resp = login_as(world.supervisor).get(f"/api/media/{item.id}")
    assert resp.status_code == 200 and b"".join(resp.streaming_content if resp.streaming else [resp.content]) == JPEG


def test_custom_s3_endpoints_use_path_style_addressing(settings):
    """Oracle Object Storage's S3-compatible endpoint (and most non-AWS providers) expect path-style addressing."""
    settings.MEDIA_STORAGE, settings.MEDIA_S3_BUCKET, settings.MEDIA_S3_REGION = "s3", BUCKET, "me-riyadh-1"
    settings.MEDIA_S3_ENDPOINT_URL = "https://example-namespace.compat.objectstorage.me-riyadh-1.oraclecloud.com"
    settings.MEDIA_S3_ADDRESSING_STYLE = "path"
    media.reset_storage()
    client = media.storage().client
    assert client.meta.config.s3["addressing_style"] == "path"
    assert client.meta.endpoint_url == settings.MEDIA_S3_ENDPOINT_URL
    media.reset_storage()
