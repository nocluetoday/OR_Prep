"""Thin wrapper around the Anthropic SDK.

Centralizes API-key handling and cost estimation so the ingest and briefing
services do not duplicate it. Calls fail loudly when ANTHROPIC_API_KEY is unset
rather than silently returning empty content.

Cost numbers are approximate. They exist so the CLIs can refuse to run an
expensive ingest unintentionally; for accounting we will pull authoritative
spend from the Anthropic dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


class AnthropicConfigurationError(RuntimeError):
    """Raised when the Anthropic SDK is required but not configured."""


@dataclass(frozen=True)
class ModelPricing:
    """Approximate per-million-token USD pricing for cost estimation."""

    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: float


# Rough public-list pricing as of late 2025; treat as upper-bound estimates.
# The briefing CLI prints "approx cost" with this; authoritative spend comes
# from the Anthropic dashboard, not this table.
PRICING = {
    "claude-opus-4-7": ModelPricing(15.0, 75.0, 1.5),
    "claude-sonnet-4-7": ModelPricing(3.0, 15.0, 0.3),
    "claude-sonnet-4-6": ModelPricing(3.0, 15.0, 0.3),
    "claude-haiku-4-5-20251001": ModelPricing(0.8, 4.0, 0.08),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    pricing = PRICING.get(model)
    if pricing is None:
        return 0.0
    uncached_input = max(0, input_tokens - cached_tokens)
    return (
        (uncached_input / 1_000_000) * pricing.input_per_mtok
        + (cached_tokens / 1_000_000) * pricing.cached_input_per_mtok
        + (output_tokens / 1_000_000) * pricing.output_per_mtok
    )


def get_client():
    """Return an Anthropic client or raise AnthropicConfigurationError.

    Importing the SDK lazily means migrations and tests do not need the
    package installed in trivial setups.
    """

    if not settings.ANTHROPIC_API_KEY:
        raise AnthropicConfigurationError(
            "ANTHROPIC_API_KEY is unset. Add it to your environment or "
            "backend/.env before running ingest or briefing commands."
        )
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise AnthropicConfigurationError(
            "anthropic package not installed. Run `pip install -r requirements.txt`."
        ) from e
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
