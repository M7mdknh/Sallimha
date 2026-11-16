"""Private evidence storage (ADR-0004). Objects are never web-served or public; every read goes through the
authorised media view. MEDIA_STORAGE=local keeps files under MEDIA_ROOT_PRIVATE (development); MEDIA_STORAGE=s3
uses a private S3-compatible bucket with server-side encryption (staging/production)."""

import hashlib
import uuid
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from core.errors import DomainError


class LocalStorage:
    def _path(self, key: str) -> Path:
        root = Path(settings.MEDIA_ROOT_PRIVATE).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise DomainError("not_found")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise DomainError("not_found")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


class S3Storage:
    """Private bucket: objects are written with server-side encryption and no ACL grants (bucket owner only)."""

    def __init__(self):
        import boto3

        self.bucket = settings.MEDIA_S3_BUCKET
        self.client = boto3.client("s3", region_name=settings.MEDIA_S3_REGION or None,
                                   endpoint_url=settings.MEDIA_S3_ENDPOINT_URL or None)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        extra = {"ServerSideEncryption": settings.MEDIA_S3_SSE} if settings.MEDIA_S3_SSE else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, **extra)

    def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise DomainError("not_found") from exc

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache(maxsize=1)
def storage():
    return S3Storage() if settings.MEDIA_STORAGE == "s3" else LocalStorage()


def reset_storage() -> None:
    storage.cache_clear()


def storage_check() -> str:
    """Write, read back and delete a probe object (deployment check)."""
    key = f"_probe/{uuid.uuid4().hex}"
    try:
        storage().put(key, b"probe", "application/octet-stream")
        ok = storage().get(key) == b"probe"
        storage().delete(key)
    except Exception as exc:  # noqa: BLE001 - reported, not raised: the caller decides what a failure means
        return f"failed: {type(exc).__name__}"
    return "ok" if ok else "failed: mismatch"

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAGIC = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/webp": (b"RIFF",)}


def validate_image(data: bytes, content_type: str) -> None:
    if content_type not in settings.MEDIA_ALLOWED_TYPES:
        raise DomainError("media_type_not_allowed")
    if len(data) > settings.MEDIA_MAX_BYTES:
        raise DomainError("media_too_large")
    if not any(data.startswith(m) for m in _MAGIC[content_type]):
        raise DomainError("media_content_mismatch")


def store_private(data: bytes, content_type: str, prefix: str) -> tuple[str, str]:
    validate_image(data, content_type)
    key = f"{prefix}/{uuid.uuid4().hex}.{_EXT[content_type]}"
    storage().put(key, data, content_type)
    return key, hashlib.sha256(data).hexdigest()


def read_private(key: str) -> bytes:
    return storage().get(key)


def delete_private(key: str) -> None:
    storage().delete(key)
