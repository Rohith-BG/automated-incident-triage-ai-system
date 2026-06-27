"""
Factory for knowledge graph store.

Reads KG_BACKEND from config and returns the matching
implementation. Add new backends here — consumers never
change.
"""

from agents.config import AgentSettings
from agents.knowledge_graph.base import KnowledgeGraphStore
from agents.knowledge_graph.in_memory import InMemoryGraphStore


def create_kg_store(
    config: AgentSettings,
) -> KnowledgeGraphStore:
    """Create and return the configured KG implementation.

    Args:
        config: Agent settings with KG_BACKEND selector.

    Returns:
        A KnowledgeGraphStore-compliant instance.

    Raises:
        ValueError: If KG_BACKEND is unsupported.
    """
    if config.KG_BACKEND == "in_memory":
        return InMemoryGraphStore(config.SERVICES_JSON_PATH)

    if config.KG_BACKEND == "neo4j":
        # Lazy import — Neo4j driver not needed for MVP
        from agents.knowledge_graph.neo4j_store import (
            Neo4jGraphStore,
        )

        return Neo4jGraphStore(
            uri=config.NEO4J_URI,
            user=config.NEO4J_USER,
            password=config.NEO4J_PASSWORD,
        )

    raise ValueError(
        f"Unknown KG_BACKEND: '{config.KG_BACKEND}'. "
        f"Expected 'in_memory' or 'neo4j'."
    )
