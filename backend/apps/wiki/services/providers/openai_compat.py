"""OpenAI-compatible provider: works for OpenAI, LM Studio, OpenRouter.

All three speak the OpenAI chat-completions wire format. The differences:

- **OpenAI**: api.openai.com, OPENAI_API_KEY, known per-model pricing.
- **LM Studio**: localhost:1234 by default (configurable), accepts any non-empty
  api key (we default to the string "lm-studio"), free (no per-token cost).
  Tool-calling reliability depends on the loaded model — some local models
  don't support tools at all.
- **OpenRouter**: openrouter.ai, OPENROUTER_API_KEY, hundreds of models routed.
  Pricing varies per model; the API returns actual spend in its usage block
  (we don't surface that yet; tracked as deferred work in the journal).

Pick by passing `kind="openai" | "lmstudio" | "openrouter"` to the constructor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .base import (
    CompletionResponse,
    Message,
    Provider,
    ProviderConfigurationError,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)


@dataclass(frozen=True)
class _Pricing:
    input_per_mtok: float
    output_per_mtok: float


# OpenAI public-list pricing (USD per million tokens). Update as needed; the
# CLI's cost estimate is best-effort, not accounting.
_OPENAI_PRICING: dict[str, _Pricing] = {
    "gpt-5": _Pricing(5.0, 20.0),
    "gpt-5-mini": _Pricing(0.5, 2.0),
    "gpt-4.1": _Pricing(2.5, 10.0),
    "gpt-4.1-mini": _Pricing(0.4, 1.6),
    "gpt-4o": _Pricing(2.5, 10.0),
    "gpt-4o-mini": _Pricing(0.15, 0.6),
}


@dataclass(frozen=True)
class _BackendConfig:
    kind: str
    default_base_url: str
    free: bool
    pricing: dict[str, _Pricing] = field(default_factory=dict)


_CONFIGS: dict[str, _BackendConfig] = {
    "openai": _BackendConfig(
        kind="openai",
        default_base_url="https://api.openai.com/v1",
        free=False,
        pricing=_OPENAI_PRICING,
    ),
    "lmstudio": _BackendConfig(
        kind="lmstudio",
        default_base_url="http://localhost:1234/v1",
        free=True,
    ),
    "openrouter": _BackendConfig(
        kind="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        free=False,
        # OpenRouter pricing varies per upstream model; the API reports actual
        # cost in `usage`. Local pricing table left empty; estimate returns 0.
    ),
}


class OpenAICompatibleProvider(Provider):
    def __init__(self, kind: str):
        if kind not in _CONFIGS:
            raise ProviderConfigurationError(
                f"unknown openai-compatible provider kind: {kind!r}. "
                f"Expected one of: {sorted(_CONFIGS)}."
            )
        self._cfg = _CONFIGS[kind]

    @property
    def name(self) -> str:
        return self._cfg.kind

    def _client(self):
        from apps.wiki.services.llm_config import get_api_key, get_base_url

        key = get_api_key(self._cfg.kind)
        if not key:
            raise ProviderConfigurationError(
                f"API key for provider={self._cfg.kind} is not configured. Set "
                f"it in Django admin (LLM settings) or as the matching env var "
                f"in backend/.env."
            )
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as e:
            raise ProviderConfigurationError(
                "openai package not installed. Run `pip install -r requirements.txt`."
            ) from e
        base_url = get_base_url(self._cfg.kind) or self._cfg.default_base_url
        return OpenAI(api_key=key, base_url=base_url)

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
        cache_system: bool = False,  # noqa: ARG002 — no explicit cache API for chat completions
    ) -> CompletionResponse:
        client = self._client()
        kwargs: dict = {
            "model": model,
            "messages": _to_openai_messages(system, messages),
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        if json_mode and not tools:
            # OpenAI's response_format conflicts with tool use on some backends.
            # Only enable when we're calling without tools (propose / audit / compose).
            kwargs["response_format"] = {"type": "json_object"}
        if self._cfg.kind == "openrouter":
            # OpenRouter only reports actual spend when usage.include is requested.
            kwargs["extra_body"] = {"usage": {"include": True}}

        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""

        tool_calls: list[ToolCall] = []
        for tc in (choice.message.tool_calls or []):
            try:
                inp = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except (json.JSONDecodeError, TypeError):
                inp = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=inp))

        usage_in = getattr(resp.usage, "prompt_tokens", 0) or 0
        usage_out = getattr(resp.usage, "completion_tokens", 0) or 0
        actual_cost = (
            _extract_openrouter_cost(resp.usage) if self._cfg.kind == "openrouter" else None
        )

        stop = "tool_use" if choice.finish_reason == "tool_calls" else (
            "max_tokens" if choice.finish_reason == "length" else "end"
        )
        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            usage=Usage(
                input_tokens=usage_in,
                output_tokens=usage_out,
                actual_cost_usd=actual_cost,
            ),
            stop_reason=stop,
            model=resp.model,
        )

    def estimate_cost_usd(self, model: str, usage: Usage) -> float:
        # Cache-hit accounting on OpenAI-compatible backends is provider-side
        # only — OpenAI applies automatic caching on long prompts and reports
        # the savings on its dashboard; OpenRouter folds it into usage.cost;
        # LM Studio is free. The local pricing fallback below does NOT subtract
        # cached_input_tokens (no cached-price column in the OpenAI pricing
        # struct), so its estimate is an upper bound. Use the provider's
        # dashboard for authoritative spend on OpenAI; trust the reported
        # usage.cost value for OpenRouter.
        if usage.actual_cost_usd is not None:
            return usage.actual_cost_usd
        if self._cfg.free:
            return 0.0
        pricing = self._cfg.pricing.get(model)
        if pricing is None:
            return 0.0
        return (
            (usage.input_tokens / 1_000_000) * pricing.input_per_mtok
            + (usage.output_tokens / 1_000_000) * pricing.output_per_mtok
        )


def _extract_openrouter_cost(usage_obj) -> float | None:
    """OpenRouter returns actual USD spend as `usage.cost` when `usage.include=true`
    is requested. The openai SDK preserves unknown fields differently across
    versions; check the obvious access paths and return the first hit."""

    if usage_obj is None:
        return None
    direct = getattr(usage_obj, "cost", None)
    if direct is not None:
        try:
            return float(direct)
        except (TypeError, ValueError):
            pass
    extra = getattr(usage_obj, "model_extra", None) or {}
    if "cost" in extra:
        try:
            return float(extra["cost"])
        except (TypeError, ValueError):
            pass
    dump = getattr(usage_obj, "model_dump", None)
    if callable(dump):
        try:
            d = dump()
        except Exception:
            d = None
        if isinstance(d, dict) and "cost" in d:
            try:
                return float(d["cost"])
            except (TypeError, ValueError):
                pass
    return None


def _to_openai_messages(system: str, messages: list[Message]) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        if m.role == "assistant":
            entry: dict = {"role": "assistant"}
            if m.text:
                entry["content"] = m.text
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.input),
                        },
                    }
                    for tc in m.tool_calls
                ]
            if "content" not in entry and "tool_calls" not in entry:
                entry["content"] = ""
            out.append(entry)
        else:
            if m.tool_results:
                for tr in m.tool_results:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": tr.tool_call_id,
                            "content": tr.content,
                        }
                    )
            else:
                out.append({"role": "user", "content": m.text})
    return out


__all__ = ["OpenAICompatibleProvider"]
