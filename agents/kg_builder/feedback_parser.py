"""
Deterministic free-text feedback parser for the KG bootstrap loop.

Extracts an intent (add/remove dependency, add node, update metadata,
approve, reject) and entity mentions from conversational reviewer
feedback using regex rules only. No LLM is required, so intent cannot
be hallucinated. Unrecognized feedback yields intent "unknown" and the
agent asks for clarification.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

_ENTITY_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.\-]*(?:-service|_service|service|module|app|db|api)?"
)

_DEPENDENCY_PHRASE_PATTERN = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9_.\-]*)\s+"
    r"(?:depends\s+on|should\s+depend\s+on|depends\s+upon)\s+"
    r"(?:the\s+)?([A-Za-z0-9][A-Za-z0-9_.\-]*)",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "and", "or", "but",
    "it", "its", "this", "that", "with", "without", "from", "to", "for",
    "of", "on", "in", "at", "by", "we", "you", "please", "also", "should",
    "has", "have", "does", "do", "not", "no", "yes", "looks", "good",
    "right", "wrong", "incorrect", "correct", "approve", "reject", "ok",
}

_APPROVE_PATTERN = re.compile(
    r"\b(approve|approved|looks\s+good|accept|accepted|ship\s+it|"
    r"go\s+ahead|good\s+to\s+go|confirmed)\b",
    re.IGNORECASE,
)
_REJECT_PATTERN = re.compile(
    r"\b(reject|rejected|wrong|incorrect|not\s+right|discard|"
    r"no\b|don't\s+apply|do\s+not\s+apply)\b",
    re.IGNORECASE,
)
_ADD_DEP_PATTERN = re.compile(
    r"(depends\s+on|add\s+dependenc|missing\s+dependenc|"
    r"should\s+depend|depends\s+upon)",
    re.IGNORECASE,
)
_REMOVE_DEP_PATTERN = re.compile(
    r"(does\s+not\s+depend|should\s+not\s+depend|no\s+dependenc|"
    r"remove\s+(the\s+)?dependenc|drop\s+(the\s+)?dependenc|"
    r"wrong\s+dependenc)",
    re.IGNORECASE,
)
_ADD_NODE_PATTERN = re.compile(
    r"\b(add|include|register)\s+(a|an|the\s+)?(new\s+)?(service|module|node|component)\b",
    re.IGNORECASE,
)
_REMOVE_NODE_PATTERN = re.compile(
    r"\b(remove|delete|drop)\s+(a|an|the\s+)?"
    r"[\w\-\.]+?\s+(service|module|node|component)\b",
    re.IGNORECASE,
)
_UPDATE_METADATA_PATTERN = re.compile(
    r"\b(owner[_\s]?team|ownership|team|language|repo|description)\s+"
    r"(?:is\s+)?(?:should\s+be\s+)?(?:=)?\s*([^\s,.;]+)",
    re.IGNORECASE,
)


@dataclass
class FeedbackParse:
    """Structured parse of a free-text feedback message."""

    intent: str = "unknown"
    entities: list[str] = field(default_factory=list)
    metadata_updates: dict[str, Any] = field(default_factory=dict)
    subject: str = ""


def _extract_entities(text: str) -> list[str]:
    """Extract candidate entity mentions from text."""
    mentions: list[str] = []

    # Quoted strings are strong candidates.
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
    mentions.extend(quoted)

    # Dependency phrases give precise subject/target pairs.
    for match in _DEPENDENCY_PHRASE_PATTERN.finditer(text):
        mentions.extend(g for g in match.groups() if g)

    # Kebab/snake identifiers.
    for match in re.findall(r"\b[a-z0-9]+(?:[-_][a-z0-9]+)+\b", text, re.IGNORECASE):
        mentions.append(match)

    # Capitalized multi-word names (e.g. "Cart Service").
    for match in re.findall(
        r"\b[A-Z][a-z]+ (?:(?:[A-Z][a-z]+)|(?:[a-z0-9-]+))\b",
        text,
    ):
        mentions.append(match.strip())

    seen: set[str] = set()
    result: list[str] = []
    for mention in mentions:
        low = mention.lower().strip()
        if low in _STOPWORDS:
            continue
        if low in seen:
            continue
        seen.add(low)
        result.append(mention.strip())
    return result


def parse_feedback(feedback_text: str) -> FeedbackParse:
    """Parse free-text reviewer feedback into structured intent + entities."""
    text = feedback_text.strip()
    result = FeedbackParse()

    # Intent detection (check remove before add so "does not depend on"
    # does not match "depends on").
    if _REJECT_PATTERN.search(text):
        result.intent = "reject"
    elif _APPROVE_PATTERN.search(text):
        result.intent = "approve"
    elif _REMOVE_DEP_PATTERN.search(text):
        result.intent = "remove_dependency"
    elif _ADD_DEP_PATTERN.search(text):
        result.intent = "add_dependency"
    elif _REMOVE_NODE_PATTERN.search(text):
        result.intent = "remove_node"
    elif _ADD_NODE_PATTERN.search(text):
        result.intent = "add_node"
    elif _UPDATE_METADATA_PATTERN.search(text):
        result.intent = "update_metadata"

    result.entities = _extract_entities(text)

    for match in _UPDATE_METADATA_PATTERN.finditer(text):
        field_name = match.group(1).lower().replace(" ", "_")
        if field_name in ("ownership", "team"):
            field_name = "owner_team"
        result.metadata_updates[field_name] = match.group(2)

    return result


def guess_subject(
    parse: FeedbackParse,
    inventory: list[str],
) -> Optional[str]:
    """Pick the most likely subject service for the feedback.

    Uses entity resolution against the inventory; returns None when
    ambiguous so the agent asks for clarification.
    """
    from agents.kg_builder.entity_resolver import resolve_entity

    if parse.subject:
        return parse.subject

    resolved: list[str] = []
    for mention in parse.entities:
        outcome = resolve_entity(mention, inventory)
        if outcome["resolved"]:
            resolved.append(outcome["match"])

    if len(resolved) == 1:
        return resolved[0]
    if len(resolved) >= 2:
        return resolved[0]
    return None
