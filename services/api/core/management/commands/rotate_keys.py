"""Rotate FIELD_ENCRYPTION_KEY and HASH_KEY over stored data (ADR-0009, docs/runbooks/secret-rotation.md).

    rotate_keys            dry run: counts what would change, writes nothing
    rotate_keys --apply    re-encrypts every stored ciphertext with the current key and recomputes every hash whose
                           input is recoverable with the current HASH_KEY; safe to run again (idempotent)
    rotate_keys --verify   counts values the current keys alone cannot read or match ("pending N"); remove the
                           previous keys from the environment only when it reports pending 0

Action-token hashes cannot be recomputed (raw tokens are never stored): keep HASH_KEY_PREVIOUS until every token
issued before the rotation has expired or been used — in practice until the events open at rotation time close.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.crypto import decrypt_text, is_current_ciphertext, keyed_hash, rotate_ciphertext
from messaging.models import Conversation, MessageOutbox
from ops.models import CollectionCode, GuestBinding, Staff

BATCH = 500


class Command(BaseCommand):
    help = "Re-encrypt stored secrets and recompute keyed hashes after a key change (dry run by default)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--verify", action="store_true")

    def handle(self, *args, apply=False, verify=False, **options):
        counts = {"reencrypted": 0, "rehashed": 0, "pending": 0}
        for step in (self._bindings, self._codes, self._staff, self._outbox, self._conversations):
            step(counts, apply=apply, verify=verify)
        mode = "apply" if apply else "verify" if verify else "dry run"
        return (f"rotate_keys {mode}: re-encrypt {counts['reencrypted']} · re-hash {counts['rehashed']} · "
                f"pending {counts['pending']}")

    # Each helper: ciphertext not readable by the current key alone → re-encrypt; hash not made with the current
    # key → recompute. In verify mode both count as pending. Rows are locked and saved one batch at a time.
    def _cipher(self, counts, value, apply, verify):
        if not value or is_current_ciphertext(value):
            return value
        if verify:
            counts["pending"] += 1
            return value
        counts["reencrypted"] += 1
        return rotate_ciphertext(value) if apply else value

    def _hash(self, counts, stored, expected, apply, verify):
        if not stored or stored == expected:
            return stored
        if verify:
            counts["pending"] += 1
            return stored
        counts["rehashed"] += 1
        return expected if apply else stored

    def _batches(self, qs):
        ids = list(qs.values_list("pk", flat=True))
        for start in range(0, len(ids), BATCH):
            with transaction.atomic():
                yield qs.model.objects.select_for_update().filter(pk__in=ids[start:start + BATCH])

    def _bindings(self, counts, apply, verify):
        for batch in self._batches(GuestBinding.objects.exclude(phone_enc="")):
            for b in batch:
                old_hash = b.phone_hash
                phone_enc = self._cipher(counts, b.phone_enc, apply, verify)
                new_hash = self._hash(counts, b.phone_hash, keyed_hash(decrypt_text(b.phone_enc), "phone"),
                                      apply, verify)
                if apply and (phone_enc != b.phone_enc or new_hash != old_hash):
                    b.phone_enc, b.phone_hash = phone_enc, new_hash
                    b.save(update_fields=["phone_enc", "phone_hash"])
                    if new_hash != old_hash:  # the guest's conversation (24 h window, step) follows the new hash
                        Conversation.objects.filter(party_key=f"guest:{old_hash}").exclude(
                            party_key=f"guest:{new_hash}").update(party_key=f"guest:{new_hash}")

    def _codes(self, counts, apply, verify):
        for batch in self._batches(CollectionCode.objects.exclude(delivery_enc="")):
            for c in batch:
                delivery = self._cipher(counts, c.delivery_enc, apply, verify)
                verifier = self._hash(counts, c.verifier,
                                      keyed_hash(f"{c.ticket_id}:{decrypt_text(c.delivery_enc)}", "collection"),
                                      apply, verify)
                if apply and (delivery != c.delivery_enc or verifier != c.verifier):
                    c.delivery_enc, c.verifier = delivery, verifier
                    c.save(update_fields=["delivery_enc", "verifier"])

    def _staff(self, counts, apply, verify):
        for batch in self._batches(Staff.objects.all()):
            for s in batch:
                secret = self._cipher(counts, s.mfa_secret_enc, apply, verify)
                phone_hash = self._hash(counts, s.phone_hash, keyed_hash(s.phone_e164, "phone"), apply, verify)
                if apply and (secret != s.mfa_secret_enc or phone_hash != s.phone_hash):
                    s.mfa_secret_enc, s.phone_hash = secret, phone_hash
                    s.save(update_fields=["mfa_secret_enc", "phone_hash"])

    def _outbox(self, counts, apply, verify):
        for batch in self._batches(MessageOutbox.objects.exclude(to_phone_enc="")):
            for m in batch:
                old_hash = m.to_phone_hash
                phone_enc = self._cipher(counts, m.to_phone_enc, apply, verify)
                new_hash = self._hash(counts, m.to_phone_hash, keyed_hash(decrypt_text(m.to_phone_enc), "phone"),
                                      apply, verify)
                if apply and (phone_enc != m.to_phone_enc or new_hash != old_hash):
                    m.to_phone_enc, m.to_phone_hash = phone_enc, new_hash
                    m.save(update_fields=["to_phone_enc", "to_phone_hash"])

    def _conversations(self, counts, apply, verify):
        for batch in self._batches(Conversation.objects.filter(data__has_key="phone_enc")):
            for conv in batch:
                value = self._cipher(counts, conv.data.get("phone_enc", ""), apply, verify)
                if apply and value != conv.data.get("phone_enc"):
                    conv.data = {**conv.data, "phone_enc": value}
                    conv.save(update_fields=["data"])
