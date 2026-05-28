"""Runtime LLM configuration resolution.

Each lookup follows the precedence:

  1. `LLMSettings` row in the DB (admin-editable, encrypted API keys).
  2. Django settings (env vars from `.env`).
  3. Hardcoded fallback (only for LM Studio's sentinel API key).

The providers in `apps.wiki.services.providers.*` and the ingest + briefing
services call into here instead of reading `django.conf.settings` directly,
so non-engineers can swap providers + models + keys from the admin without
touching the deploy.
"""

from __future__ import annotations

from django.conf import settings as django_settings


# Stage name -> (env var holding provider kind, env var holding model name).
_STAGE_ENV = {
    "briefing": ("LLM_BRIEFING_PROVIDER", "LLM_BRIEFING_MODEL"),
    "ingest_propose": ("LLM_INGEST_PROPOSE_PROVIDER", "LLM_INGEST_PROPOSE_MODEL"),
    "ingest_audit": ("LLM_INGEST_AUDIT_PROVIDER", "LLM_INGEST_AUDIT_MODEL"),
    "ingest_compose": ("LLM_INGEST_COMPOSE_PROVIDER", "LLM_INGEST_COMPOSE_MODEL"),
}

# Provider kind -> (env var for API key, env var for base URL or None,
#                   hardcoded API key fallback or None).
_PROVIDER_ENV = {
    "anthropic": ("ANTHROPIC_API_KEY", None, None),
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL", None),
    "lmstudio": ("LMSTUDIO_API_KEY", "LMSTUDIO_BASE_URL", "lm-studio"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", None),
}


def _db_settings():
    """Return the LLMSettings singleton, or None if not yet migrated / absent.

    Catches a broad set of exceptions because the migration that creates the
    table may not have been applied yet (e.g. on first `manage.py migrate`
    before this code is reached). In that case we silently fall back to env.
    """

    try:
        from apps.wiki.models import LLMSettings  # local import to avoid cycles

        return LLMSettings.objects.filter(pk=1).first()
    except Exception:
        return None


def get_stage_provider(stage: str) -> str:
    """Resolve the provider kind for a pipeline stage. DB > env."""

    if stage not in _STAGE_ENV:
        raise ValueError(f"unknown LLM stage: {stage!r}")
    row = _db_settings()
    if row is not None:
        value = (getattr(row, f"{stage}_provider", "") or "").strip()
        if value:
            return value
    return getattr(django_settings, _STAGE_ENV[stage][0])


def get_stage_model(stage: str) -> str:
    """Resolve the model name for a pipeline stage. DB > env."""

    if stage not in _STAGE_ENV:
        raise ValueError(f"unknown LLM stage: {stage!r}")
    row = _db_settings()
    if row is not None:
        value = (getattr(row, f"{stage}_model", "") or "").strip()
        if value:
            return value
    return getattr(django_settings, _STAGE_ENV[stage][1])


def get_api_key(provider: str) -> str:
    """Resolve the API key for a provider kind. DB > env > hardcoded fallback.

    Returns an empty string only when no source has a value, which the providers
    surface to the CLI as `ProviderConfigurationError`.
    """

    if provider not in _PROVIDER_ENV:
        return ""
    env_name, _, hardcoded = _PROVIDER_ENV[provider]
    row = _db_settings()
    if row is not None:
        key = row.get_api_key(provider)
        if key:
            return key
    env_value = getattr(django_settings, env_name, "")
    if env_value:
        return env_value
    return hardcoded or ""


def get_base_url(provider: str) -> str | None:
    """Resolve the base URL override for a provider kind, or None if no override
    is configured. Anthropic does not support custom base URLs in this build."""

    if provider not in _PROVIDER_ENV:
        return None
    _, env_name, _ = _PROVIDER_ENV[provider]
    if env_name is None:
        return None
    row = _db_settings()
    if row is not None:
        value = (getattr(row, f"{provider}_base_url", "") or "").strip()
        if value:
            return value
    return getattr(django_settings, env_name, "") or None


__all__ = [
    "get_stage_provider",
    "get_stage_model",
    "get_api_key",
    "get_base_url",
]
