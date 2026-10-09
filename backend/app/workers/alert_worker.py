"""
AlertWorker background SQS consumer.

Consumes AlertQueueMessage items from SQS (or in-memory mock queue in dev),
applies status-driven deduplication (Rule 13), executes the LangGraph orchestrator,
persists the report, and updates incident status.

CloudWatch alarm payloads (which lack a ``service_id``) are parsed via
``CloudWatchAlarmPayload`` and resolved to a known ``service_id`` through
the ``ServiceResolver`` at the SQS consumer boundary.

WebSocket broadcasting: investigation progress events are pushed to
connected dashboard clients via global_ws_manager.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator.graph import run_investigation
from backend.app.enums import IncidentStatus
from backend.app.repositories.incident import IncidentRepository
from backend.app.schemas.queue_messages import (
    AlertQueueMessage,
    CloudWatchAlarmPayload,
)
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


def _is_cloudwatch_envelope(data: dict[str, Any]) -> bool:
    """Return True if *data* looks like a CloudWatch alarm payload.

    CloudWatch alarms always contain ``AlarmName``.  They may arrive
    raw or wrapped in an SNS envelope (with a ``Message`` string field).
    """
    return "AlarmName" in data or (
        "Message" in data and "Type" in data
    )


def _parse_cloudwatch_envelope(
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Unwrap optional SNS envelope and return alarm data dict.

    CloudWatch → SNS → SQS delivers the alarm JSON as a string
    inside the ``Message`` field of the SNS notification.  Direct
    CloudWatch → SQS (without SNS) delivers the alarm JSON directly.
    """
    if "Message" in raw and isinstance(raw["Message"], str):
        # SNS envelope — double-parse
        try:
            return json.loads(raw["Message"])
        except (json.JSONDecodeError, TypeError):
            pass
    # Direct alarm payload or already unwrapped
    return raw


