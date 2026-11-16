"""Staging configuration: Django's deployment check passes with no warnings (placeholder values, no secrets)."""

import os
import subprocess
import sys

from cryptography.fernet import Fernet

STAGING = {
    "SALLIMHA_ENV": "staging", "DJANGO_SECRET_KEY": "s" * 20 + "placeholder-not-a-real-secret-0123456789abc",
    "FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode(), "HASH_KEY": "placeholder-hash-key",
    "WHATSAPP_APP_SECRET": "placeholder", "DATABASE_URL": "postgres://u:p@127.0.0.1:5432/x",
    "DJANGO_ALLOWED_HOSTS": "staging.sallimha.test", "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.sallimha.test",
    "TRUSTED_PROXY_COUNT": "1", "DJANGO_SETTINGS_MODULE": "sallimha.settings",
}


def _run(*args, **env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("SIMULATOR", "WHATSAPP", "SALLIMHA", "DJANGO"))}
    return subprocess.run([sys.executable, "manage.py", *args], env={**base, **STAGING, **env}, capture_output=True,
                          text=True, check=False)


def test_check_deploy_is_clean_for_staging():
    result = _run("check", "--deploy", "--fail-level", "WARNING")
    assert result.returncode == 0, result.stdout + result.stderr


def test_staging_settings_force_https_and_trust_only_the_proxy():
    code = ("import django; django.setup(); from django.conf import settings as s; "
            "print(s.SECURE_SSL_REDIRECT, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_HSTS_SECONDS > 0, "
            "s.SECURE_PROXY_SSL_HEADER, s.DEBUG)")
    base = {k: v for k, v in os.environ.items() if not k.startswith(("SIMULATOR", "WHATSAPP", "SALLIMHA", "DJANGO"))}
    result = subprocess.run([sys.executable, "-c", code], env={**base, **STAGING}, capture_output=True, text=True,
                            check=False)
    assert result.stdout.split() == ["True", "True", "True", "True", "('HTTP_X_FORWARDED_PROTO',", "'https')",
                                     "False"], result.stderr
