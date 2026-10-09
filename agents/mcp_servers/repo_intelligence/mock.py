"""
Mock repo_intelligence provider for dev/test.

Builds realistic-but-fake repository facts from the bundled
data/services.json fixture so the KG bootstrap agent can run
end-to-end without GitHub credentials.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MockRepoIntelligenceProvider:
    """RepoIntelligenceProvider backed by the services.json fixture."""

    def __init__(self, data_dir: Path) -> None:
        """Load the fixture topology once."""
        self._data_path = data_dir / "services.json"
        with open(self._data_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._services = {svc["id"]: svc for svc in raw["services"]}
        self._external_apis: set[str] = set(raw.get("external_apis", []))
        self._databases: set[str] = set(raw.get("databases", []))

    async def list_repositories(
        self, org: str
    ) -> list[dict[str, Any]]:
        """Return one fake repo per service in the fixture."""
        return [
            {
                "name": svc["id"],
                "repo": f"{org}/{svc['id']}",
                "language": svc.get("language", "Python"),
                "default_branch": "main",
                "description": f"Mock repository for {svc['id']}",
            }
            for svc in self._services.values()
        ]

    async def get_repo_tree(
        self, repo: str
    ) -> list[dict[str, Any]]:
        """Return a fake tree containing a manifest for the service."""
        service_id = repo.split("/")[-1]
        svc = self._services.get(service_id, {})
        language = (svc.get("language") or "Python").lower()
        files = [
            {"path": "README.md", "type": "blob"},
        ]
        if language in ("python", "py"):
            files.append({"path": "requirements.txt", "type": "blob"})
            files.append({"path": "main.py", "type": "blob"})
        elif language in ("node.js", "javascript", "typescript"):
            files.append({"path": "package.json", "type": "blob"})
            files.append({"path": "index.js", "type": "blob"})
        elif language in ("go", "golang"):
            files.append({"path": "go.mod", "type": "blob"})
            files.append({"path": "main.go", "type": "blob"})
        else:
            files.append({"path": "package.json", "type": "blob"})
        files.append({"path": "docker-compose.yml", "type": "blob"})
        return files

    async def read_file(
        self, repo: str, path: str
    ) -> str:
        """Return deterministic mock file content for the fixture service."""
        service_id = repo.split("/")[-1]
        svc = self._services.get(service_id, {})
        filename = path.rsplit("/", 1)[-1]
        if filename == "docker-compose.yml":
            deps = [d for d in svc.get("dependencies", []) if d not in self._databases and d not in self._external_apis]
            lines = ["version: '3'", "services:", f"  {service_id}:", "    image: mock-img"]
            for d in deps:
                lines.append(f"    depends_on:\n      - {d}")
            return "\n".join(lines) + "\n"
        if filename == "package.json":
            deps = [d for d in svc.get("dependencies", [])]
            return json.dumps({"name": service_id, "version": "1.0.0", "dependencies": {d: "1.0.0" for d in deps}}, indent=2)
        if filename == "requirements.txt":
            return "\n".join(svc.get("dependencies", [])) + "\n"
        if filename == "go.mod":
            return "\n".join(f"require {d} v1.0.0" for d in svc.get("dependencies", [])) + "\n"
        if filename in ("main.py", "index.js", "main.go"):
            return "\n".join(f"import {d}" for d in svc.get("dependencies", [])) + "\n"
        return f"# {service_id} mock file"

    async def extract_manifests(
        self, repo: str, service_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Return manifest records derived from fixture dependencies."""
        sid = service_id or repo.split("/")[-1]
        svc = self._services.get(sid, {})
        deps = svc.get("dependencies", [])
        return {
            "manifests": [
                {
                    "path": "docker-compose.yml",
                    "kind": "compose",
                    "dependencies": [
                        {"name": d, "kind": "internal_service", "evidence": f"docker-compose.yml:services.{sid}.depends_on"}
                        for d in deps
                    ],
                },
                {
                    "path": "requirements.txt",
                    "kind": "python",
                    "dependencies": [
                        {"name": d, "version": "1.0.0", "kind": "library", "evidence": "requirements.txt:1"}
                        for d in deps
                    ],
                },
            ],
            "files_scanned": ["docker-compose.yml", "requirements.txt"],
            "errors": [],
        }

    async def infer_dependencies(
        self,
        repo: str,
        service_id: str,
        architecture_type: str = "microservice",
    ) -> dict[str, Any]:
        """Return the fixture dependency edges with evidence."""
        svc = self._services.get(service_id, {})
        dependencies = [
            {
                "to": dep,
                "kind": "internal_service" if dep not in self._external_apis and dep not in self._databases else "external",
                "evidence": f"docker-compose.yml:services.{service_id}.depends_on",
            }
            for dep in svc.get("dependencies", [])
        ]
        return {
            "service_id": service_id,
            "repo": repo,
            "dependencies": dependencies,
            "entry_points": ["docker-compose.yml"],
            "notes": ["Mock inference from services.json fixture."],
        }

    async def inspect_architecture(
        self, repo: str, architecture_type: str
    ) -> dict[str, Any]:
        """Derive the graph component id from the repo slug."""
        service_id = repo.split("/")[-1]
        modules = (
            [{"path": repo, "kind": "service", "evidence": f"{repo}:repo"}]
            if architecture_type == "microservice"
            else [{"path": "src", "kind": "module", "evidence": f"{repo}:tree/src"}]
        )
        return {
            "repo": repo,
            "architecture_type": architecture_type,
            "service_id": service_id,
            "modules": modules,
            "summary": f"Mock: repo {repo} mapped as {architecture_type} component '{service_id}'.",
        }

    async def inspect_deep_structure(
        self, repo: str, architecture_type: str
    ) -> dict[str, Any]:
        """Mock implementation of deep structure discovery.

        Returns a realistic multi-level hierarchy: modules, packages
        (with sub-dirs), files with classes/methods and standalone
        functions, including cross-package call references.
        """
        return {
            "repo": repo,
            "modules": ["backend", "agents"],
            "packages": [
                {
                    "module": "backend",
                    "name": "controllers",
                    "path": "backend/app/controllers",
                    "evidence": f"{repo}:tree/backend/app/controllers",
                },
                {
                    "module": "backend",
                    "name": "services",
                    "path": "backend/app/services",
                    "evidence": f"{repo}:tree/backend/app/services",
                },
                {
                    "module": "backend",
                    "name": "repositories",
                    "path": "backend/app/repositories",
                    "evidence": f"{repo}:tree/backend/app/repositories",
                },
                {
                    "module": "backend",
                    "name": "routes",
                    "path": "backend/app/routes",
                    "evidence": f"{repo}:tree/backend/app/routes",
                },
            ],
            "files": [
                {
                    "package_id": "backend.controllers",
                    "file_stem": "incidents",
                    "file_path": "backend/app/controllers/incidents.py",
                    "classes": [
                        {
                            "name": "IncidentController",
                            "line_number": 15,
                            "methods": [
                                {
                                    "name": "ingest_alert",
                                    "is_async": True,
                                    "line_number": 22,
                                    "calls": [
                                        "self._service.create_incident"
                                    ],
                                },
                            ],
                        }
                    ],
                    "functions": [],
                },
                {
                    "package_id": "backend.services",
                    "file_stem": "auth",
                    "file_path": "backend/app/services/auth.py",
                    "classes": [
                        {
                            "name": "AuthService",
                            "line_number": 25,
                            "methods": [
                                {
                                    "name": "register",
                                    "is_async": True,
                                    "line_number": 31,
                                    "calls": ["self._repo.create"],
                                },
                                {
                                    "name": "login",
                                    "is_async": True,
                                    "line_number": 50,
                                    "calls": [
                                        "self._repo.get_by_email"
                                    ],
                                },
                            ],
                        }
                    ],
                    "functions": [],
                },
                {
                    "package_id": "backend.services",
                    "file_stem": "incident",
                    "file_path": "backend/app/services/incident.py",
                    "classes": [
                        {
                            "name": "IncidentService",
                            "line_number": 18,
                            "methods": [
                                {
                                    "name": "create_incident",
                                    "is_async": True,
                                    "line_number": 25,
                                    "calls": [
                                        "self._repo.create",
                                        "self._repo.find_active_by_service",
                                    ],
                                },
                            ],
                        }
                    ],
                    "functions": [],
                },
                {
                    "package_id": "backend.repositories",
                    "file_stem": "incident",
                    "file_path": "backend/app/repositories/incident.py",
                    "classes": [
                        {
                            "name": "IncidentRepository",
                            "line_number": 12,
                            "methods": [
                                {
                                    "name": "create",
                                    "is_async": True,
                                    "line_number": 18,
                                    "calls": [],
                                },
                                {
                                    "name": "find_active_by_service",
                                    "is_async": True,
                                    "line_number": 30,
                                    "calls": [],
                                },
                            ],
                        }
                    ],
                    "functions": [],
                },
                {
                    "package_id": "backend.routes",
                    "file_stem": "incidents",
                    "file_path": "backend/app/routes/incidents.py",
                    "classes": [],
                    "functions": [
                        {
                            "name": "ingest_alert",
                            "is_async": True,
                            "line_number": 20,
                            "calls": [
                                "controller.ingest_alert"
                            ],
                        },
                    ],
                },
            ],
        }

    async def close(self) -> None:
        """No-op for the mock provider."""
        return None

