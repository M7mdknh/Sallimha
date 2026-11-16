# ADR-0009 — Rotation of the field-encryption and hashing keys

- Status: **Accepted 2026-11-16** (user mandate 2026-11-16 item 4; replaces "not supported yet" in the runbook).
- Requirement basis: docs/05 (secret rotation runbook, encrypted personal data), ADR-0001 (Fernet field
  encryption, keyed hashes for lookups).

## What the keys protect
| Key | Used for | Recomputable from stored data? |
|---|---|---|
| `FIELD_ENCRYPTION_KEY` (Fernet) | guest phone (`GuestBinding.phone_enc`), collection code for delivery (`CollectionCode.delivery_enc`), staff TOTP secret, outbox direct-recipient phone, conversation scratch phone | yes — every ciphertext can be re-encrypted (`MultiFernet.rotate`) |
| `HASH_KEY` (HMAC-SHA256) | phone lookup hashes (guests, staff, outbox), the guest conversation key, collection-code verifiers, action-token hashes, login-throttle keys | phones and collection codes yes (plaintext recoverable); **action tokens no** (raw tokens never stored); throttle counters are short-lived |

## Decision
- `FIELD_ENCRYPTION_KEY` encrypts; `FIELD_ENCRYPTION_KEYS_PREVIOUS` (comma-separated) still decrypt (MultiFernet).
- `HASH_KEY` creates hashes; every lookup also accepts `HASH_KEY_PREVIOUS` (guest sender, staff sender, action
  tokens, collection-code verification).
- `manage.py rotate_keys` (dry run by default; `--apply`; `--verify`) re-encrypts every ciphertext with the current
  key and recomputes every recoverable hash; it moves each guest conversation to the new phone hash; it is
  idempotent and batched. `--verify` reports `pending N`; previous keys are removed only at `pending 0`.
- Action tokens: keep `HASH_KEY_PREVIOUS` until every token issued before the rotation has expired or been used —
  in practice until the events open at rotation time have closed.
- `DJANGO_SECRET_KEY_FALLBACKS` (Django `SECRET_KEY_FALLBACKS`) lets `DJANGO_SECRET_KEY` rotate without signing
  everyone out.

## Recovery
- A failed or interrupted `--apply` is safe to rerun; nothing becomes unreadable while the previous keys remain.
- Backups taken before rotation hold data encrypted with the old key: **retain each old key in the secret store
  (not in the running environment) for as long as backups that need it are retained.** Restoring such a backup
  means putting that key back into `FIELD_ENCRYPTION_KEYS_PREVIOUS`/`HASH_KEY_PREVIOUS` and running
  `rotate_keys --apply`.
