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
        return GitHubCodeDiffProvider(token=config.GITHUB_TOKEN)

    raise ValueError(
        f"Unknown CODE_DIFF_BACKEND: '{backend}'. "
        "Expected 'mock' or 'github'."
    )
