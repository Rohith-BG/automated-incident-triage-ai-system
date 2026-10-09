"""
LangChain BaseChatModel adapter implementing LLMAdapter interface.

Provides provider-agnostic LLM calls powered by LangChain init_chat_model()
and .with_fallbacks() chains.
"""

import logging
from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agents.config import AgentSettings
from agents.llm.base import LLMMessage, LLMResponse, LLMToolDef

logger = logging.getLogger(__name__)

def _extract_text_content(content: Any) -> str:
    """Extract plain text from LangChain AIMessage content.

    LangChain content is either a plain string or a list of
    content-part dicts (Gemini style):
    ``[{'type': 'text', 'text': '...'}, ...]``.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(part["text"])
        return "\n".join(parts) if parts else str(content)
    return str(content)


class LangChainAdapter:
    """LLMAdapter implementation wrapping a LangChain BaseChatModel or Runnable fallback chain."""

    def __init__(self, model: BaseChatModel, config: AgentSettings) -> None:
        """Initialise with a LangChain model or fallback chain."""
        self._model = model
        self._config = config

    def _convert_messages(self, messages: list[LLMMessage]) -> list[BaseMessage]:
        """Convert LLMMessage dataclasses to LangChain BaseMessage objects."""
        lc_messages: list[BaseMessage] = []
        for m in messages:
            if m.role == "system":
                lc_messages.append(SystemMessage(content=m.content))
            elif m.role == "user":
                lc_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                lc_messages.append(AIMessage(content=m.content))
            elif m.role == "tool":
                lc_messages.append(
                    ToolMessage(
                        content=m.content,
                        tool_call_id=m.tool_call_id or "tool_call",
                    )
                )
        return lc_messages

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDef]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Send messages to LangChain chat model and format LLMResponse."""
        lc_messages = self._convert_messages(messages)
        model = self._model

        if tools:
            # Bind tools if provided
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            model = model.bind(tools=formatted_tools)  # type: ignore[assignment]

        try:
            res: AIMessage = await model.ainvoke(lc_messages)  # type: ignore[assignment]

            content = _extract_text_content(res.content)
            tool_calls = None
            if hasattr(res, "tool_calls") and res.tool_calls:
                tool_calls = [
                    {
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    }
                    for tc in res.tool_calls
                ]

            usage_metadata = getattr(res, "usage_metadata", {}) or {}
            usage = {
                "prompt_tokens": usage_metadata.get("input_tokens", 0),
                "completion_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            }

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason="stop",
                usage=usage,
            )
        except Exception as e:
            logger.error("LangChain adapter execution failed: %s", e)
            raise

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        """Simple text generation convenience wrapper."""
        msg = LLMMessage(role="user", content=prompt)
        resp = await self.generate([msg], temperature=temperature)
        return resp.content or ""
