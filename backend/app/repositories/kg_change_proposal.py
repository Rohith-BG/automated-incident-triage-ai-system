"""
Repository for KG change proposal database operations.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.kg_change_proposal import KGChangeProposal
from ..enums import ProposalStatus


class KGChangeProposalRepository:
    """Database access layer for KG change proposals."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with database session."""
        self._session = session

    async def create(
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
        """Create and store a new KG change proposal."""
        proposal = KGChangeProposal(
            service_id=service_id,
            commit_sha=commit_sha,
            repo=repo,
            architecture_type=architecture_type,
            component_id=component_id or service_id,
            proposed_changes=proposed_changes,
            diff_summary=diff_summary,
            status=ProposalStatus.PENDING,
            parent_proposal_id=parent_proposal_id,
        )
        self._session.add(proposal)
        await self._session.flush()
        return proposal

    async def get_by_id(self, proposal_id: str) -> Optional[KGChangeProposal]:
        """Get proposal by ID."""
        stmt = select(KGChangeProposal).where(KGChangeProposal.id == proposal_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_pending_by_commit(
        self, service_id: str, commit_sha: str
    ) -> Optional[KGChangeProposal]:
        """Find an existing pending proposal for service and commit SHA."""
        stmt = (
            select(KGChangeProposal)
            .where(KGChangeProposal.service_id == service_id)
            .where(KGChangeProposal.commit_sha == commit_sha)
            .where(KGChangeProposal.status == ProposalStatus.PENDING)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_proposals(
        self,
        service_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[KGChangeProposal]:
        """List proposals filtered by service_id and/or status."""
        stmt = select(KGChangeProposal).order_by(KGChangeProposal.created_at.desc())
        if service_id:
            stmt = stmt.where(KGChangeProposal.service_id == service_id)
        if status:
            stmt = stmt.where(KGChangeProposal.status == status)
        stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        proposal_id: str,
        status: str,
        reviewed_by: Optional[str] = None,
        admin_feedback: Optional[str] = None,
    ) -> Optional[KGChangeProposal]:
        """Update proposal status and review metadata."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            return None

        proposal.status = status
        if reviewed_by:
            proposal.reviewed_by = reviewed_by
            proposal.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if admin_feedback:
            proposal.admin_feedback = admin_feedback

        await self._session.flush()
        return proposal
