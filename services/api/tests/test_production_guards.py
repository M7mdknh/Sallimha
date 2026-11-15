"""Simulator, demo seeding and the fake transport can never be enabled outside local/test."""

import os
import subprocess
import sys

import pytest
from django.core.management import CommandError, call_command


def _import_settings(**env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("SIMULATOR", "WHATSAPP", "SALLIMHA"))}
    base.update({"DJANGO_SECRET_KEY": "x" * 50, "FIELD_ENCRYPTION_KEY": "ZGV2LW9ubHktZmllbGQta2V5LTMyLWJ5dGVzLWxvbmc=",
                 "HASH_KEY": "h", "WHATSAPP_APP_SECRET": "s",
                 "DATABASE_URL": "postgres://u:p@127.0.0.1:5432/x"}, **env)
    return subprocess.run([sys.executable, "-c", "import sallimha.settings as s; print(s.SIMULATOR_ENABLED, "
                           "s.WHATSAPP_TRANSPORT)"], env=base, capture_output=True, text=True, cwd=os.getcwd(),
                          check=False)


def test_production_refuses_simulator_flag():
    result = _import_settings(SALLIMHA_ENV="production", SIMULATOR_ENABLED="1", WHATSAPP_TRANSPORT="cloud")
    assert result.returncode != 0 and "SIMULATOR_ENABLED" in result.stderr


def test_production_refuses_fake_transport():
    result = _import_settings(SALLIMHA_ENV="production", WHATSAPP_TRANSPORT="fake")
    assert result.returncode != 0 and "WHATSAPP_TRANSPORT" in result.stderr


def test_production_defaults_disable_simulator():
    result = _import_settings(SALLIMHA_ENV="staging")
    assert result.returncode == 0 and result.stdout.split() == ["False", "cloud"]


def test_seed_demo_refuses_outside_dev(settings, db):
    settings.IS_DEV = False
    with pytest.raises(CommandError):
        call_command("seed_demo")


def test_simulator_routes_not_registered_when_disabled():
    result = subprocess.run(
        [sys.executable, "-c",
         "import django, os; django.setup(); from django.urls import get_resolver; "
         "print(any('dev/sim' in str(p.pattern) for p in get_resolver().url_patterns[-1].url_patterns))"],
        env={**os.environ, "SIMULATOR_ENABLED": "0", "DJANGO_SETTINGS_MODULE": "sallimha.settings"},
        capture_output=True, text=True, check=False)
    assert result.stdout.strip() == "False", result.stderr
