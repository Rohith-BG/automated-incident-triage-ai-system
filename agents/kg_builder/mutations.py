"""
Deterministic mutation builders and validator for the KG bootstrap loop.

Every mutation produced here is compatible with the stores'
`apply_mutations` contract:
  - add_node:       {"action", "node", "metadata"}
  - remove_node:    {"action", "node"}
  - add_dependency: {"action", "from", "to"}
  - remove_dependency: {"action", "from", "to"}
  - update_metadata: {"action", "node", "field", "value"}

Additionally, every mutation carries an "evidence" key recording the
provenance (repo, file, line, sha or deterministic source). The
validator drops any mutation without valid evidence so facts that
cannot be grounded are never applied (Rule 24).
"""

import re
from typing import Any

from agents.tracing import sanitize_text

_SUPPORTED_ACTIONS = {
    "add_node",
    "remove_node",
    "add_dependency",
    "remove_dependency",
    "add_contains",
    "update_metadata",
}


def build_add_node_mutation(
    node_id: str,
    metadata: dict[str, Any],
    evidence: str,
) -> dict[str, Any]:
    """Build an add_node mutation carrying provenance."""
    meta = dict(metadata)
    meta["evidence"] = sanitize_text(evidence)
    return {
        "action": "add_node",
        "node": node_id,
        "metadata": meta,
    }


def build_remove_node_mutation(
    node_id: str,
    evidence: str,
) -> dict[str, Any]:
    """Build a remove_node mutation carrying provenance."""
    return {
        "action": "remove_node",
        "node": node_id,
        "evidence": sanitize_text(evidence),
    }


def build_add_dependency_mutation(
    from_id: str,
    to_id: str,
    evidence: str,
) -> dict[str, Any]:
    """Build an add_dependency mutation carrying provenance."""
    return {
        "action": "add_dependency",
        "from": from_id,
        "to": to_id,
        "evidence": sanitize_text(evidence),
    }


def build_add_contains_mutation(
    parent_id: str,
    child_id: str,
    evidence: str,
) -> dict[str, Any]:
    """Build an add_contains mutation for parent→child hierarchy."""
    return {
        "action": "add_contains",
        "from": parent_id,
        "to": child_id,
        "evidence": sanitize_text(evidence),
    }


def build_remove_dependency_mutation(
    from_id: str,
    to_id: str,
    evidence: str,
) -> dict[str, Any]:
    """Build a remove_dependency mutation carrying provenance."""
    return {
        "action": "remove_dependency",
        "from": from_id,
        "to": to_id,
        "evidence": sanitize_text(evidence),
    }


def build_update_metadata_mutation(
    node_id: str,
    field: str,
    value: Any,
    evidence: str,
) -> dict[str, Any]:
    """Build an update_metadata mutation carrying provenance."""
    return {
        "action": "update_metadata",
        "node": node_id,
        "field": field,
        "value": value,
        "evidence": sanitize_text(evidence),
    }


def validate_mutations(
    mutations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (valid_mutations, dropped_reasons).

    Drops mutations that are malformed or lack evidence so that only
    grounded facts reach the staging graph.
    """
    valid: list[dict[str, Any]] = []
    dropped: list[str] = []

    for m in mutations:
        action = m.get("action")
        if action not in _SUPPORTED_ACTIONS:
            dropped.append(f"Unsupported action: {action}")
            continue

        evidence = m.get("evidence")
        if action == "add_node" and not evidence:
            metadata = m.get("metadata") or {}
            evidence = metadata.get("evidence")
        if not evidence or not str(evidence).strip():
            dropped.append(f"Missing evidence for {action} mutation")
            continue

        if action == "add_node":
            node_id = m.get("node")
            if not node_id or not isinstance(m.get("metadata"), dict):
                dropped.append(f"Invalid add_node for {node_id!r}")
                continue
        elif action == "remove_node":
            if not m.get("node"):
                dropped.append("Invalid remove_node: missing node")
                continue
        elif action in (
            "add_dependency", "remove_dependency", "add_contains",
        ):
            if not m.get("from") or not m.get("to"):
                dropped.append(f"Invalid {action}: missing from/to")
                continue
        elif action == "update_metadata":
            if not m.get("node") or "value" not in m:
                dropped.append(f"Invalid update_metadata for {m.get('node')!r}")
                continue

        valid.append(m)

    return valid, dropped


def deduplicate_mutations(
    mutations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove exact duplicate mutations, keeping the last occurrence."""
    seen: dict[str, dict[str, Any]] = {}
    for m in mutations:
        key_parts: list[Any] = [m.get("action")]
        if m.get("action") == "add_node":
            key_parts.append(m.get("node"))
        elif m.get("action") == "remove_node":
            key_parts.append(m.get("node"))
        elif m.get("action") in (
            "add_dependency", "remove_dependency", "add_contains",
        ):
            key_parts.extend([m.get("from"), m.get("to")])
        elif m.get("action") == "update_metadata":
            key_parts.extend([m.get("node"), m.get("field")])
        key = "|".join(str(p) for p in key_parts)
        seen[key] = m
    return list(seen.values())


def normalize_node_id(value: str) -> str:
    """Normalize an entity mention into a canonical graph node id.

    Lowercases, strips punctuation, and removes trailing 'service'
    suffixes so 'Cart Service', 'cart-service', and 'cart_service'
    all converge to the same canonical form for comparison.
    """
    normalized = value.strip().lower().replace("_", "-")
    normalized = re.sub(r"[- ]?services?$", "", normalized)
    return normalized.strip("-")


def derive_service_id(repo: str) -> str:
    """Derive a service id from a repo slug (last path segment)."""
    return repo.rstrip("/").split("/")[-1]


def evidence_summary(mutations: list[dict[str, Any]]) -> str:
    """Build a short human summary of a mutation set."""
    nodes = sum(1 for m in mutations if m.get("action") == "add_node")
    rm_nodes = sum(1 for m in mutations if m.get("action") == "remove_node")
    deps = sum(1 for m in mutations if m.get("action") == "add_dependency")
    contains = sum(1 for m in mutations if m.get("action") == "add_contains")
    rem = sum(1 for m in mutations if m.get("action") == "remove_dependency")
    ups = sum(1 for m in mutations if m.get("action") == "update_metadata")
    parts = []
    if nodes:
        parts.append(f"{nodes} node(s)")
    if rm_nodes:
        parts.append(f"{rm_nodes} removed node(s)")
    if deps:
        parts.append(f"{deps} dependency edge(s)")
    if contains:
        parts.append(f"{contains} contains edge(s)")
    if rem:
        parts.append(f"{rem} removed edge(s)")
    if ups:
        parts.append(f"{ups} metadata update(s)")
    return ", ".join(parts) if parts else "no changes"
