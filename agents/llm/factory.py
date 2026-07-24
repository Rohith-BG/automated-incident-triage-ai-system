"""
Factory for LLM models and adapters.

Uses LangChain's `init_chat_model` and `.with_fallbacks()` for provider-agnostic
model creation across Google Gemini, OpenAI, and Anthropic.
"""

import logging
from typing import Any
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from agents.config import AgentSettings
from agents.llm.base import LLMAdapter
from agents.llm.langchain_adapter import LangChainAdapter

logger = logging.getLogger(__name__)


def create_llm_model(config: AgentSettings) -> BaseChatModel:
    """Create a provider-agnostic LangChain chat model or fallback chain.

    Dev mode (LLM_PROVIDER=google):
      Returns `init_chat_model("google_genai:gemini-2.5-flash")`.

    Production mode (LLM_PROVIDER=anthropic):
      Primary: `anthropic:claude-sonnet-4-6`
      Fallback: `openai:gpt-4o`
      Escalation: `anthropic:claude-opus-4`
      Returns primary.with_fallbacks([fallback, escalation]).
    """
    provider = config.LLM_PROVIDER.lower()

    if provider == "google":
        api_key = config.GOOGLE_API_KEY or config.LLM_API_KEY
        return init_chat_model(
            model=f"google_genai:{config.LLM_MODEL}",
            api_key=api_key,
            temperature=config.LLM_TEMPERATURE,
        )

    if provider == "anthropic":
        anthropic_key = config.ANTHROPIC_API_KEY or config.LLM_API_KEY
        openai_key = config.OPENAI_API_KEY or config.LLM_API_KEY

        primary = init_chat_model(
            model=f"anthropic:{config.LLM_MODEL}",
            api_key=anthropic_key,
            temperature=config.LLM_TEMPERATURE,
        )

        fallbacks = []
        if openai_key:
            fb = init_chat_model(
                model=f"openai:{config.LLM_FALLBACK_MODEL}",
                api_key=openai_key,
                temperature=config.LLM_TEMPERATURE,
            )
            fallbacks.append(fb)

        if anthropic_key:
            esc = init_chat_model(
                model=f"anthropic:{config.LLM_ESCALATION_MODEL}",
                api_key=anthropic_key,
                temperature=config.LLM_TEMPERATURE,
            )
            fallbacks.append(esc)

        if fallbacks:
            logger.info("Configured Anthropic LLM chain with %d fallbacks", len(fallbacks))
            return primary.with_fallbacks(fallbacks)  # type: ignore[return-value]
        return primary

    if provider == "openai":
        api_key = config.OPENAI_API_KEY or config.LLM_API_KEY
        return init_chat_model(
            model=f"openai:{config.LLM_MODEL}",
            api_key=api_key,
            temperature=config.LLM_TEMPERATURE,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER: '{config.LLM_PROVIDER}'. "
        f"Expected 'google', 'openai', or 'anthropic'."
    )


def create_llm_adapter(config: AgentSettings) -> LLMAdapter:
    """Create and return an LLMAdapter wrapping the configured LangChain chat model."""
    if config.LLM_PROVIDER == "google" and (config.GOOGLE_API_KEY or config.LLM_API_KEY):
        try:
            model = create_llm_model(config)
            return LangChainAdapter(model=model, config=config)
        except Exception as e:
            logger.warning("Failed to initialize LangChain google_genai model, using direct GeminiAdapter: %s", e)
            from agents.llm.gemini_adapter import GeminiAdapter
            return GeminiAdapter(config)

    model = create_llm_model(config)
    return LangChainAdapter(model=model, config=config)
