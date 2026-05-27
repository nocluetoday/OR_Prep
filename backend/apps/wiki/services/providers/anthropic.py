"""Anthropic SDK provider.

Implements the provider ABC against `anthropic.Anthropic`. Translates the
provider-agnostic Message / ToolCall / ToolResult shape into Anthropic content
blocks (text / tool_use / tool_result) on the way in, and back out of the
response.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    cached_input_per_mtok: float


# Public-list pricing as of late 2025; treat as upper-bound estimates only.
_PRICING: dict[str, _Pricing] = {
    "claude-opus-4-7": _Pricing(15.0, 75.0, 1.5),
    "claude-sonnet-4-7": _Pricing(3.0, 15.0, 0.3),
    "claude-sonnet-4-6": _Pricing(3.0, 15.0, 0.3),
    "claude-haiku-4-5-20251001": _Pricing(0.8, 4.0, 0.08),
}


class AnthropicProvider(Provider):
    @property
    def name(self) -> str:
        return "anthropic"

    def _client(self):
        if not settings.ANTHROPIC_API_KEY:
            raise ProviderConfigurationError(
                "ANTHROPIC_API_KEY is unset. Add it to backend/.env (or "
                "docker/.env for compose) before running ingest or briefing "
                "commands with the anthropic provider."
            )
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as e:
            raise ProviderConfigurationError(
                "anthropic package not installed. Run `pip install -r requirements.txt`."
            ) from e
        return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,  # noqa: ARG002 — Anthropic enforces JSON via prompt
    ) -> CompletionResponse:
        client = self._client()
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": _to_anthropic_messages(messages),
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        msg = client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in msg.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=dict(block.input))
                )

        stop = _normalize_stop_reason(msg.stop_reason)
        return CompletionResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=Usage(
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
            ),
            stop_reason=stop,
            model=msg.model,
        )

    def estimate_cost_usd(self, model: str, usage: Usage) -> float:
        pricing = _PRICING.get(model)
        if pricing is None:
            return 0.0
        uncached_input = max(0, usage.input_tokens - usage.cached_input_tokens)
        return (
            (uncached_input / 1_000_000) * pricing.input_per_mtok
            + (usage.cached_input_tokens / 1_000_000) * pricing.cached_input_per_mtok
            + (usage.output_tokens / 1_000_000) * pricing.output_per_mtok
        )


def _to_anthropic_messages(messages: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "assistant":
            blocks: list[dict] = []
            if m.text:
                blocks.append({"type": "text", "text": m.text})
            for tc in m.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                    }
                )
            if not blocks:
                # Anthropic rejects empty assistant turns. Shouldn't happen in
                # our loops (we only append assistant when tool_calls is set or
                # text is non-empty), but guard so a buggy caller fails clearly.
                continue
            out.append({"role": "assistant", "content": blocks})
        else:  # user (plain text or tool results)
            if m.tool_results:
                blocks = []
                for tr in m.tool_results:
                    block: dict = {
                        "type": "tool_result",
                        "tool_use_id": tr.tool_call_id,
                        "content": tr.content,
                    }
                    if tr.is_error:
                        block["is_error"] = True
                    blocks.append(block)
                out.append({"role": "user", "content": blocks})
            else:
                out.append({"role": "user", "content": m.text})
    return out


def _normalize_stop_reason(raw: str | None) -> str:
    if raw == "tool_use":
        return "tool_use"
    if raw == "max_tokens":
        return "max_tokens"
    if raw in ("end_turn", "stop_sequence"):
        return "end"
    return raw or "end"


__all__ = ["AnthropicProvider"]
