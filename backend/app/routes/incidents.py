"""
Incident REST API routes.

Provides endpoints for alert ingestion, incident listing,
and incident detail retrieval. All business logic delegates
through the Controller → Service → Repository chain.

The background orchestrator task runs outside the request
lifecycle and uses its own DB session for result persistence.
"""

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..controllers.incident import IncidentController
from ..core.database import AsyncSessionLocal, get_db, sqlite_serialize_writes

from ..dependencies import get_incident_controller, get_current_user, require_role
from ..enums import IncidentStatus, UserRole
from ..models.user import User
from ..repositories.incident import IncidentRepository
from ..schemas.incidents import (
    IncidentDetailResponse,
    IncidentListResponse,
    IngestAlertRequest,
    IngestAlertResponse,
)
from ..schemas.resolutions import CreateResolutionRequest, ResolutionResponse
from ..services.incident import IncidentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])

# Max time the background investigation may run before forced timeout.
_INVESTIGATION_TIMEOUT_SECONDS = 300  # 5 minutes

# Persistence is retried because a background investigation writes to the
# same database as live requests and workers. On SQLite a concurrent writer
# surfaces as "database is locked", and losing that race must never leave an
# incident stuck in INVESTIGATING.
_PERSIST_MAX_ATTEMPTS = 3
_PERSIST_RETRY_BASE_DELAY_SECONDS = 0.5


async def _persist_with_retry(
    description: str,
    operation: Any,
    incident_id: str,
) -> bool:
    """Run a DB write with bounded exponential-backoff retries.

    Args:
        description: Human-readable label used in log messages.
        operation: Zero-argument awaitable factory performing the write.
        incident_id: Incident the write belongs to, for log correlation.

    Returns:
        True if the write eventually succeeded, False if every attempt failed.
    """
    for attempt in range(1, _PERSIST_MAX_ATTEMPTS + 1):
        try:
            await operation()
            return True
        except Exception as exc:
            if attempt == _PERSIST_MAX_ATTEMPTS:
                logger.error(
                    "%s failed for incident %s after %d attempts: %s",
                    description,
                    incident_id,
                    _PERSIST_MAX_ATTEMPTS,
                    exc,
                    exc_info=True,
                )
                return False
            delay = _PERSIST_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "%s failed for incident %s (attempt %d/%d): %s "
                "- retrying in %.1fs",
                description,
                incident_id,
                attempt,
                _PERSIST_MAX_ATTEMPTS,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    return False  # pragma: no cover - loop always returns


async def _force_terminal_status(
    incident_id: str,
    status: IncidentStatus,
) -> bool:
    """Drive an incident to a terminal status using a fresh session per attempt.

    This is the last-resort transition. It runs in its own session so that a
    poisoned session (or a lock held by a partially-applied report insert)
    cannot prevent the incident from ever leaving INVESTIGATING. Leaving an
    incident in INVESTIGATING also wedges the service: deduplication keeps
    routing new alerts onto the zombie incident forever.

    Args:
        incident_id: Incident to transition.
        status: Terminal status to apply.

    Returns:
        True if the status was persisted.
    """

    async def _attempt() -> None:
        async with sqlite_serialize_writes():
            async with AsyncSessionLocal() as session:
                try:
                    repo = IncidentRepository(session=session)
                    await repo.update_status(incident_id, status)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise


    applied = await _persist_with_retry(
        f"Forcing incident status to {status.value}",
        _attempt,
        incident_id,
    )
    if applied:
        logger.info(
            "Incident %s transitioned to %s", incident_id, status.value
        )
    else:
        # Nothing further can be done automatically; make it actionable.
        logger.critical(
            "Could not persist status %s for incident %s. It is wedged in "
            "INVESTIGATING and will block deduplication for its service. "
            "Update the incidents row manually or re-trigger via "
            "POST /incidents/%s/investigate.",
            status.value,
            incident_id,
            incident_id,
        )
    return applied


