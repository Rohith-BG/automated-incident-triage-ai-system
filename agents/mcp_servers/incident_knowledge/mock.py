"""
Mock incident knowledge provider for testing without a database.
"""

from typing import Any, Optional

MOCK_RUNBOOKS = [
    {
        "id": "rb-1",
        "title": "Stripe timeout during payment transaction",
        "applies_to_services": ["payment-service"],
        "applies_to_error_types": ["stripe_api_timeout"],
        "symptoms": "High rate of Stripe billing failures, HTTP 504 gateway timeouts.",
        "root_cause_pattern": "Stripe API latency spike causing connection pool exhaustion.",
        "immediate_steps": "1. Check status.stripe.com.\n2. Restart payment-service containers to clear connection pool.",
        "permanent_fix": "Add request timeouts and circuit-breaker wrapping to all Stripe API client requests.",
        "escalate_if": "Restarting containers does not restore payment processing within 5 minutes.",
        "owner_team": "payments-team",
        "created_by": "admin@triage.ai",
    },
    {
        "id": "rb-2",
        "title": "Redis cache pool exhaustion",
        "applies_to_services": ["cart-service"],
        "applies_to_error_types": ["redis_connection_error", "redis_oom"],
        "symptoms": "Redis connection timeout, cart storage failures.",
        "root_cause_pattern": "Maxmemory limit reached or client connections leaked.",
        "immediate_steps": "1. Verify Redis memory usage.\n2. Trigger cache eviction or restart redis server.",
        "permanent_fix": "Enable volatile-lru eviction policy and size connections pool correctly.",
        "escalate_if": "Redis memory exhaust recurs immediately after restart.",
        "owner_team": "core-infra",
        "created_by": "admin@triage.ai",
    }
]

MOCK_RESOLUTIONS = [
    {
        "id": "res-1",
        "incident_id": "inc-99",
        "resolved_by": "usr-sre1",
        "what_was_root_cause": "Stripe webhook failed to respond within 5 seconds due to a network glitch.",
        "what_fixed_it": "Manually re-queued the payment transaction from SRE panel.",
        "time_to_resolve_min": 10,
        "should_update_incident_knowledge": True,
        "incident_knowledge_id": "rb-1",
        "notes": "Stripe team confirmed a transient routing issue on their side.",
        "created_at": "2026-06-22T10:10:00Z"
    }
]

MOCK_HISTORICAL_INCIDENTS = [
    {
        "id": "inc-99",
        "service_id": "payment-service",
        "status": "completed",
        "created_at": "2026-06-22T10:00:00Z",
        "report": {
            "root_cause": "Stripe API timeout",
            "evidence_summary": "Stripe HTTP client timed out after 5.0 seconds in checkout view logs.",
            "affected_services": ["payment-service"],
            "remediation_steps": ["Check Stripe status, trigger manual retry of failed transactions."],
            "confidence_score": 0.88,
        }
    }
]


class MockIncidentKnowledgeProvider:
    """Mock implementation returning self-contained playbooks/resolutions."""

    def __init__(self, data_dir: Optional[Any] = None) -> None:
        """Initialise with optional data_dir."""
        pass

    async def search_incident_knowledge(
        self,
        service: str,
        error_type: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search mock incident knowledge."""
        results = []
        for r in MOCK_RUNBOOKS:
            if service not in r["applies_to_services"]:
                continue
            if error_type and error_type not in r["applies_to_error_types"]:
                continue
            if query:
                q = query.lower()
                title_match = q in r["title"].lower()
                symptom_match = q in r["symptoms"].lower()
                if not (title_match or symptom_match):
                    continue
            results.append(r)
        return results[:limit]

    async def get_incident_knowledge(
        self,
        incident_knowledge_id: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch detail of an incident knowledge entry by ID."""
        for r in MOCK_RUNBOOKS:
            if r["id"] == incident_knowledge_id:
                return r
        return None

    async def get_past_resolutions(
        self,
        service: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return mock resolutions for service."""
        # Join with similar incidents to verify service_id
        results = []
        for res in MOCK_RESOLUTIONS:
            inc_id = res["incident_id"]
            for inc in MOCK_HISTORICAL_INCIDENTS:
                if inc["id"] == inc_id and inc["service_id"] == service:
                    results.append(res)
                    break
        return results[:limit]

    async def get_similar_incidents(
        self,
        service: str,
        error_pattern: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return historical incidents for service."""
        results = []
        for inc in MOCK_HISTORICAL_INCIDENTS:
            if inc["service_id"] != service:
                continue
            if error_pattern:
                report = inc.get("report") or {}
                rc = report.get("root_cause", "").lower()
                es = report.get("evidence_summary", "").lower()
                if error_pattern.lower() not in rc and error_pattern.lower() not in es:
                    continue
            results.append(inc)
        return results[:limit]
