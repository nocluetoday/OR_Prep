"""Provider registry — single entry point for `get_provider(kind)`.

Kinds are short strings stored in settings (LLM_*_PROVIDER) and the
`IngestRun.model_*` fields don't need to encode the provider; the model name
is enough alongside the per-step provider setting captured on the run.
"""

from __future__ import annotations

from .base import Provider, ProviderConfigurationError


_OPENAI_COMPAT_KINDS = frozenset({"openai", "lmstudio", "openrouter"})


def get_provider(kind: str) -> Provider:
    """Resolve a provider by short name. Raises ProviderConfigurationError for
    unknown kinds; per-provider import + key checks happen at first call time."""

    kind = (kind or "").strip().lower()
    if kind == "anthropic":
        from .anthropic import AnthropicProvider

        return AnthropicProvider()
    if kind in _OPENAI_COMPAT_KINDS:
        from .openai_compat import OpenAICompatibleProvider

        return OpenAICompatibleProvider(kind)
    raise ProviderConfigurationError(
        f"unknown LLM provider: {kind!r}. Expected one of: "
        f"anthropic, openai, lmstudio, openrouter."
    )


__all__ = ["get_provider"]
