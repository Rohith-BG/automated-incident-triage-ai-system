"""
Protocol interface for the LLM adapter.

Every LLM provider (Google Gemini, OpenAI, Anthropic, local)
must satisfy this contract. Consumers depend only on this
Protocol — never on a concrete SDK.
"""

from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel


# ── Structured types for LLM I/O ────────────────────────


class LLMMessage(BaseModel):
    """Single message in a conversation."""

    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None


class LLMToolDef(BaseModel):
    """Tool definition exposed to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    content: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    finish_reason: str = "stop"
    usage: dict[str, int] = {}  # prompt_tokens, completion_tokens, total_tokens


# ── Protocol ─────────────────────────────────────────────


@runtime_checkable
class LLMAdapter(Protocol):
    """Provider-agnostic LLM interface."""

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDef]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Send messages to LLM, optionally with tool defs.

        Args:
            messages: Conversation history.
            tools: Available tools the LLM may call.
            temperature: Override default temperature.
            max_tokens: Max tokens in response.

        Returns:
            Standardized LLMResponse.
        """
        ...

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        """Simple text-in → text-out. No tools.

        Convenience wrapper over generate() for cases
        where you just need a string response.
        """
        ...
