"""
Protocol interface for the repo_intelligence MCP provider.

The KG bootstrap agent reads codebases exclusively through these
tools (rule: never parse code directly inside the agent). Every
result is typed and carries provenance so the agent can cite
exact files/lines when proposing graph mutations.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class RepoIntelligenceProvider(Protocol):
    """Structured, evidence-carrying codebase facts for KG building."""

    async def list_repositories(
        self, org: str
    ) -> list[dict[str, Any]]:
        """List repositories in a GitHub organization.

        Returns records: {name, repo, language, default_branch, description}.
        """
        ...

    async def get_repo_tree(
        self, repo: str
    ) -> list[dict[str, Any]]:
        """Return the repository file tree.

        Returns records: {path, type} where type is 'blob' or 'tree'.
        """
        ...

    async def read_file(
        self, repo: str, path: str
    ) -> str:
        """Read the decoded content of a file (empty string if missing)."""
        ...

    async def extract_manifests(
        self, repo: str, service_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Parse manifest/config files into structured dependency records.

        Returns: {
            "manifests": [{"path", "kind", "dependencies": [{"name", "version", "evidence"}]}],
            "files_scanned": [paths],
            "errors": ["unreadable file paths"],
        }
        """
        ...

    async def infer_dependencies(
        self,
        repo: str,
        service_id: str,
        architecture_type: str = "microservice",
    ) -> dict[str, Any]:
        """Derive service-level dependency edges from manifests and imports.

        Returns: {
            "service_id", "repo",
            "dependencies": [{"to", "kind", "evidence"}],
            "entry_points": [paths],
            "notes": [str],
        }
        """
        ...

    async def inspect_architecture(
        self, repo: str, architecture_type: str
    ) -> dict[str, Any]:
        """Describe how the repository maps to the graph.

        Returns: {
            "repo", "architecture_type", "service_id",
            "modules": [{"path", "kind", "evidence"}],
            "summary": str,
        }
        """
        ...

    async def inspect_deep_structure(
        self, repo: str, architecture_type: str
    ) -> dict[str, Any]:
        """Discover packages, files, classes, and functions for hierarchical KG.

        Returns: {
            "repo",
            "modules": [str],
            "packages": [{"module", "name", "path", "evidence"}],
            "files": [{
                "package_id", "file_stem", "file_path",
                "classes": [{"name", "line_number", "methods": [{"name", "is_async", "line_number", "calls"}]}],
                "functions": [{"name", "is_async", "line_number", "calls"}],
            }],
        }
        """
        ...