# ── Background orchestrator task ─────────────────────────


async def _run_orchestrator_task(
    incident_id: str,
    service_id: str,
    alert_message: str,
) -> None:
    """Background task: run the LangGraph investigation pipeline.

    Creates its own DB session to persist results, since
    the original request session is already closed by the
    time this runs. Bounded by _INVESTIGATION_TIMEOUT_SECONDS
    to prevent hanging forever on stuck MCP/LLM calls.

    Always drives the incident to a terminal status. An incident
    left in INVESTIGATING is not merely cosmetic: it is an active
    status, so alert deduplication keeps attaching new alerts to it
    and the service can never raise a fresh incident.
    """
    logger.info(
        "Background investigation started for incident %s",
        incident_id,
    )

    from ..websocket import global_ws_manager

    async def _broadcast_progress(event: dict[str, Any]) -> None:
        logger.info(
            "Progress [%s]: %s - %s",
            incident_id,
            event.get("event_type"),
            event.get("message"),
        )
        await global_ws_manager.broadcast_event(incident_id, event)

    # 1. Run the agent pipeline with an overall timeout
    report = None
    failure_reason = ""
    try:
        from agents.orchestrator import run_investigation

        state = await asyncio.wait_for(
            run_investigation(
                incident_id=incident_id,
                service_id=service_id,
                alert_message=alert_message,
                progress_callback=_broadcast_progress,
            ),
            timeout=_INVESTIGATION_TIMEOUT_SECONDS,
        )
        report = state.report
    except asyncio.TimeoutError:
        failure_reason = (
            f"Investigation timed out after "
            f"{_INVESTIGATION_TIMEOUT_SECONDS}s"
        )
        logger.error(
            "Orchestrator timed out for incident %s after %ds",
            incident_id,
            _INVESTIGATION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        failure_reason = f"Orchestrator exception: {exc}"
        logger.exception(
            "Orchestrator failed for incident %s: %s",
            incident_id,
            exc,
        )

    # 2. Persist the report and transition to a terminal status.
    #    The report write and the status write are independent: losing the
    #    report must not stop the status from advancing, otherwise the
    #    incident is left in INVESTIGATING indefinitely.
    report_saved = False
    if report:
        async def _save_report() -> None:
            async with sqlite_serialize_writes():
                async with AsyncSessionLocal() as session:
                    try:
                        repo = IncidentRepository(session=session)
                        # Verify the incident is visible to this
                        # session before attempting the report INSERT.
                        incident = await repo.get_by_id(incident_id)
                        if incident is None:
                            raise RuntimeError(
                                f"Incident {incident_id} not found "
                                "in database — commit race; will retry"
                            )
                        service = IncidentService(repository=repo)
                        await service.complete_investigation(
                            incident_id, report
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise


        report_saved = await _persist_with_retry(
            "Persisting investigation report", _save_report, incident_id
        )

    if report_saved:
        logger.info(
            "Investigation completed for incident %s (confidence=%.2f)",
            incident_id,
            report.confidence_score,
        )
        await _force_terminal_status(
            incident_id, IncidentStatus.COMPLETED
        )
    else:
        if report:
            logger.error(
                "Report was produced for incident %s but could not be "
                "persisted; marking the incident FAILED instead of "
                "leaving it INVESTIGATING",
                incident_id,
            )
        await _force_terminal_status(
            incident_id,
            IncidentStatus.FAILED,
        )
        logger.warning(
            "Investigation did not complete for incident %s: %s",
            incident_id,
            failure_reason or "No report produced by orchestrator",
        )


# ── Endpoints ────────────────────────────────────────────


@router.post(
    "/ingest",
    response_model=IngestAlertResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest an alert and trigger investigation",
)
async def ingest_alert(
    payload: IngestAlertRequest,
    background_tasks: BackgroundTasks,
    force: bool = Query(
        False,
        description="Force trigger investigation even if attached to an existing active incident",
    ),
    db: AsyncSession = Depends(get_db),
    controller: IncidentController = Depends(
        get_incident_controller
    ),
) -> IngestAlertResponse:
    """Ingest a monitoring alert.

    Deduplication: if an active incident exists for the same
    service, the alert is attached to it. Otherwise a new
    incident is created and a background investigation is
    dispatched. If force=True, investigation is dispatched
    even when attached to an existing incident.
    """
    response = await controller.ingest_alert(payload)

    # Commit the incident to the database BEFORE dispatching
    # the background task.  Without this explicit commit the
    # dependency-cleanup commit (code after ``get_db`` yield)
    # can race with the background task on PostgreSQL, causing
    # FK violations when the report INSERT runs before the
    # incident row is visible.
    await db.commit()

    if response.is_new or force:
        background_tasks.add_task(
            _run_orchestrator_task,
            incident_id=response.incident_id,
            service_id=payload.service_id,
            alert_message=payload.alert_message,
        )

    return response


@router.post(
    "/{incident_id}/investigate",
    response_model=dict[str, Any],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger investigation for an existing incident",
)
async def trigger_investigation(
    incident_id: str,
    background_tasks: BackgroundTasks,
    controller: IncidentController = Depends(
        get_incident_controller
    ),
) -> dict[str, Any]:
    """Trigger or re-trigger an investigation for an existing incident.

    Resets status to INVESTIGATING so stuck/failed incidents
    can be re-processed cleanly.
    """
    incident = await controller.get_incident(incident_id)
    alert_msg = (
        incident.alerts[-1].alert_message
        if incident.alerts
        else "Manual trigger"
    )

    # Reset status so the pipeline starts fresh
    async with sqlite_serialize_writes():
        async with AsyncSessionLocal() as session:
            repo = IncidentRepository(session=session)
            await repo.update_status(
                incident_id, IncidentStatus.INVESTIGATING
            )
            await session.commit()

    background_tasks.add_task(
        _run_orchestrator_task,
        incident_id=incident.id,
        service_id=incident.service_id,
        alert_message=alert_msg,
    )
    return {
        "incident_id": incident.id,
        "status": "investigation_dispatched",
        "message": f"Investigation dispatched for {incident.id}",
    }


@router.get(
    "",
    response_model=IncidentListResponse,
    summary="List incidents",
)
async def list_incidents(
    limit: int = Query(
        20, ge=1, le=100, description="Items per page"
    ),
    cursor: Optional[str] = Query(
        None,
        description="Opaque cursor from a previous response",
    ),
    service_id: Optional[str] = Query(
        None, description="Filter by service"
    ),
    status_filter: Optional[IncidentStatus] = Query(
        None,
        alias="status",
        description="Filter by incident status",
    ),
    controller: IncidentController = Depends(
        get_incident_controller
    ),
) -> IncidentListResponse:
    """Return a cursor-paginated list of incidents.

    Supports optional filtering by service_id and status.
    Pass the ``next_cursor`` value from a previous response
    as ``?cursor=`` to fetch the next page.
    """
    return await controller.list_incidents(
        limit=limit,
        cursor=cursor,
        service_id=service_id,
        status=status_filter,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="Get incident detail",
)
async def get_incident(
    incident_id: str,
    controller: IncidentController = Depends(
        get_incident_controller
    ),
) -> IncidentDetailResponse:
    """Return full incident detail including alerts and report."""
    return await controller.get_incident(incident_id)


@router.post(
    "/{incident_id}/resolution",
    response_model=IncidentDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Resolve an incident and attach resolution notes",
)
async def resolve_incident(
    incident_id: str,
    payload: CreateResolutionRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.DEVELOPER)),
    controller: IncidentController = Depends(get_incident_controller),
) -> IncidentDetailResponse:
    """Resolve an incident and attach resolution notes."""
    return await controller.resolve_incident(
        incident_id=incident_id,
        resolved_by=current_user.id,
        payload=payload,
    )
