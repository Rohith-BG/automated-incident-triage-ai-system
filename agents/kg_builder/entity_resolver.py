"""
Deterministic entity resolution for the KG bootstrap feedback loop.

Resolves free-text entity mentions (service names, module paths)
against the graph inventory without an LLM. Matching is exact first,
then normalized (kebab-case, suffix-stripped), then fuzzy on token
overlap. Ambiguous mentions return a "needs clarification" result so
the agent asks the reviewer instead of guessing (ask-when-unsure).
"""

import re
from difflib import SequenceMatcher
from typing import Any, Optional

from agents.kg_builder.mutations import normalize_node_id


def _normalize_candidate(value: str) -> str:
    """Normalize an inventory id for comparison."""
    return normalize_node_id(value)


def _token_overlap(a: str, b: str) -> float:
    """Fuzzy similarity in [0, 1] based on token overlap."""
    a_tokens = set(re.findall(r"[a-z0-9]+", _normalize_candidate(a)))
    b_tokens = set(re.findall(r"[a-z0-9]+", _normalize_candidate(b)))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def _sequence_similarity(a: str, b: str) -> float:
    """Ratio similarity used as a tie-breaker."""
    return SequenceMatcher(
        None, _normalize_candidate(a), _normalize_candidate(b)
    ).ratio()


def resolve_entity(
    mention: str,
    inventory: list[str],
) -> dict[str, Any]:
    """Resolve a free-text mention against the graph inventory.

    Returns a dict::
        {"resolved": bool, "match": str|None, "ambiguous": list[str]|None}

    ``resolved`` is True only for a unique best match.
    """
    if not mention or not inventory:
        return {"resolved": False, "match": None, "ambiguous": None}

    mention_norm = _normalize_candidate(mention)

    # 1. Exact match
    for candidate in inventory:
        if candidate == mention or candidate == mention_norm:
            return {"resolved": True, "match": candidate, "ambiguous": None}

    # 2. Normalized match
    for candidate in inventory:
        if _normalize_candidate(candidate) == mention_norm:
            return {"resolved": True, "match": candidate, "ambiguous": None}

    # 3. Fuzzy: token overlap
    scored: list[tuple[float, str]] = []
    for candidate in inventory:
        overlap = _token_overlap(mention, candidate)
        if overlap >= 0.6:
            scored.append((overlap, candidate))

    if not scored:
        return {"resolved": False, "match": None, "ambiguous": None}

    # Tie-break on sequence similarity, then take the best.
    best_score = max(s for s, _ in scored)
    top = [c for s, c in scored if s == best_score]
    if len(top) == 1:
        return {"resolved": True, "match": top[0], "ambiguous": None}

    # Multiple candidates with equal score: prefer highest sequence similarity.
    ranked = sorted(
        top, key=lambda c: _sequence_similarity(mention, c), reverse=True
    )
    if len(ranked) > 1 and _sequence_similarity(mention, ranked[0]) > (
        _sequence_similarity(mention, ranked[1]) + 0.1
    ):
        return {"resolved": True, "match": ranked[0], "ambiguous": None}

    return {"resolved": False, "match": None, "ambiguous": sorted(top)}


def build_inventory(
    active_services: list[str],
    staged_nodes: list[dict[str, Any]],
    extra: Optional[list[str]] = None,
) -> list[str]:
    """Combine active + staged + extra ids into a deduplicated inventory."""
    inventory = list(active_services)
    inventory.extend(node.get("id", "") for node in staged_nodes)
    inventory.extend(extra or [])
    return sorted(set(i for i in inventory if i))
