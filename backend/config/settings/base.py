"""Base settings shared by dev and prod."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "simple_history",
    "apps.users",
    "apps.modules",
    "apps.documents",
    "apps.wiki",
    "apps.cases",
]

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # simple-history captures the request.user for audit-log entries
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    ),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Where the faculty-authored module YAML lives. Defaults to ../modules from
# the backend directory for native dev; docker-compose overrides this to /modules
# via env var so the read-only bind mount is the source.
MODULES_DIR = env("MODULES_DIR", default=str((BASE_DIR.parent / "modules").resolve()))

# LLM provider configuration.
#
# Each pipeline stage (briefing, ingest propose, ingest adversarial audit, ingest
# compose) has its own provider + model setting so different stages can run on
# different backends — e.g. local LM Studio for ingest propose to keep cost down,
# Anthropic Opus for the audit pass for strictness. Provider kinds: anthropic,
# openai, lmstudio, openrouter. See apps.wiki.services.providers.
#
# Backwards compat: the older ANTHROPIC_BRIEFING_MODEL / ANTHROPIC_INGEST_MODEL /
# ANTHROPIC_AUDIT_MODEL env vars are still honored as defaults for the new
# LLM_*_MODEL settings, so existing .env files keep working.

ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default="https://api.openai.com/v1")

# LM Studio runs locally; accepts any non-empty API key (we default to a
# sentinel string). Override LMSTUDIO_BASE_URL when the server is on a
# different port / host.
LMSTUDIO_API_KEY = env("LMSTUDIO_API_KEY", default="lm-studio")
LMSTUDIO_BASE_URL = env("LMSTUDIO_BASE_URL", default="http://localhost:1234/v1")

OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")

_LEGACY_BRIEFING_MODEL = env("ANTHROPIC_BRIEFING_MODEL", default="claude-sonnet-4-6")
_LEGACY_INGEST_MODEL = env("ANTHROPIC_INGEST_MODEL", default="claude-sonnet-4-6")
_LEGACY_AUDIT_MODEL = env("ANTHROPIC_AUDIT_MODEL", default="claude-opus-4-7")

LLM_BRIEFING_PROVIDER = env("LLM_BRIEFING_PROVIDER", default="anthropic")
LLM_INGEST_PROPOSE_PROVIDER = env("LLM_INGEST_PROPOSE_PROVIDER", default="anthropic")
LLM_INGEST_AUDIT_PROVIDER = env("LLM_INGEST_AUDIT_PROVIDER", default="anthropic")
LLM_INGEST_COMPOSE_PROVIDER = env("LLM_INGEST_COMPOSE_PROVIDER", default="anthropic")

LLM_BRIEFING_MODEL = env("LLM_BRIEFING_MODEL", default=_LEGACY_BRIEFING_MODEL)
LLM_INGEST_PROPOSE_MODEL = env("LLM_INGEST_PROPOSE_MODEL", default=_LEGACY_INGEST_MODEL)
LLM_INGEST_AUDIT_MODEL = env("LLM_INGEST_AUDIT_MODEL", default=_LEGACY_AUDIT_MODEL)
LLM_INGEST_COMPOSE_MODEL = env("LLM_INGEST_COMPOSE_MODEL", default=_LEGACY_INGEST_MODEL)

# Per-resident daily briefing cap; the briefing command refuses to run further
# requests for a user once they hit this number on a given day.
BRIEFING_DAILY_CAP_PER_USER = env.int("BRIEFING_DAILY_CAP_PER_USER", default=10)

# Soft monthly ingest budget envelope (USD). The ingest command warns and refuses
# to run when month-to-date ingest spend would exceed this without --force.
INGEST_MONTHLY_BUDGET_USD = env.float("INGEST_MONTHLY_BUDGET_USD", default=30.0)

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}
