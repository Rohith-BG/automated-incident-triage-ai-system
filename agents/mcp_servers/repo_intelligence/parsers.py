"""
Deterministic manifest/import parsers for repo_intelligence.

These functions are pure and rule-based: they turn file contents
into structured dependency records with provenance (file path +
locator). No LLM is involved, so extracted facts cannot hallucinate.
Unrecognized formats are reported, never guessed.
"""

import re
from typing import Any


def _evidence(path: str, locator: str) -> str:
    """Build a provenance string for a parsed dependency record."""
    return f"{path}:{locator}"


def parse_package_json(
    content: str, path: str
) -> list[dict[str, Any]]:
    """Parse package.json dependencies (npm/yarn)."""
    records: list[dict[str, Any]] = []
    try:
        import json

        data = json.loads(content)
    except (ValueError, TypeError):
        return records

    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(section) or {}
        if not isinstance(deps, dict):
            continue
        for name, version in deps.items():
            records.append(
                {
                    "name": name,
                    "version": str(version),
                    "kind": "library",
                    "evidence": _evidence(path, f"{section}.{name}"),
                }
            )
    return records


def parse_go_mod(content: str, path: str) -> list[dict[str, Any]]:
    """Parse go.mod require directives."""
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line.startswith("require "):
            continue
        parts = line.split()
        if len(parts) >= 2:
            module = parts[1]
            version = parts[2] if len(parts) >= 3 else ""
            records.append(
                {
                    "name": module,
                    "version": version,
                    "kind": "library",
                    "evidence": _evidence(path, str(line_no)),
                }
            )
    return records


def parse_requirements_txt(content: str, path: str) -> list[dict[str, Any]]:
    """Parse pip requirements.txt lines."""
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip environment markers / extras for a clean package name
        name = re.split(r"[<>=!\[\];\s]", stripped, maxsplit=1)[0]
        if name:
            records.append(
                {
                    "name": name,
                    "version": "",
                    "kind": "library",
                    "evidence": _evidence(path, str(line_no)),
                }
            )
    return records


def parse_docker_compose(content: str, path: str) -> list[dict[str, Any]]:
    """Parse docker-compose.yml services and their depends_on edges."""
    records: list[dict[str, Any]] = []
    services: dict[str, dict[str, Any]] = {}
    try:
        import yaml

        data = yaml.safe_load(content) or {}
    except Exception:
        return records

    for svc_name, svc in (data.get("services") or {}).items():
        if not isinstance(svc, dict):
            continue
        services[svc_name] = {
            "name": svc_name,
            "image": svc.get("image", ""),
            "ports": svc.get("ports", []),
            "depends_on": svc.get("depends_on", []),
            "evidence": _evidence(path, f"services.{svc_name}"),
        }
        for dep in svc.get("depends_on") or []:
            dep_name = dep if isinstance(dep, str) else dep.get("service")
            records.append(
                {
                    "name": dep_name,
                    "version": "",
                    "kind": "internal_service",
                    "evidence": _evidence(path, f"services.{svc_name}.depends_on"),
                }
            )

    for svc_name, svc in services.items():
        records.append(
            {
                "name": svc_name,
                "version": "",
                "kind": "deployable",
                "image": svc.get("image", ""),
                "evidence": svc["evidence"],
            }
        )
    return records


def parse_pom_xml(content: str, path: str) -> list[dict[str, Any]]:
    """Parse Maven pom.xml dependencies (basic, dependency-only)."""
    records: list[dict[str, Any]] = []
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(content)
    except Exception:
        return records

    ns = ""
    m = re.match(r"\{.*\}", root.tag)
    if m:
        ns = m.group(0)

    def _text(elem: Any, tag: str) -> str:
        found = elem.find(f"{ns}{tag}")
        return found.text.strip() if found is not None and found.text else ""

    for dep in root.findall(f".//{ns}dependencies/{ns}dependency"):
        group = _text(dep, "groupId")
        artifact = _text(dep, "artifactId")
        if group and artifact:
            records.append(
                {
                    "name": f"{group}:{artifact}",
                    "version": _text(dep, "version"),
                    "kind": "library",
                    "evidence": _evidence(path, "dependencies.dependency"),
                }
            )
    return records


