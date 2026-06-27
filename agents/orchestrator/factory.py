"""
Factory for LangGraph orchestrator.

Returns the entrypoint function for executing investigations.
Allows swappability in testing or future orchestrators.
"""

from typing import Any, Callable
from agents.config import AgentSettings


def create_orchestrator(
    config: AgentSettings,
) -> Callable[..., Any]:
    """Create and return the orchestrator entrypoint callable.

    Args:
        config: Agent settings.

    Returns:
        The run_investigation function.
    """
    from agents.orchestrator.graph import run_investigation

    return run_investigation
