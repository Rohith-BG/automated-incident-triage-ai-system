"""
Knowledge Graph bootstrap agent package.

Builds the initial knowledge graph from the codebase (via the
repo_intelligence MCP server) into a staging graph for human review,
and applies verified reviewer feedback through the revision loop.
"""

from .graph import apply_feedback_revision, run_kg_bootstrap
from .state import KgBootstrapState

__all__ = ["KgBootstrapState", "apply_feedback_revision", "run_kg_bootstrap"]
