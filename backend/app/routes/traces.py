"""
Agent execution traces REST API route.

Exposes investigation tool execution traces for a given incident.
Uses TraceService injected via DI — route never imports agents/ directly
(Rule 6: backend↔agent boundary separation).
"""

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_current_user, get_trace_service
from backend.app.services.trace import TraceService

router = APIRouter(prefix="/incidents", tags=["traces"])


@router.get(
    "/{incident_id}/traces",
    summary="Get agent execution traces for an incident",
)
async def get_incident_traces(
    incident_id: str,
    _: Any = Depends(get_current_user),
    trace_service: TraceService = Depends(get_trace_service),
) -> dict[str, Any]:
    """Return agent tool execution traces for a given incident.

    Includes per-tool latency, token usage, success/failure,
    and aggregate summary metrics.
    """
    return trace_service.get_incident_traces(incident_id)
