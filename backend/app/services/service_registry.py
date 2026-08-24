"""
Services for Service Registry and KG Proposals management.
"""

import logging
from typing import Any, Optional

from ..exceptions import NotFoundException
from ..models.kg_change_proposal import KGChangeProposal
from ..models.service_registry import ServiceRegistry
from ..enums import ProposalStatus
from ..repositories.kg_change_proposal import KGChangeProposalRepository
from ..repositories.service_registry import ServiceRegistryRepository

logger = logging.getLogger(__name__)

KG_BOOTSTRAP_COMPONENT = "kg-bootstrap"


class ServiceRegistryService:
    """Service layer business logic for ServiceRegistry."""

    def __init__(self, repo: ServiceRegistryRepository) -> None:
        """Initialise with repository."""
        self._repo = repo

    async def register_service(
        self,
        service_id: str,
        repo: str,
        owner_team: str,
        architecture_type: str = "microservice",
        language: Optional[str] = None,
        alert_threshold: str = "medium",
    ) -> ServiceRegistry:
        """Register a new service."""
        existing = await self._repo.get_by_service_id(service_id)
        if existing:
            updated = await self._repo.update(
                service_id,
                repo=repo,
                owner_team=owner_team,
                architecture_type=architecture_type,
                language=language,
                alert_threshold=alert_threshold,
                is_active=True,
            )
            assert updated is not None  # guaranteed: checked above
            return updated
        return await self._repo.create(
            service_id=service_id,
            repo=repo,
            owner_team=owner_team,
            architecture_type=architecture_type,
            language=language,
            alert_threshold=alert_threshold,
        )

    async def get_service(self, service_id: str) -> ServiceRegistry:
        """Get service details by ID."""
        service = await self._repo.get_by_service_id(service_id)
        if not service:
            raise NotFoundException(f"Service '{service_id}' not registered.")
        return service

    async def list_services(self, active_only: bool = True) -> list[ServiceRegistry]:
        """List registered services."""
        return await self._repo.list_all(active_only=active_only)

    async def update_service(self, service_id: str, **kwargs: Any) -> ServiceRegistry:
        """Update service registry entry."""
        updated = await self._repo.update(service_id, **kwargs)
        if not updated:
            raise NotFoundException(f"Service '{service_id}' not found.")
        return updated

    async def delete_service(self, service_id: str) -> bool:
        """Deactivate service in registry."""
        success = await self._repo.delete(service_id)
        if not success:
            raise NotFoundException(f"Service '{service_id}' not found.")
        return True