def _build_alert_message_from_alarm(
    alarm: CloudWatchAlarmPayload,
) -> str:
    """Construct a human-readable alert_message from CloudWatch fields.

    Combines AlarmName, NewStateReason, and optionally
    AlarmDescription into a single string the downstream
    pipeline (orchestrator, LLM synthesizer) can consume.
    """
    parts = [f"CloudWatch Alarm: {alarm.AlarmName}"]
    if alarm.AlarmDescription:
        parts.append(alarm.AlarmDescription)
    if alarm.NewStateReason:
        parts.append(f"Reason: {alarm.NewStateReason}")
    trigger = alarm.Trigger
    if trigger.MetricName:
        parts.append(
            f"Metric: {trigger.MetricName} "
            f"({trigger.Namespace})"
        )
    return " | ".join(parts)


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

    async def _resolve_service_id_from_alarm(
        self,
        alarm_data: dict[str, Any],
    ) -> dict[str, Optional[str]]:
        """Resolve service_id from CloudWatch alarm data via KG.

        Returns:
            Dict with ``service_id`` and ``entry_point``
            (both may be None on failure).
        """
        from agents.config import agent_settings
        from agents.knowledge_graph.factory import create_kg_store
        from backend.app.services.service_resolver import (
            ServiceResolver,
        )

        try:
            kg = create_kg_store(agent_settings)
            known = await kg.get_all_services()
        except Exception as e:
            logger.error(
                "Failed to load service list from KG: %s", e
            )
            known = []

        resolver = ServiceResolver(known)
        return resolver.resolve(alarm_data)

    async def _process_sqs_message(self, message_body: str) -> None:
        """Process a single SQS message.

        Handles two payload shapes:
        1. **CloudWatch alarm** — has ``AlarmName`` (possibly inside
           an SNS ``Message`` envelope).  Resolved to a known
           ``service_id`` via ``ServiceResolver``.
        2. **Internal AlertQueueMessage** — direct JSON with
           ``service_id`` and ``alert_message``.

        Raises:
            Exception: Re-raised so the caller can route the poison
                message to the DLQ (Rule 10).
        """
        message_data = json.loads(message_body)

        if _is_cloudwatch_envelope(message_data):
            # CloudWatch alarm path
            alarm_data = _parse_cloudwatch_envelope(message_data)
            alarm = CloudWatchAlarmPayload(**alarm_data)

            # Only process ALARM state transitions
            if alarm.NewStateValue != "ALARM":
                logger.info(
                    "Skipping non-ALARM state: %s for %s",
                    alarm.NewStateValue,
                    alarm.AlarmName,
                )
                return

            resolved = await self._resolve_service_id_from_alarm(
                alarm_data
            )
            service_id = resolved.get("service_id")
            if not service_id:
                raise ValueError(
                    f"Could not resolve service_id from "
                    f"CloudWatch alarm: {alarm.AlarmName}"
                )

            alert_message = _build_alert_message_from_alarm(alarm)

            # Build entry_point info into metadata for
            # monolith entry_point extraction downstream
            metadata: dict[str, Any] = {
                "cloudwatch_alarm_name": alarm.AlarmName,
                "cloudwatch_namespace": (
                    alarm.Trigger.Namespace
                ),
                "cloudwatch_metric": alarm.Trigger.MetricName,
                "cloudwatch_region": alarm.Region,
            }
            entry_point = resolved.get("entry_point")
            if entry_point:
                metadata["entry_point"] = entry_point
                # Prepend entry_point to alert_message so
                # the orchestrator's _extract_module_entry_point
                # can find it for monolith architectures
                alert_message = (
                    f"[{entry_point}] {alert_message}"
                )

            alert_msg = AlertQueueMessage(
                service_id=service_id,
                alert_message=alert_message,
                source="cloudwatch",
                metric_name=alarm.Trigger.MetricName or None,
                metadata=metadata,
            )
        else:
            # Internal / direct AlertQueueMessage path
            alert_msg = AlertQueueMessage(**message_data)
            # If only service_name provided (no service_id),
            # resolve via KG
            if not alert_msg.service_id and alert_msg.service_name:
                from agents.config import agent_settings
                from agents.knowledge_graph.factory import (
                    create_kg_store,
                )

                kg = create_kg_store(agent_settings)
                known = await kg.get_all_services()
                lower_map = {s.lower(): s for s in known}
                resolved_id = lower_map.get(
                    alert_msg.service_name.lower()
                )
                if not resolved_id:
                    raise ValueError(
                        f"service_name '{alert_msg.service_name}' "
                        f"not found in known services"
                    )
                alert_msg.service_id = resolved_id

        result = await self.process_alert(alert_msg)
        logger.info(
            "Processed alert for service %s: "
            "incident_id=%s, is_duplicate=%s",
            alert_msg.service_id,
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
        4. Save RootCauseReportModel and move the incident to a terminal
           status: ROOT_CAUSE_IDENTIFIED when the confidence gate passes,
           COMPLETED when the gate fails (a report was still delivered),
           FAILED when no report could be produced. The incident is never
           left in INVESTIGATING.

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
                        affected_services=report.affected_services,
                        raw_logs=report.raw_logs,
                        raw_metrics=report.raw_metrics,
                        observability_analysis=report.observability_analysis,
                        code_diffs=report.code_diffs,
                        past_resolutions=report.past_resolutions,
                        remediation_steps=report.remediation_steps,
                        confidence_score=report.confidence_score,
                        uncertainty=report.uncertainty,
                    )
                    # The gate decision is recorded on the report, never on
                    # the lifecycle status. Reverting to INVESTIGATING here
                    # would leave an incident that has already produced a
                    # report looking like it is still running, and because
                    # INVESTIGATING is an active status it would also block
                    # deduplication from ever raising a fresh incident for
                    # this service.
                    final_status = (
                        IncidentStatus.ROOT_CAUSE_IDENTIFIED
                        if investigation_state.confidence_gate_passed
                        else IncidentStatus.COMPLETED
                    )
                    await repo.update_status(incident_id, final_status)
                else:
                    final_status = IncidentStatus.FAILED
                    await repo.update_status(incident_id, final_status)

                await session.commit()

            return {
                "incident_id": incident_id,
                "service_id": message.service_id,
                "is_duplicate": False,
                "status": final_status.value,
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
