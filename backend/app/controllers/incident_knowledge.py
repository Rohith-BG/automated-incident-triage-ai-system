"""
Incident knowledge controller — HTTP formatting and response conversion for SRE knowledge.
"""

import logging
from typing import Optional

from ..schemas.incident_knowledge import (
    CreateIncidentKnowledgeRequest,
    IncidentKnowledgeListResponse,
    IncidentKnowledgeResponse,
    UpdateIncidentKnowledgeRequest,
)
from ..services.incident_knowledge import IncidentKnowledgeService

logger = logging.getLogger(__name__)


class IncidentKnowledgeController:
    """HTTP transport layer helper for IncidentKnowledge endpoints."""

    def __init__(self, service: IncidentKnowledgeService) -> None:
        """Initialise with the service."""
        self._service = service

    async def create_knowledge(
        self,
        created_by: str,
        payload: CreateIncidentKnowledgeRequest,
    ) -> IncidentKnowledgeResponse:
        """Process knowledge creation."""
        ik = await self._service.create_knowledge(created_by, payload)
        return IncidentKnowledgeResponse.model_validate(ik)

    async def get_knowledge(self, ik_id: str) -> IncidentKnowledgeResponse:
        """Process knowledge detail retrieval."""
        ik = await self._service.get_knowledge(ik_id)
        return IncidentKnowledgeResponse.model_validate(ik)

    async def list_knowledge(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        service_id: Optional[str] = None,
    ) -> IncidentKnowledgeListResponse:
        """Process paginated list retrieval."""
        items, next_cursor, has_more = await self._service.list_knowledge(
            limit=limit,
            cursor=cursor,
            service_id=service_id,
        )
        return IncidentKnowledgeListResponse(
            items=[IncidentKnowledgeResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
            has_more=has_more,
            limit=limit,
        )

    async def update_knowledge(
        self,
        ik_id: str,
        payload: UpdateIncidentKnowledgeRequest,
    ) -> IncidentKnowledgeResponse:
        """Process knowledge partial update."""
        updated = await self._service.update_knowledge(ik_id, payload)
        return IncidentKnowledgeResponse.model_validate(updated)

    async def delete_knowledge(self, ik_id: str) -> None:
        """Process knowledge deletion."""
        await self._service.delete_knowledge(ik_id)
