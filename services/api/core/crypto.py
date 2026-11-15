"""Field encryption (Fernet), keyed hashes for lookups/verifiers, and random secrets."""

import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings


@lru_cache(maxsize=4)
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode())


def encrypt_text(plain: str) -> str:
    return _fernet(settings.FIELD_ENCRYPTION_KEY).encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str:
    return _fernet(settings.FIELD_ENCRYPTION_KEY).decrypt(token.encode()).decode()


def keyed_hash(value: str, purpose: str) -> str:
    message = f"{purpose}:{value}".encode()
    return hmac.new(settings.HASH_KEY.encode(), message, hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_token() -> str:
    return secrets.token_urlsafe(24)


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"
