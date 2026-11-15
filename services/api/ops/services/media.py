"""Private evidence storage. Files live outside any web-served path; access goes through an
authorized view only. Local filesystem in Phases 0–2; S3-compatible storage before staging."""

import hashlib
import uuid
from pathlib import Path

from django.conf import settings

from core.errors import DomainError

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
    path = Path(settings.MEDIA_ROOT_PRIVATE) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key, hashlib.sha256(data).hexdigest()


def read_private(key: str) -> bytes:
    root = Path(settings.MEDIA_ROOT_PRIVATE).resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise DomainError("not_found")
    return path.read_bytes()


def delete_private(key: str) -> None:
    root = Path(settings.MEDIA_ROOT_PRIVATE).resolve()
    path = (root / key).resolve()
    if root in path.parents and path.exists():
        path.unlink()