def parse_imports(content: str, path: str, language: str) -> list[dict[str, Any]]:
    """Extract import/require statements for internal dependency inference."""
    imports: list[dict[str, Any]] = []
    lang = (language or "").lower()

    if lang in ("javascript", "typescript", "js", "ts", "node"):
        patterns = [
            r"""from\s+['"]([^'"]+)['"]""",
            r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
            r"""import\s+['"]([^'"]+)['"]""",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                imports.append(
                    {
                        "module": match.group(1),
                        "evidence": _evidence(path, "import"),
                    }
                )
    elif lang in ("python", "py"):
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            m = re.match(r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", stripped)
            if m:
                module = m.group(1) or m.group(2)
                imports.append(
                    {
                        "module": module,
                        "evidence": _evidence(path, str(line_no)),
                    }
                )
    elif lang in ("go", "golang"):
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            m = re.match(r"^import\s+(?:\w+\s+)?[\"']([^\"']+)[\"']", stripped)
            if m:
                imports.append(
                    {
                        "module": m.group(1),
                        "evidence": _evidence(path, str(line_no)),
                    }
                )
    return imports


def parse_manifests_for_path(
    path: str, content: str
) -> list[dict[str, Any]]:
    """Dispatch file content to the matching manifest parser.

    Returns a flat list of dependency records with evidence.
    """
    filename = path.rsplit("/", 1)[-1].lower()
    if filename == "package.json":
        return parse_package_json(content, path)
    if filename == "go.mod":
        return parse_go_mod(content, path)
    if filename == "requirements.txt":
        return parse_requirements_txt(content, path)
    if filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        return parse_docker_compose(content, path)
    if filename == "pom.xml":
        return parse_pom_xml(content, path)
    return []


MANIFEST_NAMES = {
    "package.json": "npm",
    "go.mod": "go",
    "requirements.txt": "python",
    "docker-compose.yml": "compose",
    "docker-compose.yaml": "compose",
    "compose.yml": "compose",
    "compose.yaml": "compose",
    "pom.xml": "maven",
}


# ── Python AST extraction ────────────────────────────────


def parse_python_ast(
    content: str, file_path: str
) -> dict[str, Any]:
    """Extract file structure from Python source via AST.

    Returns a dict with classes (and their methods) plus
    standalone top-level functions::

        {
            "file_path": "backend/app/services/auth.py",
            "classes": [
                {
                    "name": "AuthService",
                    "line_number": 25,
                    "methods": [
                        {"name": "register", "is_async": True,
                         "line_number": 31, "calls": [...]},
                    ],
                },
            ],
            "functions": [
                {"name": "helper_func", "is_async": False,
                 "line_number": 10, "calls": [...]},
            ],
        }
    """
    import ast

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {
            "file_path": file_path,
            "classes": [],
            "functions": [],
        }

    classes: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []

    for node in ast.iter_child_nodes(tree):
        # Top-level class definitions.
        if isinstance(node, ast.ClassDef):
            methods: list[dict[str, Any]] = []
            for child in ast.iter_child_nodes(node):
                if not isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    continue
                if (
                    child.name.startswith("__")
                    and child.name.endswith("__")
                ):
                    continue
                calls = _collect_calls(child)
                methods.append({
                    "name": child.name,
                    "is_async": isinstance(
                        child, ast.AsyncFunctionDef
                    ),
                    "line_number": child.lineno,
                    "calls": calls,
                })
            if methods:
                classes.append({
                    "name": node.name,
                    "line_number": node.lineno,
                    "methods": methods,
                })

        # Top-level function definitions.
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if (
                node.name.startswith("__")
                and node.name.endswith("__")
            ):
                continue
            calls = _collect_calls(node)
            functions.append({
                "name": node.name,
                "is_async": isinstance(
                    node, ast.AsyncFunctionDef
                ),
                "line_number": node.lineno,
                "calls": calls,
            })

    return {
        "file_path": file_path,
        "classes": classes,
        "functions": functions,
    }


def _collect_calls(node: Any) -> list[str]:
    """Collect call target names from a function AST node."""
    import ast

    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _ast_call_name(child)
            if name:
                calls.append(name)
    return calls


def _ast_call_name(node: Any) -> str:
    """Extract a dotted call name from an ast.Call node."""
    import ast

    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        obj = func.value
        while isinstance(obj, ast.Attribute):
            parts.append(obj.attr)
            obj = obj.value
        if isinstance(obj, ast.Name):
            parts.append(obj.id)
        return ".".join(reversed(parts))
    return ""
