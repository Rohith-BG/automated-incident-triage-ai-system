"""
Background SQS consumer worker for deployment messages.

Consumes deployment notifications sent by GitHub Actions CD pipeline,
invokes Deploy MCP server analysis, and persists KG change proposals.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from agents.config import AgentSettings
from ..schemas.deploy_message import DeployMessage
from ..services.service_registry import KGProposalService

logger = logging.getLogger(__name__)

# Optional AWS imports - only used in production
try:
    import aioboto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    aioboto3 = None
    ClientError = Exception


class DeployWorker:
    """Background SQS worker processing CD deployment events."""

    def __init__(
        self,
        proposal_service: KGProposalService,
        deploy_mcp_client: Any,
        config: AgentSettings,
        aws_region: str = "us-east-1",
        queue_url: Optional[str] = None,
        dlq_url: Optional[str] = None,
    ) -> None:
        """Initialise worker with dependencies.

        Args:
            proposal_service: KGProposalService for persisting proposals.
            deploy_mcp_client: Deploy MCP client (must be initialized before use).
            config: Agent settings.
            aws_region: AWS region for SQS.
            queue_url: Source SQS queue URL (None = mock mode).
            dlq_url: Dead-letter queue URL for poison messages (Rule 10).
        """
        self._proposal_service = proposal_service
        self._deploy_mcp_client = deploy_mcp_client
        self._config = config
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
                "Poison deploy message: %s...; no DLQ configured, "
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
            logger.warning("Routed poison deploy message to DLQ %s", self._dlq_url)
        except Exception as e:
            logger.error("Failed to route deploy message to DLQ: %s", e)

    async def process_message_payload(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """Validate payload, analyze via deploy MCP tool, and save proposal."""
        # 1. Validate SQS message contract
        msg = DeployMessage.model_validate(raw_payload)

        logger.info(
            "DeployWorker processing deployment for %s (%s) on %s",
            msg.service_id,
            msg.commit_sha[:7],
            msg.repo,
        )

        # 2. Call Deploy MCP server tool `analyze_deployment`
        analysis_result = await self._deploy_mcp_client.call_tool(
            server="deploy",
            tool_name="analyze_deployment",
            arguments={
                "service_id": msg.service_id,
                "commit_sha": msg.commit_sha,
                "repo": msg.repo,
                "pr_number": msg.pr_number,
                "architecture_type": msg.architecture_type,
                "component_id": msg.component_id,
            },
        )

        proposed_changes = analysis_result.get("proposed_changes", [])
        diff_summary = analysis_result.get("diff_summary", "")

        # 3. Create proposal entry for human review
        proposal = await self._proposal_service.create_proposal(
            service_id=msg.service_id,
            commit_sha=msg.commit_sha,
            repo=msg.repo,
            proposed_changes=proposed_changes,
            architecture_type=msg.architecture_type,
            component_id=msg.component_id,
            diff_summary=diff_summary,
        )

        logger.info("DeployWorker created KGProposal %s for %s", proposal.id, msg.service_id)
        return proposal.to_dict()

    async def start(self) -> None:
        """Start worker loop consuming from SQS deployments-queue."""
        self._running = True

        # Initialize SQS client if queue URL is provided
        if self._queue_url:
            await self._initialize_sqs_client()

        if self._queue_url and self._sqs_client:
            logger.info("DeployWorker started consuming from SQS queue: %s", self._queue_url)
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
                                import json
                                from ..schemas.deploy_message import DeployMessage

                                # Parse the message body as JSON
                                message_data = json.loads(message['Body'])

                                # Process the deployment using existing logic
                                result = await self.process_message_payload(message_data)
                                logger.info(
                                    "Processed deployment for service %s: proposal_id=%s",
                                    message_data.get("service_id"),
                                    result.get("id") if isinstance(result, dict) else None,
                                )

                                # Delete message from queue after successful processing
                                await sqs.delete_message(
                                    QueueUrl=self._queue_url,
                                    ReceiptHandle=message['ReceiptHandle']
                                )
                            except Exception as e:
                                logger.error("Failed to process deployment message: %s", e)
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
                    logger.error("Error in DeployWorker SQS loop: %s", e)
                    await asyncio.sleep(5.0)
        else:
            logger.info("DeployWorker started polling deployments queue (mock mode)...")
            # Mock/local mode: wait quietly unless invoked externally
            while self._running:
                try:
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in DeployWorker loop: %s", e)
                    await asyncio.sleep(2.0)

    async def stop(self) -> None:
        """Stop worker loop."""
        self._running = False
        logger.info("DeployWorker stopped.")
