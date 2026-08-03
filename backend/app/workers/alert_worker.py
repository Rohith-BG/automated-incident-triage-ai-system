"""
AlertWorker background SQS consumer.

Consumes AlertQueueMessage items from SQS (or in-memory mock queue in dev),
applies status-driven deduplication (Rule 13), executes the LangGraph orchestrator,
persists the report, and updates incident status.

WebSocket broadcasting: investigation progress events are pushed to
connected dashboard clients via global_ws_manager.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator.graph import run_investigation
from backend.app.enums import IncidentStatus
from backend.app.repositories.incident import IncidentRepository
from backend.app.schemas.queue_messages import AlertQueueMessage
from backend.app.websocket import global_ws_manager

logger = logging.getLogger(__name__)


async def _ws_progress_callback(event: dict[str, Any]) -> None:
    """Default progress callback broadcasting to WebSocket clients."""
    incident_id = event.get("incident_id", "unknown")
    await global_ws_manager.broadcast_event(incident_id, event)


class AlertWorker:
    """Idempotent background worker processing ingested SQS alert messages."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        progress_callback: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> None:
        """Initialise with async DB session factory and optional progress streaming callback."""
        self._session_factory = session_factory
        self._progress_callback = progress_callback or _ws_progress_callback

    async def process_alert(self, message: AlertQueueMessage) -> dict[str, Any]:
        """Process a single AlertQueueMessage.

        Rules:
        1. Status-driven deduplication (Rule 13): Check for active incident for service
           with status INVESTIGATING or ROOT_CAUSE_IDENTIFIED.
        2. If active incident exists, attach alert payload and skip starting duplicate workflow.
        3. If no active incident, create new Incident (INVESTIGATING), attach alert, run LangGraph.
        4. Save RootCauseReportModel and set status to ROOT_CAUSE_IDENTIFIED (or FAILED).

        Returns:
            Dict containing incident_id, is_duplicate, and final status.
        """
        logger.info(
            "Processing alert for service=%s source=%s",
            message.service_id,
            message.source,
        )

        async with self._session_factory() as session:
            repo = IncidentRepository(session)

            # 1. Deduplication check (Rule 13)
            active_incident = await repo.find_active_by_service(message.service_id)
            if active_incident:
                logger.info(
                    "Active incident %s found for service %s. Deduplicating alert.",
                    active_incident.id,
                    message.service_id,
                )
                await repo.attach_alert(
                    incident_id=active_incident.id,
                    alert_message=message.alert_message,
                )
                await session.commit()
                return {
                    "incident_id": active_incident.id,
                    "service_id": message.service_id,
                    "is_duplicate": True,
                    "status": active_incident.status,
                }

            # 2. Create new Incident
            incident = await repo.create(service_id=message.service_id)
            await repo.attach_alert(
                incident_id=incident.id,
                alert_message=message.alert_message,
            )
            await session.commit()
            incident_id = incident.id

        # 3. Dispatch LangGraph Orchestrator Investigation
        try:
            investigation_state = await run_investigation(
                incident_id=incident_id,
                service_id=message.service_id,
                alert_message=message.alert_message,
                progress_callback=self._progress_callback,
            )

            # 4. Save report and update status
            async with self._session_factory() as session:
                repo = IncidentRepository(session)
                report = investigation_state.report
                if report:
                    await repo.save_report(
                        incident_id=incident_id,
                        root_cause=report.root_cause,
                        evidence_summary=report.evidence_summary,
                        affected_services=report.affected_services,
                        remediation_steps=report.remediation_steps,
                        confidence_score=report.confidence_score,
                        uncertainty=report.uncertainty,
                        model_used=report.model_used,
                    )
                    final_status = (
                        IncidentStatus.ROOT_CAUSE_IDENTIFIED
                        if investigation_state.confidence_gate_passed
                        else IncidentStatus.INVESTIGATING
                    )
                    await repo.update_status(incident_id, final_status)
                else:
                    await repo.update_status(incident_id, IncidentStatus.FAILED)

                await session.commit()

            return {
                "incident_id": incident_id,
                "service_id": message.service_id,
                "is_duplicate": False,
                "status": IncidentStatus.ROOT_CAUSE_IDENTIFIED.value
                if investigation_state.confidence_gate_passed
                else IncidentStatus.INVESTIGATING.value,
            }

        except Exception as e:
            logger.error(
                "Error executing investigation for incident %s: %s",
                incident_id,
                e,
            )
            async with self._session_factory() as session:
                repo = IncidentRepository(session)
                await repo.update_status(incident_id, IncidentStatus.FAILED)
                await session.commit()
            raise
