"""
Factory for the observability provider.
"""

from agents.config import AgentSettings
from .base import ObservabilityProvider


def create_observability_provider(
    config: AgentSettings,
) -> ObservabilityProvider:
    """Create and return the configured ObservabilityProvider."""
    backend = config.OBSERVABILITY_BACKEND

    if backend == "mock":
        from .mock import MockObservabilityProvider
        return MockObservabilityProvider(data_dir=config.DATA_DIR)

    if backend == "cloudwatch":
        from .aws_provider import AWSObservabilityProvider
        return AWSObservabilityProvider(
            region_name=config.AWS_REGION,
            log_group_prefix=config.CLOUDWATCH_LOG_GROUP_PREFIX,
        )

    raise ValueError(
        f"Unknown OBSERVABILITY_BACKEND: '{backend}'. "
        "Expected 'mock' or 'cloudwatch'."
    )
