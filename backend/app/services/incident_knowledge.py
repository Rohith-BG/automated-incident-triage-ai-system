"""
Incident knowledge service — CRUD logic for pre-written SRE knowledge/runbooks.
"""

import logging
from typing import Optional

from ..exceptions import NotFoundException
from ..models.incident_knowledge import IncidentKnowledge
from ..repositories.incident_knowledge import IncidentKnowledgeRepository
from ..schemas.incident_knowledge import CreateIncidentKnowledgeRequest, UpdateIncidentKnowledgeRequest

logger = logging.getLogger(__name__)


class IncidentKnowledgeService:
    """Business logic for SRE knowledge base (incident_knowledges)."""

    def __init__(self, repository: IncidentKnowledgeRepository) -> None:
        """Initialise with the repository."""
        self._repo = repository

    async def create_knowledge(
        self,
        created_by: str,
        data: CreateIncidentKnowledgeRequest,
    ) -> IncidentKnowledge:
        """Create a new knowledge/runbook entry."""
        return await self._repo.create(
            title=data.title,
            applies_to_services=data.applies_to_services,
            applies_to_error_types=data.applies_to_error_types,
            symptoms=data.symptoms,
            root_cause_pattern=data.root_cause_pattern,
            immediate_steps=data.immediate_steps,
            permanent_fix=data.permanent_fix,
            escalate_if=data.escalate_if,
            owner_team=data.owner_team,
            created_by=created_by,
        )

    async def get_knowledge(self, ik_id: str) -> IncidentKnowledge:
        """Fetch an entry by ID, raising NotFoundException if missing."""
        ik = await self._repo.get_by_id(ik_id)
        if not ik:
            raise NotFoundException(
                f"Incident knowledge entry '{ik_id}' not found.",
                context={"incident_knowledge_id": ik_id},
            )
        return ik

    async def list_knowledge(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        service_id: Optional[str] = None,
    ) -> tuple[list[IncidentKnowledge], Optional[str], bool]:
        """Fetch a cursor-paginated list of knowledge entries."""
        return await self._repo.list_all(
            limit=limit,
            cursor=cursor,
            service_id=service_id,
        )

    async def update_knowledge(
        self,
        ik_id: str,
        data: UpdateIncidentKnowledgeRequest,
    ) -> IncidentKnowledge:
        """Update an entry partially."""
        # Ensure it exists
        await self.get_knowledge(ik_id)

        update_dict = data.model_dump(exclude_unset=True)
        updated = await self._repo.update(ik_id, **update_dict)
        if not updated:
            raise NotFoundException(
                f"Failed to update. Incident knowledge entry '{ik_id}' not found.",
                context={"incident_knowledge_id": ik_id},
            )
        return updated

    async def delete_knowledge(self, ik_id: str) -> None:
        """Delete an entry."""
        # Ensure it exists
        await self.get_knowledge(ik_id)
        await self._repo.delete(ik_id)
