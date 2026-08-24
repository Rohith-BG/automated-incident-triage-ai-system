"""
Service for KG bootstrap agent dispatch.

Bridges backend (HTTP/auth/DB/notifications) and agents (repo
intelligence MCP + LangGraph bootstrap workflow). Runs the agent,
persists the resulting proposal (component_id="kg-bootstrap",
commit_sha="kg-bootstrap"), and notifies the initiating admin.
"""

import logging
from typing import Any, Optional

from agents.config import AgentSettings
from agents.knowledge_graph.factory import create_kg_store
from agents.mcp_client.factory import create_mcp_client

from ..core.database import AsyncSessionLocal
from ..enums import ProposalStatus
from ..repositories.kg_change_proposal import KGChangeProposalRepository
from ..repositories.notification import NotificationRepository
from ..services.notification import NotificationService

logger = logging.getLogger(__name__)

KG_BOOTSTRAP_COMPONENT = "kg-bootstrap"
KG_BOOTSTRAP_COMMIT = "kg-bootstrap"


class KgBootstrapService:
    """Dispatch and orchestrate the KG bootstrap agent from the backend."""

    def __init__(
        self,
        proposal_repo: KGChangeProposalRepository,
        notification_repo: NotificationRepository,
        config: Optional[AgentSettings] = None,
    ) -> None:
        """Initialise with repositories and agent settings."""
        self._proposal_repo = proposal_repo
        self._notification_service = NotificationService(notification_repo)
        self._config = config or AgentSettings()

    @property
    def is_bootstrap_enabled(self) -> bool:
        """Whether the KG bootstrap agent is enabled in this environment."""
        return self._config.KG_BOOTSTRAP_ENABLED

    async def run_bootstrap(
        self,
        user_email: str,
        source: Optional[str] = None,
        org: Optional[str] = None,
        repo: Optional[str] = None,
        architecture_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run the KG bootstrap agent and persist a pending proposal.

        Opens its own DB session because this runs in a background
        task after the request session has closed. Builds the staged
        graph in the knowledge graph store, creates a KGChangeProposal
        carrying the proposed mutations, and notifies the initiating
        admin via the in-app notification channel.
        """
        from agents.kg_builder.graph import run_kg_bootstrap

        src = source or self._config.KG_BOOTSTRAP_SOURCE
        org_slug = org or self._config.KG_BOOTSTRAP_ORG or ""
        repo_slug = repo or self._config.KG_BOOTSTRAP_REPO or ""
        arch = architecture_type or self._config.KG_BOOTSTRAP_ARCHITECTURE

        mcp_client = create_mcp_client(self._config)
        await mcp_client.initialize()
        try:
            kg_store = create_kg_store(self._config)
            state = await run_kg_bootstrap(
                kg_store=kg_store,
                mcp_client=mcp_client,
                config=self._config,
                source=src,
                org=org_slug,
                repo=repo_slug,
            )
        finally:
            await mcp_client.shutdown()

        async with AsyncSessionLocal() as session:
            proposal_repo = KGChangeProposalRepository(session=session)
            notification_service = NotificationService(
                NotificationRepository(session=session)
            )

            proposal = await proposal_repo.create(
                service_id=repo_slug or org_slug or "kg-bootstrap",
                commit_sha=KG_BOOTSTRAP_COMMIT,
                repo=repo_slug or org_slug or "",
                proposed_changes=state.mutations,
                architecture_type=arch,
                component_id=KG_BOOTSTRAP_COMPONENT,
                diff_summary=state.diff_summary,
            )
            await session.commit()

            await notification_service.notify_and_broadcast(
                user_email=user_email,
                category="kg_bootstrap",
                title="Knowledge graph bootstrap ready for review",
                message=(
                    f"Staged {len(state.mutations)} mutation(s): {state.diff_summary}. "
                    f"Review the proposal before it reaches the active graph."
                ),
                payload={
                    "proposal_id": proposal.id,
                    "uncertainty": state.uncertainty,
                },
            )
            await session.commit()

            result = proposal.to_dict()
            result["uncertainty"] = state.uncertainty
            return result

    async def get_status(self) -> dict[str, Any]:
        """Return KG bootstrap status for the UI CTA.

        Reports whether a pending bootstrap proposal exists, whether
        any proposal was approved, and whether the active graph has
        content. Used to decide whether to show the 'Build KG' prompt.
        """
        pending = await self._proposal_repo.list_proposals(
            status=ProposalStatus.PENDING, limit=50
        )
        bootstrap_pending = [
            p for p in pending if p.component_id == KG_BOOTSTRAP_COMPONENT
        ]

        approved = await self._proposal_repo.list_proposals(
            status=ProposalStatus.APPROVED, limit=50
        )
        bootstrap_approved = [
            p for p in approved if p.component_id == KG_BOOTSTRAP_COMPONENT
        ]

        has_active_graph = False
        try:
            kg_store = create_kg_store(self._config)
            services = await kg_store.get_all_services()
            has_active_graph = len(services) > 0
        except Exception as e:
            logger.warning("Could not check active graph status: %s", e)

        return {
            "needs_bootstrap": not has_active_graph and not bootstrap_pending,
            "has_active_graph": has_active_graph,
            "bootstrap_enabled": self._config.KG_BOOTSTRAP_ENABLED,
            "pending_proposal_id": (
                bootstrap_pending[0].id if bootstrap_pending else None
            ),
            "approved_proposal_id": (
                bootstrap_approved[0].id if bootstrap_approved else None
            ),
            "pending_count": len(bootstrap_pending),
        }

    async def get_staging_snapshot(self) -> dict[str, Any]:
        """Return the current staged graph for visualization."""
        kg_store = create_kg_store(self._config)
        return await kg_store.staging_snapshot()

    async def get_active_snapshot(self) -> dict[str, Any]:
        """Return the active production graph for visualization."""
        kg_store = create_kg_store(self._config)
        return await kg_store.active_snapshot()

