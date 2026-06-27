"""
Alert webhook router.

Exposes endpoints to ingest alerts, perform deduplication, and
execute the triage orchestrator graph in the background, logging the final report.
"""

from datetime import datetime
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import run_investigation
from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.models.incident import Alert, Incident, RootCauseReportModel
from backend.app.schemas.alerts import AlertWebhookPayload, AlertWebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


async def run_orchestrator_task(
    incident_id: str,
    service_id: str,
    alert_message: str,
) -> None:
    """FastAPI background task worker.

    Runs the orchestrator graph, logs progress updates, and persists
    the final RootCauseReport to the DB, writing a structured log output.
    """
    logger.info(f"Background task started for incident {incident_id}")

    async def log_progress_callback(event: dict[str, Any]) -> None:
        """Helper callback to log orchestrator progress events."""
        logger.info(f"Progress event for incident {incident_id}: {event.get('event_type')} - {event.get('message')}")

    # 1. Run LangGraph investigation
    try:
        state = await run_investigation(
            incident_id=incident_id,
            service_id=service_id,
            alert_message=alert_message,
            progress_callback=log_progress_callback,
        )
        report = state.report
    except Exception as e:
        logger.exception(f"Exception during orchestrator run for incident {incident_id}: {e}")
        report = None

    # 2. Update database with final result
    async with AsyncSessionLocal() as session:
        try:
            # Fetch the incident
            stmt = select(Incident).where(Incident.id == incident_id)
            result = await session.execute(stmt)
            incident = result.scalars().first()

            if not incident:
                logger.error(f"Incident {incident_id} not found in database during post-processing")
                return

            if report:
                # Save synthesized report to DB
                db_report = RootCauseReportModel(
                    incident_id=incident_id,
                    root_cause=report.root_cause,
                    evidence_summary=report.evidence_summary,
                    affected_services=report.affected_services,
                    remediation_steps=report.remediation_steps,
                    confidence_score=report.confidence_score,
                )
                session.add(db_report)
                incident.status = "completed"
                
                # Structured logs for SRE analysis
                logger.info("=" * 60)
                logger.info(f"INCIDENT TRIAGE REPORT COMPLETED FOR: {incident_id}")
                logger.info(f"Root Cause       : {report.root_cause}")
                logger.info(f"Evidence Summary : {report.evidence_summary}")
                logger.info(f"Affected Services: {report.affected_services}")
                logger.info(f"Remediation      : {', '.join(report.remediation_steps)}")
                logger.info(f"Confidence Score : {report.confidence_score}")
                logger.info("=" * 60)
            else:
                incident.status = "failed"
                logger.warning(f"Incident {incident_id} triage failed (no report produced)")

            incident.updated_at = datetime.utcnow()
            await session.commit()

        except Exception as e:
            logger.exception(f"Error persisting orchestrator report to database: {e}")
            await session.rollback()


@router.post(
    "/alerts/webhook",
    response_model=AlertWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def alert_webhook(
    payload: AlertWebhookPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ingest monitoring alert, check for active duplicates, and triage.

    Deduplication rules:
    - If there is an active incident (status = 'investigating') on the same service,
      the alert is attached to it, avoiding duplicate LangGraph runs.
    - Otherwise, a new incident is created, and LangGraph is queued.
    """
    logger.info(f"Received webhook alert for service '{payload.service_id}'")

    # 1. Query for any active incident on the same service
    stmt = (
        select(Incident)
        .where(
            Incident.service_id == payload.service_id,
            Incident.status == "investigating",
        )
        .order_by(Incident.created_at.desc())
    )
    result = await db.execute(stmt)
    active_incident = result.scalars().first()

    if active_incident:
        logger.info(f"Deduplicated alert: service '{payload.service_id}' has active incident {active_incident.id}")
        # Attach alert payload to existing active incident
        alert = Alert(
            incident_id=active_incident.id,
            alert_message=payload.alert_message,
        )
        db.add(alert)
        await db.commit()

        return {
            "success": True,
            "incident_id": active_incident.id,
            "status": active_incident.status,
            "is_duplicate": True,
        }

    # 2. No active incident: create new incident and spawn background worker
    new_incident = Incident(
        service_id=payload.service_id,
        status="investigating",
    )
    db.add(new_incident)
    # Flush to ensure new_incident gets its autogenerated UUID
    await db.flush()

    alert = Alert(
        incident_id=new_incident.id,
        alert_message=payload.alert_message,
    )
    db.add(alert)
    await db.commit()

    logger.info(f"Created new incident {new_incident.id} for service '{payload.service_id}'. Spawning agent...")

    # Dispatch to background executor
    background_tasks.add_task(
        run_orchestrator_task,
        incident_id=new_incident.id,
        service_id=payload.service_id,
        alert_message=payload.alert_message,
    )

    return {
        "success": True,
        "incident_id": new_incident.id,
        "status": "investigating",
        "is_duplicate": False,
    }
