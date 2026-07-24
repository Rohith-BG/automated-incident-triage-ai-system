"""
Incident controller — transport/formatting concerns only.

Converts between HTTP request payloads and service calls,
and formats service results into API response schemas.
No business logic, no direct database access.
"""

from typing import Optional
from typing import cast
from datetime import datetime
from ..enums import IncidentStatus
from ..models.incident import Incident
from ..schemas.incidents import (
    AlertResponse,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentSummaryResponse,
    IngestAlertRequest,
    IngestAlertResponse,
    ReportResponse,
)
from ..schemas.resolutions import CreateResolutionRequest, ResolutionResponse
from ..services.incident import IncidentService


class IncidentController:
    """HTTP transport layer for incident endpoints."""

    def __init__(self, service: IncidentService) -> None:
        """Initialise with an incident service.

        Args:
            service: Injected via FastAPI Depends chain.
        """
        self._service = service

    async def ingest_alert(
        self, payload: IngestAlertRequest
    ) -> IngestAlertResponse:
        """Process an incoming alert payload.

        Args:
            payload: Validated alert request body.

        Returns:
            Response indicating incident ID, status, and
            whether a new incident was created.
        """
        incident, is_new = await self._service.ingest_alert(
            service_id=payload.service_id,
            alert_message=payload.alert_message,
        )
        return IngestAlertResponse(
            incident_id=incident.id,
            status=incident.status,
            is_new=is_new,
        )

    async def get_incident(
        self, incident_id: str
    ) -> IncidentDetailResponse:
        """Fetch full incident detail.

        Args:
            incident_id: UUID of the incident.

        Returns:
            Detail response with alerts and report.
        """
        incident = await self._service.get_incident(incident_id)
        return self._to_detail(incident)

    async def list_incidents(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        service_id: Optional[str] = None,
        status: Optional[IncidentStatus] = None,
    ) -> IncidentListResponse:
        """List incidents with cursor-based pagination and filters.

        Args:
            limit: Max items per page.
            cursor: Opaque cursor from a previous response.
            service_id: Optional service filter.
            status: Optional status filter.

        Returns:
            Cursor-paginated list response.
        """
        incidents, next_cursor, has_more = (
            await self._service.list_incidents(
                limit=limit,
                cursor=cursor,
                service_id=service_id,
                status=status,
            )
        )
        items = [self._to_summary(inc) for inc in incidents]
        return IncidentListResponse(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            limit=limit,
        )

    @staticmethod
    def _to_summary(incident: Incident) -> IncidentSummaryResponse:
        """Convert an Incident model to a summary schema."""
        return IncidentSummaryResponse(
            id=incident.id,
            service_id=incident.service_id,
            status=incident.status,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            alert_count=len(list(incident.alerts)),
        )

    @staticmethod
    def _to_detail(incident: Incident) -> IncidentDetailResponse:
        """Convert an Incident model to a full detail schema."""
        

        alerts = [
            AlertResponse(
                id=a.id,
                incident_id=a.incident_id,
                alert_message=a.alert_message,
                created_at=a.created_at,
            )
            for a in list(incident.alerts)
        ]

        report = None
        if incident.report:
            r = incident.report
            report = ReportResponse(
                id=r.id,
                root_cause=r.root_cause,
                evidence_summary=r.evidence_summary,
                affected_services=list(r.affected_services),
                remediation_steps=list(r.remediation_steps),
                confidence_score=r.confidence_score,
                created_at=r.created_at,
            )

        resolution = None
        if incident.resolution:
            res = incident.resolution
            resolution = ResolutionResponse(
                id=res.id,
                incident_id=res.incident_id,
                resolved_by=res.resolved_by,
                what_was_root_cause=res.what_was_root_cause,
                what_fixed_it=res.what_fixed_it,
                time_to_resolve_min=res.time_to_resolve_min,
                should_update_incident_knowledge=res.should_update_incident_knowledge,
                incident_knowledge_id=res.incident_knowledge_id,
                notes=res.notes,
                created_at=res.created_at,
            )

        return IncidentDetailResponse(
            id=incident.id,
            service_id=incident.service_id,
            status=incident.status,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            alerts=alerts,
            report=report,
            resolution=resolution,
        )

    async def resolve_incident(
        self,
        incident_id: str,
        resolved_by: str,
        payload: CreateResolutionRequest,
    ) -> IncidentDetailResponse:
        """Resolve the incident via service and return detail."""
        incident = await self._service.resolve_incident(
            incident_id=incident_id,
            resolved_by=resolved_by,
            what_was_root_cause=payload.what_was_root_cause,
            what_fixed_it=payload.what_fixed_it,
            time_to_resolve_min=payload.time_to_resolve_min,
            should_update_incident_knowledge=payload.should_update_incident_knowledge,
            incident_knowledge_id=payload.incident_knowledge_id,
            notes=payload.notes,
        )
        return self._to_detail(incident)
