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
        cache_system: bool = False,
    ) -> CompletionResponse:
        client = self._client()
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": _to_anthropic_messages(messages),
        }
        if system:
            if cache_system:
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
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

        # Pull cache-hit token counts out of the usage block. The Anthropic SDK
        # exposes cache_read_input_tokens (cache hits) and
        # cache_creation_input_tokens (writes); the read count is what gets the
        # cached-input price discount.
        cached_input = getattr(msg.usage, "cache_read_input_tokens", 0) or 0

        stop = _normalize_stop_reason(msg.stop_reason)
        return CompletionResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=Usage(
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
                cached_input_tokens=cached_input,
            ),
            stop_reason=stop,
            model=msg.model,
        )

    def estimate_cost_usd(self, model: str, usage: Usage) -> float:
        if usage.actual_cost_usd is not None:
            return usage.actual_cost_usd
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
    """Convert provider-agnostic Messages to Anthropic format.

    Consecutive same-role messages are merged into one provider message with
    multiple content blocks. This is how prompt caching breakpoints get
    expressed: caller splits a static-cacheable prefix from variable input
    into two Messages; converter emits one Anthropic message with two text
    blocks, with cache_control on the cacheable one only.
    """

    # First pass: build (role, blocks) tuples per Message.
    per_message: list[tuple[str, list[dict]]] = []
    for m in messages:
        if m.role == "assistant":
            blocks: list[dict] = []
            if m.text:
                block: dict = {"type": "text", "text": m.text}
                if m.cache:
                    block["cache_control"] = {"type": "ephemeral"}
                blocks.append(block)
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
            per_message.append(("assistant", blocks))
        else:  # user (plain text or tool results)
            if m.tool_results:
                tr_blocks: list[dict] = []
                for tr in m.tool_results:
                    block = {
                        "type": "tool_result",
                        "tool_use_id": tr.tool_call_id,
                        "content": tr.content,
                    }
                    if tr.is_error:
                        block["is_error"] = True
                    tr_blocks.append(block)
                per_message.append(("user", tr_blocks))
            else:
                block = {"type": "text", "text": m.text}
                if m.cache:
                    block["cache_control"] = {"type": "ephemeral"}
                per_message.append(("user", [block]))

    # Second pass: merge consecutive same-role messages so cache markers across
    # adjacent Messages become multi-block content on a single Anthropic message.
    merged: list[dict] = []
    for role, blocks in per_message:
        if merged and merged[-1]["role"] == role:
            merged[-1]["content"].extend(blocks)
        else:
            merged.append({"role": role, "content": list(blocks)})
    return merged


def _normalize_stop_reason(raw: str | None) -> str:
    if raw == "tool_use":
        return "tool_use"
    if raw == "max_tokens":
        return "max_tokens"
    if raw in ("end_turn", "stop_sequence"):
        return "end"
    return raw or "end"


__all__ = ["AnthropicProvider"]
