"""Sallimha settings.

Environment-driven. `SALLIMHA_ENV` is one of local | test | staging | production.
Local and test environments get clearly-labelled development keys when none are
supplied; staging and production refuse to start without real secrets.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent

ENVIRONMENT = os.environ.get("SALLIMHA_ENV", "local")
IS_DEV = ENVIRONMENT in {"local", "test"}


def _secret(name: str, dev_default: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    if IS_DEV:
        return dev_default
    raise ImproperlyConfigured(f"{name} must be set outside local/test environments")


SECRET_KEY = _secret("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-not-for-staging-or-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1" if IS_DEV else "0") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
_DEFAULT_ORIGINS = "http://localhost:5180,http://127.0.0.1:5180"
_ORIGINS = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", _DEFAULT_ORIGINS)
CSRF_TRUSTED_ORIGINS = [o for o in _ORIGINS.split(",") if o]

# Fernet key (urlsafe base64, 32 bytes) for field encryption; HMAC key for keyed hashes.
FIELD_ENCRYPTION_KEY = _secret("FIELD_ENCRYPTION_KEY", "ZGV2LW9ubHktZmllbGQta2V5LTMyLWJ5dGVzLWxvbmc=")
HASH_KEY = _secret("HASH_KEY", "dev-only-hash-key")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "rest_framework",
    "drf_spectacular",
    "core",
    "ops",
    "messaging",
    "console",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CorrelationIdMiddleware",
]

ROOT_URLCONF = "sallimha.urls"
WSGI_APPLICATION = "sallimha.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


def _database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL must be a PostgreSQL URL")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 0,
        "ATOMIC_REQUESTS": False,
    }


DATABASES = {
    "default": _database_from_url(
        os.environ.get(
            "DATABASE_URL",
            "postgres://sallimha:sallimha-local-only@127.0.0.1:55432/sallimha" if IS_DEV else "",
        )
        or "postgres://missing"
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DISPLAY_TIME_ZONE = "Asia/Riyadh"

STATIC_URL = "static/"
MEDIA_ROOT_PRIVATE = Path(os.environ.get("MEDIA_ROOT_PRIVATE", str(REPO_ROOT / "var" / "media")))
MEDIA_MAX_BYTES = 10 * 1024 * 1024
MEDIA_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not IS_DEV
CSRF_COOKIE_SECURE = not IS_DEV
SESSION_COOKIE_AGE = 12 * 60 * 60
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["console.auth.CsrfSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}
SPECTACULAR_SETTINGS = {"TITLE": "Sallimha console API", "VERSION": "0.1.0"}

# WhatsApp transport. "fake" is the local simulator; its results are SIMULATED.
WHATSAPP_TRANSPORT = os.environ.get("WHATSAPP_TRANSPORT", "fake" if IS_DEV else "cloud")
WHATSAPP_APP_SECRET = _secret("WHATSAPP_APP_SECRET", "dev-only-simulator-app-secret")
WHATSAPP_APP_SECRET_PREVIOUS = os.environ.get("WHATSAPP_APP_SECRET_PREVIOUS", "")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
SIMULATOR_ENABLED = os.environ.get("SIMULATOR_ENABLED", "1" if IS_DEV else "0") == "1"
if SIMULATOR_ENABLED and not IS_DEV:
    raise ImproperlyConfigured("SIMULATOR_ENABLED is only allowed in local/test environments")
if WHATSAPP_TRANSPORT == "fake" and not IS_DEV:
    raise ImproperlyConfigured("WHATSAPP_TRANSPORT=fake is only allowed in local/test environments")

WORKER_HEARTBEAT_STALE_SECONDS = 15
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"mask": {"()": "core.logging.MaskingFilter"}},
    "formatters": {
        "plain": {
            "()": "core.logging.MaskingFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "filters": ["mask"], "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
