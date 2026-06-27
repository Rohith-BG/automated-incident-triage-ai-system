"""
Google Gemini LLM adapter.

Uses the new `google.genai` SDK (replaces deprecated
google.generativeai). Native async via client.aio.
Handles retries and timeout via config.
"""

import asyncio
import logging
from typing import Any, Optional

from google import genai
from google.genai import types

from agents.config import AgentSettings
from agents.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolDef,
)

logger = logging.getLogger(__name__)


class GeminiAdapter:
    """Google Gemini LLM adapter using google.genai SDK."""

    def __init__(self, config: AgentSettings) -> None:
        """Initialize the Gemini client.

        Args:
            config: Agent settings with GOOGLE_API_KEY,
                    LLM_MODEL, etc.
        """
        self._config = config
        self._model_name = config.LLM_MODEL
        self._temperature = config.LLM_TEMPERATURE
        self._timeout = config.LLM_TIMEOUT_SECONDS
        self._max_retries = config.LLM_MAX_RETRIES

        # Resolve API key
        api_key = config.GOOGLE_API_KEY or config.LLM_API_KEY
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY or LLM_API_KEY must be set "
                "for Gemini provider"
            )

        # Create client (sync + async via client.aio)
        self._client = genai.Client(api_key=api_key)

    # ── Protocol methods ─────────────────────────────────

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDef]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Send messages to Gemini and return response."""
        temp = (
            temperature
            if temperature is not None
            else self._temperature
        )

        # Build contents and config
        contents = self._build_contents(messages)
        system_instruction = self._extract_system(messages)

        config = types.GenerateContentConfig(
            temperature=temp,
            system_instruction=system_instruction,
        )
        if max_tokens is not None:
            config.max_output_tokens = max_tokens

        # Build tool declarations
        if tools:
            config.tools = self._build_tool_declarations(tools)

        # Call with retries
        response = await self._call_with_retry(
            contents=contents,
            config=config,
        )

        return self._parse_response(response)

    async def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        """Simple text prompt → text response."""
        response = await self.generate(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=temperature,
        )
        return response.content or ""

    # ── Internal helpers ─────────────────────────────────

    def _extract_system(
        self, messages: list[LLMMessage]
    ) -> Optional[str]:
        """Extract system instruction from messages."""
        system_parts = [
            m.content for m in messages if m.role == "system"
        ]
        return "\n\n".join(system_parts) if system_parts else None

    def _build_contents(
        self, messages: list[LLMMessage]
    ) -> list[types.Content]:
        """Convert LLMMessage list to Gemini Contents.

        Skips system messages (handled via system_instruction).
        Maps 'assistant' → 'model', everything else → 'user'.
        """
        contents: list[types.Content] = []

        for msg in messages:
            if msg.role == "system":
                continue

            role = "model" if msg.role == "assistant" else "user"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.content)],
                )
            )

        return contents

    def _build_tool_declarations(
        self, tools: list[LLMToolDef]
    ) -> list[types.Tool]:
        """Convert LLMToolDef list to Gemini Tool format."""
        declarations = []
        for tool in tools:
            declarations.append(
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters,
                )
            )
        return [types.Tool(function_declarations=declarations)]

    def _parse_response(self, response: Any) -> LLMResponse:
        """Convert Gemini response to LLMResponse."""
        candidate = response.candidates[0]
        parts = candidate.content.parts

        text_content = None
        tool_calls = None

        for part in parts:
            if part.text:
                text_content = (text_content or "") + part.text
            if (
                hasattr(part, "function_call")
                and part.function_call
            ):
                if tool_calls is None:
                    tool_calls = []
                fc = part.function_call
                tool_calls.append({
                    "name": fc.name,
                    "arguments": (
                        dict(fc.args) if fc.args else {}
                    ),
                })

        finish = "tool_calls" if tool_calls else "stop"

        # Token usage
        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "prompt_tokens": getattr(
                    um, "prompt_token_count", 0
                ),
                "completion_tokens": getattr(
                    um, "candidates_token_count", 0
                ),
                "total_tokens": getattr(
                    um, "total_token_count", 0
                ),
            }

        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            finish_reason=finish,
            usage=usage,
        )

    async def _call_with_retry(
        self,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
    ) -> Any:
        """Call Gemini async with retry + backoff."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 2):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model_name,
                        contents=contents,
                        config=config,
                    ),
                    timeout=self._timeout,
                )
                return response

            except asyncio.TimeoutError:
                last_error = TimeoutError(
                    f"Gemini timed out after "
                    f"{self._timeout}s (attempt {attempt})"
                )
                logger.warning(str(last_error))

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Gemini failed (attempt {attempt}): {e}"
                )

            if attempt <= self._max_retries:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                await asyncio.sleep(wait)

        raise last_error  # type: ignore[misc]
