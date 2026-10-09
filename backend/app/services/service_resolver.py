"""
Service resolver — maps CloudWatch alarm metadata to a known service_id.

Extracts service identity from Trigger.Dimensions (namespace-aware),
AlarmName patterns, and AlarmDescription keyword scans.  Validates
resolved names against the knowledge graph's canonical service list.

This module lives in the backend because it is a transport/boundary
concern — the orchestrator always receives an already-resolved
service_id.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Dimension extraction strategies ────────────────────────


def _extract_from_ecs_dimensions(
    dimensions: list[dict[str, str]],
) -> Optional[str]:
    """Extract service name from AWS/ECS dimensions.

    Looks for the ``ServiceName`` dimension.
    """
    for dim in dimensions:
        name = dim.get("name") or dim.get("Name", "")
        if name == "ServiceName":
            return dim.get("value") or dim.get("Value")
    return None


def _extract_from_alb_dimensions(
    dimensions: list[dict[str, str]],
) -> Optional[str]:
    """Extract service name from AWS/ApplicationELB dimensions.

    Parses the ``TargetGroup`` dimension value which follows
    the convention ``tg/{service-name}/...`` or
    ``targetgroup/{service-name}/...``.
    """
    for dim in dimensions:
        name = dim.get("name") or dim.get("Name", "")
        if name == "TargetGroup":
            value = dim.get("value") or dim.get("Value") or ""
            # Convention: "tg/cart-service/abc123" or
            #             "targetgroup/cart-service/abc123"
            parts = value.split("/")
            if len(parts) >= 2:
                return parts[1]
    return None


def _extract_from_eks_dimensions(
    dimensions: list[dict[str, str]],
) -> Optional[str]:
    """Extract service name from ContainerInsights (EKS) dimensions.

    Looks for the ``Service`` or ``PodName`` dimension.
    """
    for dim in dimensions:
        name = dim.get("name") or dim.get("Name", "")
        if name == "Service":
            return dim.get("value") or dim.get("Value")
    return None


def _extract_from_apigateway_dimensions(
    dimensions: list[dict[str, str]],
) -> dict[str, Optional[str]]:
    """Extract service name and entry point from API Gateway dimensions.

    Returns dict with ``service_name`` (from ApiName) and
    ``entry_point`` (from Resource + Method) for monolith routing.
    """
    api_name: Optional[str] = None
    resource: Optional[str] = None
    method: Optional[str] = None

    for dim in dimensions:
        name = dim.get("name") or dim.get("Name", "")
        value = dim.get("value") or dim.get("Value") or ""
        if name == "ApiName":
            api_name = value
        elif name == "Resource":
            resource = value
        elif name == "Method":
            method = value

    entry_point = None
    if resource:
        entry_point = f"{method} {resource}" if method else resource

    return {"service_name": api_name, "entry_point": entry_point}


def _extract_from_custom_dimensions(
    dimensions: list[dict[str, str]],
) -> dict[str, Optional[str]]:
    """Extract service/module from custom namespace dimensions.

    Looks for ``Module``, ``ServiceName``, ``Service``, or
    ``FunctionName`` dimensions.
    """
    module: Optional[str] = None
    service: Optional[str] = None

    for dim in dimensions:
        name = dim.get("name") or dim.get("Name", "")
        value = dim.get("value") or dim.get("Value") or ""
        if name == "Module":
            module = value
        elif name in ("ServiceName", "Service", "FunctionName"):
            service = value

    return {"service_name": service, "entry_point": module}


# ── AlarmName pattern matching ─────────────────────────────


def _extract_service_from_alarm_name(
    alarm_name: str,
    known_services: list[str],
) -> Optional[str]:
    """Match a known service_id as a prefix/substring of AlarmName.

    Checks longest service names first so ``cart-service``
    matches before ``cart``.
    """
    lower = alarm_name.lower()
    # Sort by length descending so longer names match first
    for svc in sorted(known_services, key=len, reverse=True):
        if svc.lower() in lower:
            return svc
    return None


def _extract_service_from_description(
    description: str,
    known_services: list[str],
) -> Optional[str]:
    """Scan AlarmDescription for a known service name."""
    lower = description.lower()
    for svc in sorted(known_services, key=len, reverse=True):
        if svc.lower() in lower:
            return svc
    return None


# ── Public resolver ────────────────────────────────────────


class ServiceResolver:
    """Resolves CloudWatch alarm payloads to canonical service_ids.

    Delegates to namespace-specific dimension extractors, then
    falls back to AlarmName/AlarmDescription pattern matching.
    All resolved names are validated against the known service
    list.
    """

    def __init__(self, known_services: list[str]) -> None:
        """Initialise with the canonical service list.

        Args:
            known_services: Service IDs from the knowledge graph
                (``KnowledgeGraphStore.get_all_services()``).
        """
        self._known = known_services

    def resolve(
        self, alarm_data: dict[str, Any]
    ) -> dict[str, Optional[str]]:
        """Resolve service_id and optional entry_point from alarm data.

        Args:
            alarm_data: Parsed CloudWatch alarm JSON (the inner
                ``Message`` payload, not the SNS envelope).

        Returns:
            Dict with ``service_id`` (str | None) and
            ``entry_point`` (str | None).  ``service_id`` is
            None when resolution fails — caller should DLQ.
        """
        namespace = (
            alarm_data.get("Trigger", {}).get("Namespace", "")
        )
        dimensions: list[dict[str, str]] = (
            alarm_data.get("Trigger", {}).get("Dimensions", [])
        )
        alarm_name = alarm_data.get("AlarmName", "")
        description = alarm_data.get("AlarmDescription", "") or ""

        candidate: Optional[str] = None
        entry_point: Optional[str] = None

        # 1. Namespace-aware dimension extraction
        if namespace == "AWS/ECS":
            candidate = _extract_from_ecs_dimensions(dimensions)

        elif namespace == "AWS/ApplicationELB":
            candidate = _extract_from_alb_dimensions(dimensions)

        elif namespace in (
            "ContainerInsights",
            "AWS/ContainerInsights",
        ):
            candidate = _extract_from_eks_dimensions(dimensions)

        elif namespace == "AWS/ApiGateway":
            apigw = _extract_from_apigateway_dimensions(dimensions)
            candidate = apigw["service_name"]
            entry_point = apigw["entry_point"]

        elif namespace.startswith("Custom/"):
            custom = _extract_from_custom_dimensions(dimensions)
            candidate = custom["service_name"]
            entry_point = custom["entry_point"]

        # 2. Fallback: AlarmName pattern match
        if not candidate:
            candidate = _extract_service_from_alarm_name(
                alarm_name, self._known
            )

        # 3. Fallback: AlarmDescription scan
        if not candidate:
            candidate = _extract_service_from_description(
                description, self._known
            )

        # 4. Validate against known services
        if candidate and candidate in self._known:
            return {
                "service_id": candidate,
                "entry_point": entry_point,
            }

        # Candidate found but not in KG — try fuzzy match
        if candidate:
            lower_candidate = candidate.lower()
            for svc in self._known:
                if svc.lower() == lower_candidate:
                    return {
                        "service_id": svc,
                        "entry_point": entry_point,
                    }

        logger.warning(
            "Could not resolve service_id from CloudWatch alarm: "
            "AlarmName=%s, Namespace=%s, candidate=%s",
            alarm_name,
            namespace,
            candidate,
        )
        return {"service_id": None, "entry_point": entry_point}
