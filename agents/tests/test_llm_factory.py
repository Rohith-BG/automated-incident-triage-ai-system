"""Unit tests for provider-agnostic LLM factory and LangChainAdapter."""

import pytest
from agents.config import AgentSettings
from agents.llm.factory import create_llm_adapter, create_llm_model


def test_create_llm_model_google() -> None:
    """create_llm_model creates Google Gemini model in dev mode."""
    config = AgentSettings(ENVIRONMENT="dev", LLM_PROVIDER="google", GOOGLE_API_KEY="test-key")
    model = create_llm_model(config)
    assert model is not None


def test_create_llm_model_anthropic_with_fallbacks() -> None:
    """create_llm_model creates Anthropic chain with OpenAI and Opus fallbacks."""
    config = AgentSettings(
        ENVIRONMENT="prod",
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="test-anthropic-key",
        OPENAI_API_KEY="test-openai-key",
    )
    model = create_llm_model(config)
    assert model is not None


def test_create_llm_adapter_creation() -> None:
    """create_llm_adapter returns LLMAdapter instance."""
    config = AgentSettings(ENVIRONMENT="dev", LLM_PROVIDER="google", GOOGLE_API_KEY="test-key")
    adapter = create_llm_adapter(config)
    assert adapter is not None
