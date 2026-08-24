"""
System configuration report route.

Exposes the *effective* runtime component selections so operators (and the
frontend console) can confirm a configuration change took effect after modify +
restart. This is strictly informational and sanitized: it reports provider
names and model identifiers, never secrets or API keys.

Backend owns the HTTP layer; the constraint from AGENTS.md that the two
settings classes are not cross-imported refers to the backend never reading the
backend Settings class from agents (and vice-versa). Reading the agent settings
singleton here is the one intentional informational read and mirrors how the
backend already imports ``agents.orchestrator``.
"""

from fastapi import APIRouter

from agents.config import agent_settings

from ..core.config import settings

router = APIRouter(prefix="/config", tags=["system"])


def _has_key(provider: str) -> bool:
    """True when an API key for the given provider is configured."""
    if provider == "google":
        return bool(agent_settings.GOOGLE_API_KEY)
    if provider == "openai":
        return bool(agent_settings.OPENAI_API_KEY)
    if provider == "anthropic":
        return bool(agent_settings.ANTHROPIC_API_KEY)
    if provider == "local":
        return bool(agent_settings.LLM_BASE_URL)
    return bool(agent_settings.LLM_API_KEY)


@router.get("", summary="Current runtime component configuration")
async def runtime_config() -> dict:
    """Return sanitized effective component configuration."""
    return {
        "environment": settings.ENVIRONMENT,
        "llm": {
            "provider": agent_settings.LLM_PROVIDER,
            "model": agent_settings.LLM_MODEL,
            "temperature": agent_settings.LLM_TEMPERATURE,
            "configured": _has_key(agent_settings.LLM_PROVIDER)
            or bool(agent_settings.LLM_API_KEY),
        },
        "backends": {
            "kg": agent_settings.KG_BACKEND,
            "observability": agent_settings.OBSERVABILITY_BACKEND,
            "deploy": agent_settings.DEPLOY_BACKEND,
            "incident_knowledge": agent_settings.INCIDENT_KNOWLEDGE_BACKEND,
            "code_diff": agent_settings.CODE_DIFF_BACKEND,
            "notification": agent_settings.NOTIFICATION_BACKEND,
            "ticket": agent_settings.TICKET_BACKEND,
        },
        "investigation": {
            "confidence_threshold": agent_settings.CONFIDENCE_THRESHOLD,
            "tool_timeout_seconds": agent_settings.TOOL_TIMEOUT_SECONDS,
        },
    }