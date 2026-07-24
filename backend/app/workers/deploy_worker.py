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


class DeployWorker:
    """Background SQS worker processing CD deployment events."""

    def __init__(
        self,
        proposal_service: KGProposalService,
        deploy_mcp_client: Any,
        config: AgentSettings,
        sqs_client: Optional[Any] = None,
    ) -> None:
        """Initialise worker with dependencies."""
        self._proposal_service = proposal_service
        self._deploy_mcp_client = deploy_mcp_client
        self._config = config
        self._sqs_client = sqs_client
        self._running = False

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
        logger.info("DeployWorker started polling deployments queue...")
        # Polling loop structure for AWS SQS (aiobotocore / boto3)
        while self._running:
            try:
                # In mock/local mode, wait quietly unless invoked
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
