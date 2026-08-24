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

# Optional AWS imports - only used in production
try:
    import aioboto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    aioboto3 = None
    ClientError = Exception

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
        aws_region: str = "us-east-1",
        queue_url: Optional[str] = None,
        dlq_url: Optional[str] = None,
    ) -> None:
        """Initialise with async DB session factory and optional progress streaming callback.

        Args:
            session_factory: Factory returning an AsyncSession.
            progress_callback: Optional callback for streaming investigation progress.
            aws_region: AWS region for SQS.
            queue_url: Source SQS queue URL (None = mock mode).
            dlq_url: Dead-letter queue URL for poison messages (Rule 10).
        """
        self._session_factory = session_factory
        self._progress_callback = progress_callback or _ws_progress_callback
        self._aws_region = aws_region
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._running = False
        self._sqs_client = None

    async def _initialize_sqs_client(self) -> None:
        """Initialize AWS SQS client if queue URL is configured."""
        if not AWS_AVAILABLE or not self._queue_url:
            logger.warning("SQS not available or queue URL not configured - running in mock mode")
            return

        try:
            self._sqs_client = aioboto3.client(
                "sqs",
                region_name=self._aws_region
            )
            logger.info("SQS client initialized for queue: %s", self._queue_url)
        except Exception as e:
            logger.error("Failed to initialize SQS client: %s", e)
            self._sqs_client = None

    async def _process_sqs_message(self, message_body: str) -> None:
        """Process a single SQS message.

        Raises:
            Exception: Re-raised so the caller can route the poison
                message to the DLQ (Rule 10).
        """
        import json
        from backend.app.schemas.queue_messages import AlertQueueMessage

        # Parse the message body as JSON
        message_data = json.loads(message_body)
        alert_message = AlertQueueMessage(**message_data)

        # Process the alert using existing logic
        result = await self.process_alert(alert_message)
        logger.info(
            "Processed alert for service %s: incident_id=%s, is_duplicate=%s",
            alert_message.service_id,
            result.get("incident_id"),
            result.get("is_duplicate"),
        )

    async def _send_to_dlq(
        self,
        sqs: Any,
        message_body: str,
        receipt_handle: str,
    ) -> None:
        """Send a poison message to the dead-letter queue and delete it from source.

        Args:
            sqs: Active SQS client bound to the source queue.
            message_body: Raw message body to forward to the DLQ.
            receipt_handle: Receipt handle of the source message to delete.
        """
        if not self._dlq_url:
            logger.warning(
                "Poison message for alert: %s...; no DLQ configured, "
                "leaving it to the visibility timeout",
                message_body[:120],
            )
            return

        try:
            await sqs.send_message(
                QueueUrl=self._dlq_url,
                MessageBody=message_body,
            )
            await sqs.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
            )
            logger.warning("Routed poison message to DLQ %s", self._dlq_url)
        except Exception as e:
            logger.error("Failed to route message to DLQ: %s", e)

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

    async def start(self) -> None:
        """Start worker loop consuming from SQS alerts-queue."""
        self._running = True

        # Initialize SQS client if queue URL is provided
        if self._queue_url:
            await self._initialize_sqs_client()

        if self._queue_url and self._sqs_client:
            logger.info("AlertWorker started consuming from SQS queue: %s", self._queue_url)
            # Production mode: consume from actual SQS queue
            while self._running:
                try:
                    async with self._sqs_client as sqs:
                        response = await sqs.receive_message(
                            QueueUrl=self._queue_url,
                            AttributeNames=['All'],
                            MaxNumberOfMessages=10,
                            WaitTimeSeconds=20,  # Long polling
                            VisibilityTimeout=30
                        )

                        messages = response.get('Messages', [])
                        if not messages:
                            continue

                        for message in messages:
                            if not self._running:
                                break

                            try:
                                await self._process_sqs_message(message['Body'])
                                # Delete message from queue after successful processing
                                await sqs.delete_message(
                                    QueueUrl=self._queue_url,
                                    ReceiptHandle=message['ReceiptHandle']
                                )
                            except Exception as e:
                                logger.error("Failed to process message: %s", e)
                                await self._send_to_dlq(
                                    sqs,
                                    message['Body'],
                                    message['ReceiptHandle'],
                                )

                except ClientError as e:
                    logger.error("SQS client error: %s", e)
                    await asyncio.sleep(5.0)  # Wait before retrying
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in AlertWorker SQS loop: %s", e)
                    await asyncio.sleep(5.0)
        else:
            logger.info("AlertWorker started polling alerts queue (mock mode)...")
            # Mock/local mode: wait quietly unless invoked externally
            while self._running:
                try:
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in AlertWorker loop: %s", e)
                    await asyncio.sleep(2.0)

    async def stop(self) -> None:
        """Stop worker loop."""
        self._running = False
        logger.info("AlertWorker stopped.")
