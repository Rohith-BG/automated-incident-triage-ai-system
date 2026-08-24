"""
Factory for knowledge graph store.

Reads KG_BACKEND from config and returns the matching
implementation. Add new backends here — consumers never
change.

The in-memory store is cached as a process-wide singleton so
staging state written by the KG bootstrap agent is visible to
later HTTP requests (matching the global_trace_recorder and
global_ws_manager singleton pattern).
"""

from agents.config import AgentSettings
from agents.knowledge_graph.base import KnowledgeGraphStore

_cached_in_memory_store = None


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
    global _cached_in_memory_store

    if config.KG_BACKEND == "in_memory":
        if _cached_in_memory_store is None:
            from agents.knowledge_graph.in_memory import (
                InMemoryGraphStore,
            )

            _cached_in_memory_store = InMemoryGraphStore(
                config.SERVICES_JSON_PATH,
                seed_from_fixtures=not config.KG_IN_MEMORY_START_EMPTY,
            )
        return _cached_in_memory_store

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
