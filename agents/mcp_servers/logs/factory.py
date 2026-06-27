"""
Factory for the log provider.

Reads ``LOG_BACKEND`` from config and returns the matching
implementation.  Add new backends here — consumers never
change.
"""

from agents.config import AgentSettings
from agents.mcp_servers.logs.base import LogProvider


def create_log_provider(
    config: AgentSettings,
) -> LogProvider:
    """Create and return the configured LogProvider.

    Args:
        config: Agent settings with LOG_BACKEND selector.

    Returns:
        A LogProvider-compliant instance.

    Raises:
        ValueError: If LOG_BACKEND is unsupported.
    """
    if config.LOG_BACKEND == "mock":
        from agents.mcp_servers.logs.mock import (
            MockLogProvider,
        )

        data_path = config.DATA_DIR / "mock_logs.json"
        return MockLogProvider(data_path=data_path)

    if config.LOG_BACKEND == "loki":
        # Future: from agents.mcp_servers.logs.loki import
        #         LokiLogProvider
        # return LokiLogProvider(url=config.MCP_LOGS_URL)
        raise NotImplementedError(
            "Loki log provider not yet implemented. "
            "Set LOG_BACKEND=mock for MVP."
        )

    raise ValueError(
        f"Unknown LOG_BACKEND: '{config.LOG_BACKEND}'. "
        f"Expected 'mock' or 'loki'."
    )
