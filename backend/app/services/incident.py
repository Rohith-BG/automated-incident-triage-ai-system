"""
Incident service — business logic for incident lifecycle.

Owns deduplication decisions, investigation dispatch, and
status transitions. Never touches the database directly;
delegates all persistence to IncidentRepository.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from ..enums import IncidentStatus
from ..exceptions import NotFoundException
from ..models.incident import Incident
from ..repositories.incident import IncidentRepository

logger = logging.getLogger(__name__)


from ..repositories.incident_resolution import IncidentResolutionRepository

class IncidentService:
    """Business logic for incident management."""

    def __init__(
        self,
        repository: IncidentRepository,
        resolution_repository: Optional[IncidentResolutionRepository] = None,
    ) -> None:
        """Initialise with repositories.

        Args:
            repository: Injected via FastAPI Depends chain.
            resolution_repository: Injected via FastAPI Depends chain.
        """
        self._repo = repository
        self._resolution_repo = resolution_repository

    async def ingest_alert(
        self,
        service_id: str,
        alert_message: str,
    ) -> tuple[Incident, bool]:
        """Ingest an alert, deduplicating against active incidents.

        Status-driven dedup (Rule 13): if an active incident
        exists for the same service, the alert is attached to it.
        Otherwise a new incident is created.

        Args:
            service_id: Service that raised the alert.
            alert_message: Alert error message text.

        Returns:
            Tuple of (incident, is_new) where is_new is True
            when a fresh incident was created.
        """
        active = await self._repo.find_active_by_service(service_id)

        if active:
            logger.info(
                "Deduplicated alert: service '%s' has active "
                "incident %s",
                service_id,
                active.id,
            )
            await self._repo.attach_alert(
                incident_id=active.id,
                alert_message=alert_message,
            )
            return active, False

        # No active incident — create new
        incident = await self._repo.create(service_id)
        await self._repo.attach_alert(
            incident_id=incident.id,
            alert_message=alert_message,
        )
        logger.info(
            "Created new incident %s for service '%s'",
            incident.id,
            service_id,
        )
        return incident, True

    async def get_incident(self, incident_id: str) -> Incident:
        """Fetch a single incident by ID.

        Args:
            incident_id: UUID string.

        Returns:
            The Incident with eager-loaded alerts and report.

        Raises:
            NotFoundException: If incident does not exist.
        """
        incident = await self._repo.get_by_id(incident_id)
        if incident is None:
            raise NotFoundException(
                f"Incident '{incident_id}' not found.",
                context={"incident_id": incident_id},
            )
        return incident

    async def list_incidents(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        service_id: Optional[str] = None,
        status: Optional[IncidentStatus] = None,
    ) -> tuple[list[Incident], Optional[str], bool]:
        """Return a cursor-paginated, filtered list of incidents.

        Args:
            limit: Max items per page.
            cursor: Opaque cursor from a previous response.
            service_id: Optional service filter.
            status: Optional status filter.

        Returns:
            Tuple of (incidents, next_cursor, has_more).
        """
        return await self._repo.list_all(
            limit=limit,
            cursor=cursor,
            service_id=service_id,
            status=status,
        )

    async def complete_investigation(
        self,
        incident_id: str,
        report: Any,
    ) -> None:
        """Persist a successful investigation report.

        Saves the root-cause report and transitions the incident
        to COMPLETED status.

        Args:
            incident_id: Incident being completed.
            report: RootCauseReport from the orchestrator.
        """
        await self._repo.save_report(
            incident_id=incident_id,
            root_cause=report.root_cause,
            affected_services=report.affected_services,
            raw_logs=getattr(report, "raw_logs", {}),
            raw_metrics=getattr(report, "raw_metrics", {}),
            observability_analysis=getattr(
                report, "observability_analysis", ""
            ),
            code_diffs=getattr(report, "code_diffs", {}),
            past_resolutions=getattr(report, "past_resolutions", []),
            remediation_steps=report.remediation_steps,
            confidence_score=report.confidence_score,
            uncertainty=getattr(report, "uncertainty", ""),
        )
        await self._repo.update_status(
            incident_id, IncidentStatus.COMPLETED
        )

        logger.info(
            "Investigation completed for incident %s "
            "(confidence=%.2f)",
            incident_id,
            report.confidence_score,
        )

    async def fail_investigation(
        self,
        incident_id: str,
        reason: str,
    ) -> None:
        """Mark an investigation as failed.

        Args:
            incident_id: Incident that failed.
            reason: Human-readable failure reason.
        """
        await self._repo.update_status(
            incident_id, IncidentStatus.FAILED
        )
        logger.warning(
            "Investigation failed for incident %s: %s",
            incident_id,
            reason,
        )

    async def resolve_incident(
        self,
        incident_id: str,
        resolved_by: str,
        what_was_root_cause: str,
        what_fixed_it: str,
        time_to_resolve_min: int,
        should_update_incident_knowledge: bool = False,
        incident_knowledge_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Incident:
        """Resolve an active incident, attaching resolution notes.

        Args:
            incident_id: Incident to resolve.
            resolved_by: User ID of the resolving engineer.
            what_was_root_cause: Description of root cause.
            what_fixed_it: Steps taken that fixed the issue.
            time_to_resolve_min: Resolution time in minutes.
            should_update_incident_knowledge: True if SRE knowledge base needs updates.
            incident_knowledge_id: ID of linked pre-existing knowledge.
            notes: Extra optional notes.

        Returns:
            The updated Incident.
        """
        if not self._resolution_repo:
            raise RuntimeError("IncidentResolutionRepository not configured on service.")

        # This will raise NotFoundException if incident doesn't exist
        await self.get_incident(incident_id)

        # Transition status to RESOLVED
        await self._repo.update_status(incident_id, IncidentStatus.RESOLVED)

        # Create resolution record
        await self._resolution_repo.create(
            incident_id=incident_id,
            resolved_by=resolved_by,
            what_was_root_cause=what_was_root_cause,
            what_fixed_it=what_fixed_it,
            time_to_resolve_min=time_to_resolve_min,
            should_update_incident_knowledge=should_update_incident_knowledge,
            incident_knowledge_id=incident_knowledge_id,
            notes=notes,
        )

        return await self.get_incident(incident_id)
