"""Field encryption (Fernet), keyed hashes for lookups/verifiers, and random secrets.

Key rotation (ADR-0009):
- FIELD_ENCRYPTION_KEY encrypts; FIELD_ENCRYPTION_KEYS_PREVIOUS still decrypt (MultiFernet). `manage.py rotate_keys`
  re-encrypts every stored value with the current key; then the previous keys can be removed.
- HASH_KEY makes new hashes; lookups also accept HASH_KEY_PREVIOUS. `rotate_keys` recomputes every hash whose
  input is recoverable; action-token hashes are not (raw tokens are never stored), so the previous hash key stays
  until those tokens have expired or been used.
"""

import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


@lru_cache(maxsize=8)
def _multi(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(k.encode()) for k in keys])


def _fernet_keys() -> tuple[str, ...]:
    previous = tuple(k for k in getattr(settings, "FIELD_ENCRYPTION_KEYS_PREVIOUS", []) if k)
    return (settings.FIELD_ENCRYPTION_KEY, *previous)


def encrypt_text(plain: str) -> str:
    return _multi(_fernet_keys()).encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str:
    return _multi(_fernet_keys()).decrypt(token.encode()).decode()


def rotate_ciphertext(token: str) -> str:
    """Re-encrypts with the current key (preserving the token's timestamp)."""
    return _multi(_fernet_keys()).rotate(token.encode()).decode()


def is_current_ciphertext(token: str) -> bool:
    try:
        Fernet(settings.FIELD_ENCRYPTION_KEY.encode()).decrypt(token.encode())
        return True
    except Exception:  # noqa: BLE001 - InvalidToken or malformed: not readable with the current key alone
        return False


def keyed_hash(value: str, purpose: str, key: str | None = None) -> str:
    message = f"{purpose}:{value}".encode()
    return hmac.new((key or settings.HASH_KEY).encode(), message, hashlib.sha256).hexdigest()


def keyed_hash_candidates(value: str, purpose: str) -> list[str]:
    """Hashes a stored value may have during a HASH_KEY rotation: current key first, then the previous one."""
    hashes = [keyed_hash(value, purpose)]
    previous = getattr(settings, "HASH_KEY_PREVIOUS", "")
    if previous:
        hashes.append(keyed_hash(value, purpose, key=previous))
    return hashes


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_token() -> str:
    return secrets.token_urlsafe(24)


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"
