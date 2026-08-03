"""
Incident REST API routes.

Provides endpoints for alert ingestion, incident listing,
and incident detail retrieval. All business logic delegates
through the Controller → Service → Repository chain.

The background orchestrator task runs outside the request
lifecycle and uses its own DB session for result persistence.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..controllers.incident import IncidentController
from ..core.database import AsyncSessionLocal, get_db
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


# ── Background orchestrator task ─────────────────────────


async def _run_orchestrator_task(
    incident_id: str,
    service_id: str,
    alert_message: str,
) -> None:
    """Background task: run the LangGraph investigation pipeline.

    Creates its own DB session to persist results, since
    the original request session is already closed by the
    time this runs.
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

    # 1. Run the agent pipeline
    report = None
    try:
        from agents.orchestrator import run_investigation

        state = await run_investigation(
            incident_id=incident_id,
            service_id=service_id,
            alert_message=alert_message,
            progress_callback=_broadcast_progress,
        )
        report = state.report
    except Exception as exc:
        logger.exception(
            "Orchestrator failed for incident %s: %s",
            incident_id,
            exc,
        )

    # 2. Persist results via service/repo (own session)
    async with AsyncSessionLocal() as session:
        try:
            repo = IncidentRepository(session=session)
            service = IncidentService(repository=repo)

            if report:
                await service.complete_investigation(
                    incident_id, report
                )
                logger.info(
                    "Investigation completed for incident %s "
                    "(confidence=%.2f)",
                    incident_id,
                    report.confidence_score,
                )
            else:
                await service.fail_investigation(
                    incident_id,
                    "No report produced by orchestrator",
                )

            await session.commit()
        except Exception as exc:
            logger.exception(
                "Failed to persist investigation result "
                "for incident %s: %s",
                incident_id,
                exc,
            )
            await session.rollback()


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
    controller: IncidentController = Depends(
        get_incident_controller
    ),
) -> IngestAlertResponse:
    """Ingest a monitoring alert.

    Deduplication: if an active incident exists for the same
    service, the alert is attached to it. Otherwise a new
    incident is created and a background investigation is
    dispatched.
    """
    response = await controller.ingest_alert(payload)

    if response.is_new:
        background_tasks.add_task(
            _run_orchestrator_task,
            incident_id=response.incident_id,
            service_id=payload.service_id,
            alert_message=payload.alert_message,
        )

    return response


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
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.SRE, UserRole.TEAM_MEMBER)),
    controller: IncidentController = Depends(get_incident_controller),
) -> IncidentDetailResponse:
    """Resolve an incident and attach resolution notes."""
    return await controller.resolve_incident(
        incident_id=incident_id,
        resolved_by=current_user.id,
        payload=payload,
    )
