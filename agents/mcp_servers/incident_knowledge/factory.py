"""
Factory for the incident knowledge provider.
"""

from agents.config import AgentSettings
from .base import IncidentKnowledgeProvider


def create_incident_knowledge_provider(
    config: AgentSettings,
) -> IncidentKnowledgeProvider:
    """Create and return the configured IncidentKnowledgeProvider."""
    backend = config.INCIDENT_KNOWLEDGE_BACKEND

    if backend == "mock":
        from .mock import MockIncidentKnowledgeProvider
        return MockIncidentKnowledgeProvider()

    if backend == "db":
        from .db_provider import DBIncidentKnowledgeProvider
        from backend.app.core.database import AsyncSessionLocal
        return DBIncidentKnowledgeProvider(session_maker=AsyncSessionLocal)

    raise ValueError(
        f"Unknown INCIDENT_KNOWLEDGE_BACKEND: '{backend}'. "
        "Expected 'mock' or 'db'."
    )
