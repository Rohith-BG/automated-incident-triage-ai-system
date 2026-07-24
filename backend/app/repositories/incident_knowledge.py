"""
Incident knowledge repository — database access for SRE runbooks / playbooks.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.incident_knowledge import IncidentKnowledge
from ..models.incident import generate_uuid

logger = logging.getLogger(__name__)


class IncidentKnowledgeRepository:
    """Data-access layer for IncidentKnowledge."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session."""
        self._session = session

    async def create(
        self,
        *,
        title: str,
        applies_to_services: list[str],
        applies_to_error_types: list[str],
        symptoms: str,
        root_cause_pattern: str,
        immediate_steps: str,
        permanent_fix: str,
        escalate_if: str = "",
        owner_team: str,
        created_by: str,
    ) -> IncidentKnowledge:
        """Create and persist a new SRE knowledge entry."""
        ik = IncidentKnowledge(
            title=title,
            applies_to_services=applies_to_services,
            applies_to_error_types=applies_to_error_types,
            symptoms=symptoms,
            root_cause_pattern=root_cause_pattern,
            immediate_steps=immediate_steps,
            permanent_fix=permanent_fix,
            escalate_if=escalate_if,
            owner_team=owner_team,
            created_by=created_by,
        )
        self._session.add(ik)
        await self._session.flush()
        await self._session.refresh(ik)
        logger.info("Created IncidentKnowledge entry '%s' (ID: %s)", title, ik.id)
        return ik

    async def get_by_id(self, ik_id: str) -> Optional[IncidentKnowledge]:
        """Fetch an entry by ID."""
        stmt = select(IncidentKnowledge).where(IncidentKnowledge.id == ik_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        service_id: Optional[str] = None,
    ) -> tuple[list[IncidentKnowledge], Optional[str], bool]:
        """Return a cursor-paginated list of SRE knowledge entries.

        Supports service filter. Ordered newest-first by created_at.
        """
        import base64

        # Select all and sort/filter
        # Using pagination cursor similar to incidents: base64(created_at_iso|id)
        stmt = select(IncidentKnowledge)
        result = await self._session.execute(stmt)
        all_items = list(result.scalars().all())

        # Python-side filtering to ensure JSON compatibility across SQLite/Postgres
        filtered = []
        for item in all_items:
            if service_id and service_id not in (item.applies_to_services or []):
                continue
            filtered.append(item)

        # Sort: newest first
        filtered.sort(key=lambda x: (x.created_at, x.id), reverse=True)

        # Seek past the cursor
        start_index = 0
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
                ts_str, cursor_id = decoded.rsplit("|", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                for idx, item in enumerate(filtered):
                    if item.created_at < cursor_ts or (item.created_at == cursor_ts and item.id < cursor_id):
                        start_index = idx
                        break
                else:
                    start_index = len(filtered)
            except Exception:
                raise ValueError(f"Invalid pagination cursor: {cursor}")

        page_items = filtered[start_index : start_index + limit + 1]
        has_more = len(page_items) > limit
        items = page_items[:limit]

        next_cursor = None
        if has_more and items:
            last_item = items[-1]
            raw_cursor = f"{last_item.created_at.isoformat()}|{last_item.id}"
            next_cursor = base64.urlsafe_b64encode(raw_cursor.encode()).decode()

        return items, next_cursor, has_more

    async def update(self, ik_id: str, **fields: Any) -> Optional[IncidentKnowledge]:
        """Update an entry partially."""
        if not fields:
            return await self.get_by_id(ik_id)

        # Ensure updated_at is updated
        fields["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

        stmt = (
            update(IncidentKnowledge)
            .where(IncidentKnowledge.id == ik_id)
            .values(**fields)
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return await self.get_by_id(ik_id)

    async def delete(self, ik_id: str) -> bool:
        """Delete an entry."""
        stmt = delete(IncidentKnowledge).where(IncidentKnowledge.id == ik_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return (result.rowcount or 0) > 0

    async def find_matching(
        self,
        service_id: str,
        error_type: Optional[str] = None,
        query_str: Optional[str] = None,
        limit: int = 5,
    ) -> list[IncidentKnowledge]:
        """Find matching knowledge entries based on service, error type, and query string.

        Queries JSON list columns safely.
        """
        stmt = select(IncidentKnowledge)
        result = await self._session.execute(stmt)
        all_items = list(result.scalars().all())

        filtered = []
        for item in all_items:
            # 1. Service check
            services = item.applies_to_services or []
            if service_id not in services:
                continue

            # 2. Optional error type check (overlap applies_to_error_types)
            if error_type:
                errors = item.applies_to_error_types or []
                if error_type not in errors:
                    continue

            # 3. Optional text search query
            if query_str:
                q = query_str.lower()
                title_match = q in item.title.lower()
                symptom_match = q in item.symptoms.lower()
                cause_match = q in item.root_cause_pattern.lower()
                if not (title_match or symptom_match or cause_match):
                    continue

            filtered.append(item)

        # Sort by creation date (newest first)
        filtered.sort(key=lambda x: (x.created_at, x.id), reverse=True)
        return filtered[:limit]