class KGProposalService:
    """Service layer business logic for KG Change Proposals and human approval flow."""

    def __init__(
        self,
        proposal_repo: KGChangeProposalRepository,
        kg_store: Optional[Any] = None,
        deploy_mcp_client: Optional[Any] = None,
    ) -> None:
        """Initialise with repositories and graph store interfaces."""
        self._proposal_repo = proposal_repo
        self._kg_store = kg_store
        self._deploy_mcp_client = deploy_mcp_client

    async def create_proposal(
        self,
        service_id: str,
        commit_sha: str,
        repo: str,
        proposed_changes: list[dict[str, Any]],
        architecture_type: str = "microservice",
        component_id: str = "",
        diff_summary: str = "",
        parent_proposal_id: Optional[str] = None,
    ) -> KGChangeProposal:
        """Create new proposal or update existing pending proposal for same commit."""
        existing = await self._proposal_repo.find_pending_by_commit(service_id, commit_sha)
        if existing and not parent_proposal_id:
            logger.info("Pending proposal already exists for service %s commit %s", service_id, commit_sha)
            return existing

        return await self._proposal_repo.create(
            service_id=service_id,
            commit_sha=commit_sha,
            repo=repo,
            proposed_changes=proposed_changes,
            architecture_type=architecture_type,
            component_id=component_id,
            diff_summary=diff_summary,
            parent_proposal_id=parent_proposal_id,
        )

    async def get_proposal(self, proposal_id: str) -> KGChangeProposal:
        """Fetch proposal by ID."""
        proposal = await self._proposal_repo.get_by_id(proposal_id)
        if not proposal:
            raise NotFoundException(f"KGProposal '{proposal_id}' not found.")
        return proposal

    async def list_proposals(
        self,
        service_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[KGChangeProposal]:
        """List proposals."""
        return await self._proposal_repo.list_proposals(
            service_id=service_id, status=status, limit=limit
        )

    async def approve_proposal(self, proposal_id: str, reviewer: str) -> KGChangeProposal:
        """Approve proposal and apply mutations to the active Knowledge Graph store."""
        proposal = await self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"Cannot approve proposal in state '{proposal.status}'")

        if proposal.component_id == KG_BOOTSTRAP_COMPONENT:
            # Bootstrap approval promotes the staged graph into the
            # active graph (Rule 26: human approval required first).
            if self._kg_store:
                logger.info(
                    "Promoting staged bootstrap graph for proposal %s",
                    proposal_id,
                )
                await self._kg_store.promote_staging()
        elif self._kg_store:
            logger.info("Applying %d mutations from proposal %s to KG", len(proposal.proposed_changes), proposal_id)
            await self._kg_store.apply_mutations(proposal.proposed_changes)

        updated = await self._proposal_repo.update_status(
            proposal_id=proposal_id,
            status=ProposalStatus.APPROVED,
            reviewed_by=reviewer,
        )
        return updated  # type: ignore[return-value]

    async def reject_proposal(
        self, proposal_id: str, reviewer: str, reason: Optional[str] = None
    ) -> KGChangeProposal:
        """Reject proposal."""
        proposal = await self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"Cannot reject proposal in state '{proposal.status}'")

        updated = await self._proposal_repo.update_status(
            proposal_id=proposal_id,
            status=ProposalStatus.REJECTED,
            reviewed_by=reviewer,
            admin_feedback=reason,
        )
        return updated  # type: ignore[return-value]

    async def submit_feedback(
        self, proposal_id: str, reviewer: str, feedback: str
    ) -> KGChangeProposal:
        """Submit feedback for a proposal, triggering agent re-analysis loop."""
        proposal = await self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"Cannot add feedback to proposal in state '{proposal.status}'")

        # 1. Update status to feedback
        await self._proposal_repo.update_status(
            proposal_id=proposal_id,
            status=ProposalStatus.FEEDBACK,
            reviewed_by=reviewer,
            admin_feedback=feedback,
        )

        # 2. Call deploy MCP client if available to re-analyze with feedback
        new_changes = proposal.proposed_changes
        if proposal.component_id == KG_BOOTSTRAP_COMPONENT:
            new_changes = await self._apply_bootstrap_feedback(
                proposal, feedback
            )
        elif self._deploy_mcp_client:
            try:
                new_analysis = await self._deploy_mcp_client.call_tool(
                    server="deploy",
                    tool_name="re_analyze_with_feedback",
                    arguments={
                        "proposal_id": proposal_id,
                        "feedback_text": feedback,
                        "previous_changes": proposal.proposed_changes,
                    },
                )
                if isinstance(new_analysis, dict) and "proposed_changes" in new_analysis:
                    new_changes = new_analysis["proposed_changes"]
            except Exception as e:
                logger.error("Failed to re-analyze proposal with MCP client: %s", e)

        # 3. Create replacement proposal linked to parent
        new_proposal = await self._proposal_repo.create(
            service_id=proposal.service_id,
            commit_sha=proposal.commit_sha,
            repo=proposal.repo,
            proposed_changes=new_changes,
            architecture_type=proposal.architecture_type,
            component_id=proposal.component_id,
            diff_summary=proposal.diff_summary,
            parent_proposal_id=proposal.id,
        )

        # Mark original superseded
        await self._proposal_repo.update_status(
            proposal_id=proposal.id,
            status=ProposalStatus.SUPERSEDED.value,
        )

        return new_proposal

    async def _apply_bootstrap_feedback(
        self,
        proposal: KGChangeProposal,
        feedback: str,
    ) -> list[dict[str, Any]]:
        """Run the KG bootstrap revision loop for feedback on a bootstrap proposal.

        Builds the parent KgBootstrapState from the proposal, applies the
        feedback via the kg_builder workflow (deterministic intent parsing,
        entity resolution, MCP verification), and returns the updated
        mutation set with the staged graph already revised.
        """
        from agents.config import AgentSettings
        from agents.knowledge_graph.factory import create_kg_store
        from agents.mcp_client.factory import create_mcp_client
        from agents.kg_builder.graph import apply_feedback_revision

        config = AgentSettings()
        parent_state = await self._bootstrap_state_from_proposal(proposal)

        mcp_client = create_mcp_client(config)
        await mcp_client.initialize()
        try:
            kg_store = self._kg_store or create_kg_store(config)
            updated = await apply_feedback_revision(
                kg_store=kg_store,
                mcp_client=mcp_client,
                feedback_text=feedback,
                parent_state=parent_state,
                config=config,
            )
            return updated.mutations
        finally:
            await mcp_client.shutdown()

    @staticmethod
    async def _bootstrap_state_from_proposal(
        proposal: KGChangeProposal,
    ):
        """Rebuild a KgBootstrapState from a stored bootstrap proposal."""
        from agents.kg_builder.state import KgBootstrapState

        return KgBootstrapState(
            architecture_type=proposal.architecture_type,
            source="services_json",
            org="",
            repo=proposal.repo,
            owner_team="platform-team",
            mutations=list(proposal.proposed_changes),
            proposal_id=proposal.id,
        )
