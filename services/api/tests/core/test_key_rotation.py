"""Key rotation (ADR-0009): FIELD_ENCRYPTION_KEY (Fernet, many keys) and HASH_KEY (keyed lookups, one previous)."""

import os
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.utils import timezone

from core.crypto import decrypt_text, encrypt_text, keyed_hash
from messaging.models import Conversation, MessageOutbox
from ops.models import CollectionCode, GuestBinding, Staff
from ops.services import handover, tokens
from tests.factories import open_shift
from tests.ops.intake_helpers import park
from tests.wa import last, say

KEY_A, KEY_B = Fernet.generate_key().decode(), Fernet.generate_key().decode()


@pytest.fixture
def old_keys(settings):
    settings.FIELD_ENCRYPTION_KEY, settings.FIELD_ENCRYPTION_KEYS_PREVIOUS = KEY_A, []
    settings.HASH_KEY, settings.HASH_KEY_PREVIOUS = "hash-key-a", ""
    return settings


def _new_keys(settings, keep_previous=True):
    settings.FIELD_ENCRYPTION_KEY = KEY_B
    settings.FIELD_ENCRYPTION_KEYS_PREVIOUS = [KEY_A] if keep_previous else []
    settings.HASH_KEY, settings.HASH_KEY_PREVIOUS = "hash-key-b", "hash-key-a" if keep_previous else ""


def _world_with_secrets(world):
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    ticket = park(world.valets[0], world.event, phone="+966501112244")
    binding = ticket.bindings.get()
    code = handover.issue_code(ticket, binding, timezone.now())
    world.manager.mfa_secret_enc = encrypt_text("JBSWY3DPEHPK3PXP")
    world.manager.save(update_fields=["mfa_secret_enc"])
    return ticket, binding, code


def test_new_primary_key_still_reads_old_ciphertext_and_writes_with_the_new_key(old_keys):
    token = encrypt_text("+966501112244")
    _new_keys(old_keys)
    assert decrypt_text(token) == "+966501112244"
    fresh = encrypt_text("+966501112255")
    assert Fernet(KEY_B.encode()).decrypt(fresh.encode()) == b"+966501112255"  # new data uses the new key


def test_lookups_keep_working_during_the_hash_key_transition(old_keys, world):
    ticket, binding, _code = _world_with_secrets(world)
    _new_keys(old_keys)
    valet = world.valets[0]
    say(valet.phone_e164, "مساعدة")  # staff found by the phone hash made with the previous key
    assert last(valet).template == "valet.help"
    guest = binding.phone_hash
    assert guest == keyed_hash("+966501112244", "phone", key="hash-key-a")


def test_rotate_keys_rewrites_every_secret_and_previous_keys_can_then_be_removed(old_keys, world):
    ticket, binding, code = _world_with_secrets(world)
    out = MessageOutbox.objects.filter(to_phone_enc__gt="").first() or MessageOutbox.objects.create(
        kind="test.direct", template="guest.parked", to_phone_enc=encrypt_text("+966501112266"),
        to_phone_hash=keyed_hash("+966501112266", "phone"), params={}, dedupe_key="rotation-direct",
        next_attempt_at=timezone.now())
    conv = Conversation.objects.create(party_key=f"guest:{binding.phone_hash}", data={"phone_enc": encrypt_text("x")})
    _new_keys(old_keys)
    call_command("rotate_keys", "--apply")
    report = call_command("rotate_keys", "--verify")
    assert "pending 0" in report
    _new_keys(old_keys, keep_previous=False)  # old keys removed from the environment
    binding.refresh_from_db()
    assert decrypt_text(binding.phone_enc) == "+966501112244"
    assert binding.phone_hash == keyed_hash("+966501112244", "phone")
    assert Staff.objects.get(pk=world.valets[0].pk).phone_hash == keyed_hash(world.valets[0].phone_e164, "phone")
    code.refresh_from_db()
    plain = decrypt_text(code.delivery_enc)
    assert code.verifier == keyed_hash(f"{ticket.id}:{plain}", "collection")
    assert decrypt_text(Staff.objects.get(pk=world.manager.pk).mfa_secret_enc) == "JBSWY3DPEHPK3PXP"
    out.refresh_from_db()
    assert decrypt_text(out.to_phone_enc).startswith("+9665")
    assert Conversation.objects.filter(party_key=f"guest:{binding.phone_hash}").exists()
    conv.refresh_from_db()
    assert decrypt_text(conv.data["phone_enc"]) == "x"
    say(world.valets[0].phone_e164, "مساعدة")
    assert last(world.valets[0]).template == "valet.help"


def test_rotate_keys_dry_run_writes_nothing_and_a_second_apply_changes_nothing(old_keys, world):
    _ticket, binding, _code = _world_with_secrets(world)
    before = GuestBinding.objects.get(pk=binding.pk).phone_enc
    _new_keys(old_keys)
    report = call_command("rotate_keys")  # default is a dry run
    assert "dry run" in report and GuestBinding.objects.get(pk=binding.pk).phone_enc == before
    call_command("rotate_keys", "--apply")
    after = GuestBinding.objects.get(pk=binding.pk)
    call_command("rotate_keys", "--apply")
    again = GuestBinding.objects.get(pk=binding.pk)
    assert decrypt_text(again.phone_enc) == decrypt_text(after.phone_enc) and again.phone_hash == after.phone_hash


def test_action_tokens_resolve_with_the_previous_hash_key_until_it_is_removed(old_keys, world):
    """Raw action tokens are never stored, so their hashes cannot be recomputed: the previous hash key must stay
    until every token issued before the rotation has expired or been used (ADR-0009)."""
    for v in world.valets:
        open_shift(world.event, v, world.supervisor)
    ticket = park(world.valets[0], world.event)
    payload = tokens.issue("guest_request", ticket=ticket, binding=ticket.bindings.get())
    _new_keys(old_keys)
    call_command("rotate_keys", "--apply")
    assert tokens.resolve(payload) is not None
    _new_keys(old_keys, keep_previous=False)
    assert tokens.resolve(payload) is None


def test_secret_key_fallbacks_come_from_the_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SIMULATOR", "WHATSAPP", "SALLIMHA"))}
    env.update(SALLIMHA_ENV="test", DJANGO_SECRET_KEY_FALLBACKS="old-one,older-one")
    result = subprocess.run([sys.executable, "-c", "import sallimha.settings as s; print(s.SECRET_KEY_FALLBACKS)"],
                            env=env, capture_output=True, text=True, check=False)
    assert result.stdout.strip() == "['old-one', 'older-one']", result.stderr
    assert CollectionCode is not None
