"""
repo_intelligence MCP server package.

Provides structured codebase facts (manifests, imports, dependency
edges) to the KG bootstrap agent. Dev uses the mock provider; prod
uses the GitHub-backed provider.
"""

from .base import RepoIntelligenceProvider
from .factory import create_repo_intelligence_provider

__all__ = [
    "RepoIntelligenceProvider",
    "create_repo_intelligence_provider",
]
