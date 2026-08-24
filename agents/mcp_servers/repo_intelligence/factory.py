"""
Factory for the repo_intelligence provider.
"""

from agents.config import AgentSettings
from .base import RepoIntelligenceProvider


def create_repo_intelligence_provider(
    config: AgentSettings,
) -> RepoIntelligenceProvider:
    """Create and return the configured RepoIntelligenceProvider."""
    backend = config.REPO_INTELLIGENCE_BACKEND

    if backend == "mock":
        from .mock import MockRepoIntelligenceProvider
        return MockRepoIntelligenceProvider(data_dir=config.DATA_DIR)

    if backend == "github":
        from .github_provider import GitHubRepoIntelligenceProvider
        return GitHubRepoIntelligenceProvider(token=config.GITHUB_TOKEN)

    raise ValueError(
        f"Unknown REPO_INTELLIGENCE_BACKEND: '{backend}'. "
        "Expected 'mock' or 'github'."
    )
