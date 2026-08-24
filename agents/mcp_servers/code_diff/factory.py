"""
Factory for the code diff provider.
"""

from agents.config import AgentSettings
from .base import CodeDiffProvider


def create_code_diff_provider(
    config: AgentSettings,
) -> CodeDiffProvider:
    """Create and return the configured CodeDiffProvider."""
    backend = config.CODE_DIFF_BACKEND

    if backend == "mock":
        from .mock import MockCodeDiffProvider
        data_path = config.DATA_DIR / "mock_code_diffs.json"
        return MockCodeDiffProvider(data_path=data_path)

    if backend == "github":
        from .github_provider import GitHubCodeDiffProvider
        from agents.knowledge_graph.factory import create_kg_store

        # Wire the KG store as the registry so service_id -> repo
        # resolution works at runtime (previously left None, causing
        # every code_diff call to raise ValueError).
        return GitHubCodeDiffProvider(
            token=config.GITHUB_TOKEN,
            registry_service=create_kg_store(config),
        )

    raise ValueError(
        f"Unknown CODE_DIFF_BACKEND: '{backend}'. "
        "Expected 'mock' or 'github'."
    )
