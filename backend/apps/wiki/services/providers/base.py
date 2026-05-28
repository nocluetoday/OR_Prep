"""Provider-agnostic types and ABC for LLM calls.

The ingest and briefing services never import a vendor SDK directly. They
build a list of `Message`s, optionally a list of `ToolSpec`s, and call
`provider.complete(...)`. The Provider implementation handles SDK-specific
translation: Anthropic content blocks, OpenAI chat-completions tool calls,
LM Studio's OpenAI-compatible shape, OpenRouter's pass-through, etc.

Stop reasons are normalized to four values: "end" (generation complete),
"tool_use" (model called a tool and is waiting for results), "max_tokens"
(hit the budget), "error" (provider returned an error mid-response).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Provider call failed for a non-config reason (network, model, response)."""


class ProviderConfigurationError(ProviderError):
    """Provider can't run because env/config is missing — surfaced to the CLI user."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    # Optional authoritative cost (USD) reported by the provider in the response.
    # When set (non-None), Provider.estimate_cost_usd returns this verbatim
    # instead of computing from a local pricing table. OpenRouter populates this.
    actual_cost_usd: float | None = None


@dataclass
class ToolSpec:
    """Tool the model can call. Same `input_schema` (JSON Schema) for all providers."""

    name: str
    description: str
    input_schema: dict


@dataclass
class ToolCall:
    """One tool invocation by the model in a single completion."""

    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    """Server response to a ToolCall, returned to the model on the next turn."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """Provider-agnostic conversation turn.

    Assistant messages carry text + tool_calls (the model's response). Subsequent
    user messages either carry plain text or tool_results responding to prior calls.

    `cache=True` marks the message's content as cacheable. Providers that support
    explicit cache markers (Anthropic prompt caching) apply them; others ignore.
    Callers split static-from-variable into two Messages so only the static part
    gets cached — consecutive same-role messages get merged into one provider-
    native message with multiple content blocks, with cache markers preserved
    per block.
    """

    role: str  # "user" | "assistant"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    cache: bool = False


@dataclass
class CompletionResponse:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop_reason: str  # "end" | "tool_use" | "max_tokens" | "error"
    model: str


class Provider(ABC):
    """SDK-agnostic LLM provider interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short name used in logs and IngestRun.model_* fields (e.g. 'anthropic')."""

    @abstractmethod
    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
        cache_system: bool = False,
    ) -> CompletionResponse:
        """Single completion call.

        json_mode is a hint: providers that support forced-JSON output
        (OpenAI-compatible chat completions) apply it; Anthropic ignores it
        because the prompt already instructs JSON shape.

        cache_system marks the system prompt as cacheable. Providers with
        explicit cache markers (Anthropic) apply them; others ignore.
        """

    @abstractmethod
    def estimate_cost_usd(self, model: str, usage: Usage) -> float:
        """Best-effort USD cost estimate. Returns `usage.actual_cost_usd` if the
        provider reported it in the response (OpenRouter); else computes from a
        local pricing table; else returns 0.0 (model unknown, or free provider
        like LM Studio)."""
