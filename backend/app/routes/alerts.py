"""
Alert webhook router — backwards-compatible alias.

Delegates to the same incident ingestion pipeline as
``POST /incidents/ingest``. Kept for backwards compatibility
during the transition period.
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..controllers.incident import IncidentController
from ..core.database import get_db
from ..dependencies import get_incident_controller
from ..schemas.alerts import AlertWebhookPayload, AlertWebhookResponse
from ..schemas.incidents import IngestAlertRequest
from .incidents import _run_orchestrator_task

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


@router.post(
    "/alerts/webhook",
    response_model=AlertWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def alert_webhook(
    payload: AlertWebhookPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    controller: IncidentController = Depends(
        get_incident_controller
    ),
) -> dict[str, Any]:
    """Ingest monitoring alert (backwards-compatible endpoint).

    Delegates to the incident controller's ingest_alert method
    and maps the response to the legacy AlertWebhookResponse
    format.
    """
    logger.info(
        "Received webhook alert for service '%s'",
        payload.service_id,
    )

    # Reuse the canonical IngestAlertRequest
    request = IngestAlertRequest(
        service_id=payload.service_id,
        alert_message=payload.alert_message,
    )
    response = await controller.ingest_alert(request)

    # Commit before dispatching background task (same reason
    # as ingest_alert — dependency-cleanup commit can race).
    await db.commit()

    if response.is_new:
        background_tasks.add_task(
            _run_orchestrator_task,
            incident_id=response.incident_id,
            service_id=payload.service_id,
            alert_message=payload.alert_message,
        )

    return {
        "success": True,
        "incident_id": response.incident_id,
        "status": response.status,
        "is_duplicate": not response.is_new,
    }
