"""
Factory for LLM adapter.

Reads LLM_PROVIDER from config and returns the matching
implementation. Add new providers here — consumers never
change.
"""

from agents.config import AgentSettings
from agents.llm.base import LLMAdapter


def create_llm_adapter(
    config: AgentSettings,
) -> LLMAdapter:
    """Create and return the configured LLM adapter.

    Args:
        config: Agent settings with LLM_PROVIDER selector.

    Returns:
        An LLMAdapter-compliant instance.

    Raises:
        ValueError: If LLM_PROVIDER is unsupported.
    """
    if config.LLM_PROVIDER == "google":
        from agents.llm.gemini_adapter import GeminiAdapter

        return GeminiAdapter(config)

    if config.LLM_PROVIDER == "openai":
        # Lazy import — not needed unless selected
        from agents.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(config)

    if config.LLM_PROVIDER == "anthropic":
        from agents.llm.anthropic_adapter import (
            AnthropicAdapter,
        )

        return AnthropicAdapter(config)

    raise ValueError(
        f"Unknown LLM_PROVIDER: '{config.LLM_PROVIDER}'. "
        f"Expected 'google', 'openai', or 'anthropic'."
    )
