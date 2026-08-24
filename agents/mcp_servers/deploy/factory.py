"""
Factory for the deploy provider.
"""

from agents.config import AgentSettings
from .base import DeployProvider


def create_deploy_provider(
    config: AgentSettings,
) -> DeployProvider:
    """Create and return the configured DeployProvider."""
    backend = config.DEPLOY_BACKEND

    if backend == "mock":
        from .mock import MockDeployProvider
        data_path = config.DATA_DIR / "mock_deploys.json"
        return MockDeployProvider(data_path=data_path)

    if backend == "github":
        from .github_provider import GitHubDeployProvider
        from agents.knowledge_graph.factory import create_kg_store

        return GitHubDeployProvider(
            token=config.GITHUB_TOKEN,
            kg_store=create_kg_store(config),
        )

    raise ValueError(
        f"Unknown DEPLOY_BACKEND: '{backend}'. "
        "Expected 'mock' or 'github'."
    )
