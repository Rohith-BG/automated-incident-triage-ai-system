"""
Production GitHub-backed repo_intelligence provider.

Reads real repositories via the GitHub REST API (through the shared
GitHubClient) and returns deterministic, evidence-carrying facts:
manifests, imports, and derived dependency edges.
"""

import asyncio
import logging
from typing import Any, Optional

from agents.github_client import GitHubClient
from agents.mcp_servers.repo_intelligence.parsers import (
    MANIFEST_NAMES,
    parse_imports,
    parse_manifests_for_path,
)

logger = logging.getLogger(__name__)

# Source files scanned for import/require statements, capped to keep
# GitHub API usage bounded.
_IMPORT_SCAN_LIMIT = 120
_IMPORT_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx",
    ".py", ".go",
}


class GitHubRepoIntelligenceProvider:
    """RepoIntelligenceProvider backed by GitHub REST API."""

    def __init__(self, token: Optional[str] = None) -> None:
        """Initialise with the shared GitHub client."""
        self._client = GitHubClient(token=token)

    async def list_repositories(
        self, org: str
    ) -> list[dict[str, Any]]:
        """List repositories in a GitHub organization."""
        repos = await self._client.list_org_repos(org)
        logger.info("Discovered %d repositories in org %s", len(repos), org)
        return repos

    async def get_repo_tree(
        self, repo: str
    ) -> list[dict[str, Any]]:
        """Return the repository file tree."""
        return await self._client.get_repo_tree(repo)

    async def read_file(
        self, repo: str, path: str
    ) -> str:
        """Read the decoded content of a file."""
        return await self._client.get_file_content(repo, path)

    async def extract_manifests(
        self, repo: str, service_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Parse manifest/config files into structured dependency records."""
        tree = await self._client.get_repo_tree(repo)
        manifest_paths = [
            t["path"] for t in tree
            if t.get("type") == "blob"
            and t["path"].rsplit("/", 1)[-1].lower() in MANIFEST_NAMES
        ]

        manifests: list[dict[str, Any]] = []
        errors: list[str] = []
        for path in manifest_paths[:20]:
            content = await self._client.get_file_content(repo, path)
            if not content:
                errors.append(path)
                continue
            kind = MANIFEST_NAMES.get(path.rsplit("/", 1)[-1].lower(), "unknown")
            records = parse_manifests_for_path(path, content)
            manifests.append(
                {
                    "path": path,
                    "kind": kind,
                    "dependencies": records,
                }
            )

        logger.info(
            "Extracted %d manifests from %s", len(manifests), repo
        )
        return {
            "manifests": manifests,
            "files_scanned": [m["path"] for m in manifests],
            "errors": errors,
        }

    async def infer_dependencies(
        self,
        repo: str,
        service_id: str,
        architecture_type: str = "microservice",
    ) -> dict[str, Any]:
        """Derive service-level dependency edges from manifests and imports.

        For monoliths: relative imports are skipped (intra-package noise).
        Absolute cross-module imports (e.g. ``from agents.config import X``
        inside ``backend/``) are emitted as ``cross_module`` edges.
        """
        tree = await self._client.get_repo_tree(repo)
        manifest_paths = [
            t["path"] for t in tree
            if t.get("type") == "blob"
            and t["path"].rsplit("/", 1)[-1].lower() in MANIFEST_NAMES
        ]

        dependencies: list[dict[str, Any]] = []
        entry_points: list[str] = []
        notes: list[str] = []

        # Collect top-level directories as known modules for
        # cross-module detection in monoliths.
        top_level_dirs: set[str] = set()
        for t in tree:
            parts = t["path"].split("/")
            if len(parts) >= 2 and t.get("type") == "blob":
                top_level_dirs.add(parts[0])

        # 1. Manifest dependencies
        for path in manifest_paths[:20]:
            content = await self._client.get_file_content(repo, path)
            if not content:
                notes.append(f"Unreadable manifest: {path}")
                continue
            for record in parse_manifests_for_path(path, content):
                kind = record.get("kind", "library")
                if kind in ("internal_service", "deployable"):
                    dependencies.append(
                        {
                            "to": record["name"],
                            "kind": kind,
                            "evidence": record["evidence"],
                        }
                    )
                if kind == "deployable" and path.endswith(
                    ("docker-compose.yml", "compose.yml", "compose.yaml")
                ):
                    entry_points.append(path)

        # 2. Import scan over source files (bounded concurrency)
        candidate_paths: list[str] = []
        for t in tree:
            if len(candidate_paths) >= _IMPORT_SCAN_LIMIT:
                break
            path = t["path"]
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            dot_ext = f".{ext}"
            if t.get("type") == "blob" and dot_ext in _IMPORT_EXTENSIONS:
                candidate_paths.append(path)

        sem = asyncio.Semaphore(15)

        async def _scan_file(file_path: str) -> list[dict[str, Any]]:
            async with sem:
                content = await self._client.get_file_content(repo, file_path)
            if not content:
                return []
            ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
            dot_ext = f".{ext}"
            language = (
                "python" if dot_ext == ".py"
                else "javascript" if dot_ext in (
                    ".js", ".jsx", ".ts", ".tsx"
                )
                else "go"
            )
            source_module = file_path.split("/")[0] if "/" in file_path else ""
            file_deps: list[dict[str, Any]] = []
            imports = parse_imports(content, file_path, language)
            for imp in imports:
                module = imp["module"]
                if not module:
                    continue
                if module.startswith((".", "/")):
                    if architecture_type != "monolith":
                        file_deps.append(
                            {
                                "to": module,
                                "kind": "internal_module",
                                "evidence": imp["evidence"],
                            }
                        )
                    continue
                target_root = module.split(".")[0]
                if (
                    architecture_type == "monolith"
                    and target_root in top_level_dirs
                    and target_root != source_module
                ):
                    file_deps.append(
                        {
                            "from": source_module,
                            "to": target_root,
                            "kind": "cross_module",
                            "evidence": imp["evidence"],
                        }
                    )
                    continue
                if _looks_like_service(module):
                    file_deps.append(
                        {
                            "to": module,
                            "kind": "external_service",
                            "evidence": imp["evidence"],
                        }
                    )
            return file_deps

        scan_results = await asyncio.gather(
            *(_scan_file(p) for p in candidate_paths), return_exceptions=True
        )
        for res in scan_results:
            if isinstance(res, list):
                dependencies.extend(res)

        if not manifest_paths:
            notes.append(
                "No supported manifest files found; "
                "dependencies inferred from imports only."
            )

        logger.info(
            "Inferred %d dependency edges for %s",
            len(dependencies), service_id,
        )
        return {
            "service_id": service_id,
            "repo": repo,
            "dependencies": dependencies,
            "entry_points": entry_points,
            "notes": notes,
        }

    async def inspect_architecture(
        self, repo: str, architecture_type: str
    ) -> dict[str, Any]:
        """Describe how the repository maps to the graph."""
        meta = await self._client.get_repo_meta(repo)
        tree = await self._client.get_repo_tree(repo)
        service_id = meta["repo"].split("/")[-1]

        modules: list[dict[str, Any]] = []
        if architecture_type == "monolith":
            # Top-level directories are candidates for modules/components.
            # Skip non-code dirs, consistent with inspect_deep_structure.
            _ARCH_SKIP = {
                "data", "tests", "test", ".github", ".vscode",
                "__pycache__", ".git", "node_modules", ".agents",
                ".kiro", "alembic", ".venv", ".mypy_cache",
                ".pytest_cache", ".claude", ".impeccable",
            }
            seen: set[str] = set()
            for t in tree:
                parts = t["path"].split("/")
                if (
                    len(parts) >= 2
                    and parts[0] not in seen
                    and parts[0] not in _ARCH_SKIP
                    and not parts[0].startswith(".")
                    and t.get("type") == "blob"
                ):
                    seen.add(parts[0])
                    modules.append(
                        {
                            "path": parts[0],
                            "kind": "module",
                            "evidence": f"{repo}:tree/{parts[0]}",
                        }
                    )
        elif architecture_type == "microservice":
            modules.append(
                {
                    "path": repo,
                    "kind": "service",
                    "evidence": f"{repo}:repo",
                }
            )

        summary = (
            f"Repo {repo} mapped as {architecture_type} graph component "
            f"'{service_id}' with {len(modules)} modules."
        )
        return {
            "repo": repo,
            "architecture_type": architecture_type,
            "service_id": service_id,
            "modules": modules,
            "summary": summary,
        }

    async def inspect_deep_structure(
        self, repo: str, architecture_type: str
    ) -> dict[str, Any]:
        """Discover packages and functions for hierarchical KG.

        For monolith repos: discovers sub-packages (dirs with
        ``__init__.py``), then parses each ``.py`` file with AST to
        extract function/method definitions. Skips test dirs and the
        ``data`` module.

        Returns::

            {
                "repo": str,
                "modules": ["backend", "agents"],
                "packages": [
                    {"module": "backend", "name": "controllers",
                     "path": "backend/app/controllers"},
                ],
                "functions": [
                    {"package_id": "backend.controllers",
                     "name": "ingest_alert", "is_async": True,
                     "line_number": 42, "file_path": "...",
                     "calls": [...]},
                ],
            }
        """
        tree = await self._client.get_repo_tree(repo)

        # Skip dirs that aren't code modules.
        _SKIP_DIRS = {
            "data", "tests", "test", ".github", ".vscode",
            "__pycache__", ".git", "node_modules", ".agents",
            ".kiro", "alembic",
        }

        # Discover top-level modules (dirs with Python files).
        top_dirs: set[str] = set()
        for t in tree:
            parts = t["path"].split("/")
            if (
                len(parts) >= 2
                and t.get("type") == "blob"
                and parts[0] not in _SKIP_DIRS
                and parts[0] not in top_dirs
                and t["path"].endswith(".py")
            ):
                top_dirs.add(parts[0])

        # Discover packages: sub-dirs that have __init__.py.
        init_dirs: set[str] = set()
        for t in tree:
            if t.get("type") == "blob" and t["path"].endswith(
                "/__init__.py"
            ):
                init_dirs.add(
                    t["path"].rsplit("/__init__.py", 1)[0]
                )

        packages: list[dict[str, Any]] = []
        # Collect all package paths so we can exclude
        # sub-packages from parent scanning.
        all_pkg_paths: set[str] = set()
        for d in sorted(init_dirs):
            parts = d.split("/")
            top = parts[0]
            if top not in top_dirs or top in _SKIP_DIRS:
                continue
            pkg_name = parts[-1]
            if pkg_name == "__pycache__":
                continue
            # Skip the top-level dir itself — it's a module,
            # not a sub-package (avoids backend.backend).
            if len(parts) == 1:
                continue
            # Skip test and eval packages.
            if any(
                p in ("tests", "test", "eval") for p in parts
            ):
                continue
            all_pkg_paths.add(d)
            packages.append({
                "module": top,
                "name": pkg_name,
                "path": d,
                "evidence": f"{repo}:tree/{d}",
            })

        # Collect candidate files across packages (bounded concurrency).
        candidate_files: list[tuple[str, str, str]] = []
        for pkg in packages:
            pkg_path = pkg["path"]
            pkg_id = f"{pkg['module']}.{pkg['name']}"
            for t in tree:
                if len(candidate_files) >= _IMPORT_SCAN_LIMIT:
                    break
                if (
                    t.get("type") != "blob"
                    or not t["path"].endswith(".py")
                    or not t["path"].startswith(pkg_path + "/")
                ):
                    continue
                # Only files directly in this package.
                relative = t["path"][len(pkg_path) + 1:]
                if "/" in relative:
                    continue
                # Skip __init__.py and test files.
                if relative == "__init__.py" or relative.startswith("test_"):
                    continue
                candidate_files.append((pkg_id, relative, t["path"]))

        sem = asyncio.Semaphore(15)

        async def _fetch_and_parse(
            item: tuple[str, str, str]
        ) -> Optional[dict[str, Any]]:
            pkg_id, relative, file_path = item
            async with sem:
                content = await self._client.get_file_content(repo, file_path)
            if not content:
                return None
            from agents.mcp_servers.repo_intelligence.parsers import (
                parse_python_ast,
            )
            parsed = parse_python_ast(content, file_path)
            if parsed["classes"] or parsed["functions"]:
                file_stem = relative.rsplit(".", 1)[0]
                return {
                    "package_id": pkg_id,
                    "file_stem": file_stem,
                    "file_path": file_path,
                    "classes": parsed["classes"],
                    "functions": parsed["functions"],
                }
            return None

        parse_results = await asyncio.gather(
            *(_fetch_and_parse(c) for c in candidate_files),
            return_exceptions=True,
        )
        files: list[dict[str, Any]] = [
            r for r in parse_results
            if r and not isinstance(r, BaseException)
        ]

        total_fns = sum(
            len(f.get("functions", []))
            + sum(
                len(c.get("methods", []))
                for c in f.get("classes", [])
            )
            for f in files
        )
        logger.info(
            "Deep structure for %s: %d modules, %d packages, "
            "%d files, %d functions/methods",
            repo, len(top_dirs), len(packages),
            len(files), total_fns,
        )
        return {
            "repo": repo,
            "modules": sorted(top_dirs),
            "packages": packages,
            "files": files,
        }

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()


def _looks_like_service(module: str) -> bool:
    """Heuristic: does an import look like an external service reference?

    Excludes dotted Python module paths (e.g. ``backend.app.services.foo``)
    which are intra-repo imports, not external services.
    """
    if not module:
        return False
    # Dotted paths are Python internal imports, not service refs.
    if "." in module:
        return False
    lowered = module.lower()
    if any(token in lowered for token in ("-service", "_service")):
        return True
    if any(prefix in lowered for prefix in ("service/", "svc/", "internal/")):
        return True
    return False
