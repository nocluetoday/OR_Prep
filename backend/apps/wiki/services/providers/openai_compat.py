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

from django.conf import settings

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
    api_key_setting: str
    base_url_setting: str | None  # which Django setting overrides the base URL
    api_key_fallback: str  # used if setting is unset/blank (e.g. LM Studio's "lm-studio")
    free: bool
    pricing: dict[str, _Pricing] = field(default_factory=dict)


_CONFIGS: dict[str, _BackendConfig] = {
    "openai": _BackendConfig(
        kind="openai",
        default_base_url="https://api.openai.com/v1",
        api_key_setting="OPENAI_API_KEY",
        base_url_setting="OPENAI_BASE_URL",
        api_key_fallback="",
        free=False,
        pricing=_OPENAI_PRICING,
    ),
    "lmstudio": _BackendConfig(
        kind="lmstudio",
        default_base_url="http://localhost:1234/v1",
        api_key_setting="LMSTUDIO_API_KEY",
        base_url_setting="LMSTUDIO_BASE_URL",
        api_key_fallback="lm-studio",
        free=True,
    ),
    "openrouter": _BackendConfig(
        kind="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        api_key_setting="OPENROUTER_API_KEY",
        base_url_setting="OPENROUTER_BASE_URL",
        api_key_fallback="",
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
        key = getattr(settings, self._cfg.api_key_setting, "") or self._cfg.api_key_fallback
        if not key:
            raise ProviderConfigurationError(
                f"{self._cfg.api_key_setting} is unset (provider={self._cfg.kind}). "
                f"Add it to backend/.env before running with this provider."
            )
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as e:
            raise ProviderConfigurationError(
                "openai package not installed. Run `pip install -r requirements.txt`."
            ) from e
        base_url = (
            getattr(settings, self._cfg.base_url_setting, None)
            if self._cfg.base_url_setting
            else None
        ) or self._cfg.default_base_url
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

        stop = "tool_use" if choice.finish_reason == "tool_calls" else (
            "max_tokens" if choice.finish_reason == "length" else "end"
        )
        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            usage=Usage(input_tokens=usage_in, output_tokens=usage_out),
            stop_reason=stop,
            model=resp.model,
        )

    def estimate_cost_usd(self, model: str, usage: Usage) -> float:
        if self._cfg.free:
            return 0.0
        pricing = self._cfg.pricing.get(model)
        if pricing is None:
            return 0.0
        return (
            (usage.input_tokens / 1_000_000) * pricing.input_per_mtok
            + (usage.output_tokens / 1_000_000) * pricing.output_per_mtok
        )


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
