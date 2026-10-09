"""
Incident repository — all incident-related database access.

No business logic here. Only SQL queries and model persistence.
The service layer calls these methods and applies business rules.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import IncidentStatus
from ..models.incident import Alert, Incident, RootCauseReportModel

logger = logging.getLogger(__name__)


class IncidentRepository:
    """Data-access layer for Incident, Alert, and RootCauseReport."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session.

        Args:
            session: Injected via FastAPI Depends(get_db).
        """
        self._session = session

    async def create(self, service_id: str) -> Incident:
        """Create a new incident in INVESTIGATING status.

        Args:
            service_id: Service that raised the alert.

        Returns:
            The newly created Incident (flushed, ID populated).
        """
        incident = Incident(
            service_id=service_id,
            status=IncidentStatus.INVESTIGATING,
        )
        self._session.add(incident)
        await self._session.flush()
        return incident

    async def get_by_id(
        self, incident_id: str
    ) -> Optional[Incident]:
        """Fetch an incident by primary key with eager-loaded relations.

        Args:
            incident_id: UUID string.

        Returns:
            Incident or None if not found.
        """
        stmt = select(Incident).where(Incident.id == incident_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_active_by_service(
        self, service_id: str
    ) -> Optional[Incident]:
        """Find an active incident for a given service.

        Active means the status is in IncidentStatus.active_statuses().
        Used for status-driven alert deduplication (Rule 13).

        Args:
            service_id: Service to check.

        Returns:
            Most recent active Incident, or None.
        """
        active = IncidentStatus.active_statuses()
        stmt = (
            select(Incident)
            .where(
                Incident.service_id == service_id,
                Incident.status.in_(
                    [s.value for s in active]
                ),
            )
            .order_by(Incident.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ── Cursor helpers ────────────────────────────────────

    @staticmethod
    def encode_cursor(incident: Incident) -> str:
        """Encode an incident's position as an opaque cursor.

        Format: base64(created_at_iso|id). Clients must
        treat this as an opaque string.
        """
        import base64

        raw = f"{incident.created_at.isoformat()}|{incident.id}"
        return base64.urlsafe_b64encode(
            raw.encode()
        ).decode()

    @staticmethod
    def decode_cursor(
        cursor: str,
    ) -> tuple[datetime, str]:
        """Decode an opaque cursor into (created_at, id).

        Raises:
            ValueError: If the cursor is malformed.
        """
        import base64

        try:
            raw = base64.urlsafe_b64decode(
                cursor.encode()
            ).decode()
            ts_str, inc_id = raw.rsplit("|", 1)
            ts = datetime.fromisoformat(ts_str)
            return ts, inc_id
        except Exception as exc:
            raise ValueError(
                f"Invalid pagination cursor: {cursor}"
            ) from exc

    # ── List with cursor pagination ──────────────────────

    async def list_all(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        service_id: Optional[str] = None,
        status: Optional[IncidentStatus] = None,
    ) -> tuple[list[Incident], Optional[str], bool]:
        """Return a cursor-paginated, filtered list of incidents.

        Fetches ``limit + 1`` rows to determine whether more
        pages exist, avoiding a separate COUNT query.

        Args:
            limit: Max items per page.
            cursor: Opaque cursor from a previous response.
            service_id: Optional filter by service.
            status: Optional filter by status.

        Returns:
            Tuple of (incidents, next_cursor, has_more).
            next_cursor is None when no further pages exist.
        """
        from sqlalchemy import or_, and_, tuple_

        base = select(Incident)

        if service_id:
            base = base.where(
                Incident.service_id == service_id
            )
        if status:
            base = base.where(
                Incident.status == status.value
            )

        # Apply cursor filter (seek past the cursor position)
        if cursor:
            cursor_ts, cursor_id = self.decode_cursor(cursor)
            base = base.where(
                or_(
                    Incident.created_at < cursor_ts,
                    and_(
                        Incident.created_at == cursor_ts,
                        Incident.id < cursor_id,
                    ),
                )
            )

        # Fetch one extra row to detect has_more
        stmt = (
            base.order_by(
                Incident.created_at.desc(),
                Incident.id.desc(),
            )
            .limit(limit + 1)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        incidents = rows[:limit]

        next_cursor = None
        if has_more and incidents:
            next_cursor = self.encode_cursor(incidents[-1])

        return incidents, next_cursor, has_more

    # ── Aggregate counts ────────────────────────────────

    async def count_active(self) -> int:
        """Count incidents currently in an active status.

        Active means the status is in IncidentStatus.active_statuses()
        (INVESTIGATING or ROOT_CAUSE_IDENTIFIED).

        Returns:
            Number of active incidents.
        """
        stmt = select(func.count()).select_from(Incident).where(
            Incident.status.in_(
                [s.value for s in IncidentStatus.active_statuses()]
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_resolved_since(self, start: datetime) -> int:
        """Count incidents resolved or completed after ``start``.

        Resolved means the status is RESOLVED or COMPLETED and the
        incident was last updated on or after ``start``.

        Args:
            start: Lower bound (UTC, timezone-naive) for ``updated_at``.

        Returns:
            Number of resolved/completed incidents since ``start``.
        """
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.status.in_(
                    [
                        IncidentStatus.RESOLVED.value,
                        IncidentStatus.COMPLETED.value,
                    ]
                ),
                Incident.updated_at >= start,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_active_by_service(self) -> dict[str, int]:
        """Count active incidents grouped by service.

        Returns:
            Mapping of ``service_id`` to its number of active incidents.
        """
        stmt = (
            select(
                Incident.service_id,
                func.count().label("count"),
            )
            .where(
                Incident.status.in_(
                    [s.value for s in IncidentStatus.active_statuses()]
                )
            )
            .group_by(Incident.service_id)
        )
        result = await self._session.execute(stmt)
        return {
            service_id: int(count)
            for service_id, count in result.all()
        }

    async def update_status(
        self,
        incident_id: str,
        status: IncidentStatus,
    ) -> Optional[Incident]:
        """Update an incident's status and timestamp.

        Args:
            incident_id: Incident to update.
            status: New status value.

        Returns:
            Updated Incident, or None if not found.
        """
        stmt = (
            update(Incident)
            .where(Incident.id == incident_id)
            .values(
                status=status.value,
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return await self.get_by_id(incident_id)

    async def attach_alert(
        self,
        incident_id: str,
        alert_message: str,
    ) -> Alert:
        """Create and attach an alert to an existing incident.

        Args:
            incident_id: Incident to attach to.
            alert_message: Alert payload text.

        Returns:
            The newly created Alert.
        """
        alert = Alert(
            incident_id=incident_id,
            alert_message=alert_message,
        )
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def save_report(
        self,
        incident_id: str,
        root_cause: str,
        affected_services: list[str],
        raw_logs: dict | None = None,
        raw_metrics: dict | None = None,
        observability_analysis: str = "",
        code_diffs: dict | None = None,
        past_resolutions: list | None = None,
        remediation_steps: list[str] | None = None,
        confidence_score: float = 0.0,
        uncertainty: str = "",
    ) -> RootCauseReportModel:
        """Persist a root-cause report for an incident.

        Idempotent: ``root_cause_reports.incident_id`` is UNIQUE, so a
        re-triggered investigation updates the existing row rather than
        raising an IntegrityError. An IntegrityError here would abort the
        surrounding transaction and leave the incident in INVESTIGATING.

        Args:
            incident_id: Incident this report belongs to.
            root_cause: Diagnosis text.
            affected_services: List of affected service IDs.
            raw_logs: Raw log/trace MCP data per service.
            raw_metrics: Raw metric/anomaly MCP data per service.
            observability_analysis: LLM-interpreted observability summary.
            code_diffs: Commit/diff data per service.
            past_resolutions: Matching prior resolutions (empty if none).
            remediation_steps: Actionable steps.
            confidence_score: 0.0-1.0 confidence.
            uncertainty: Known evidence gaps.

        Returns:
            The created or updated RootCauseReportModel.
        """
        report = await self.get_report(incident_id)
        if report is not None:
            report.root_cause = root_cause
            report.affected_services = affected_services
            report.raw_logs = raw_logs or {}
            report.raw_metrics = raw_metrics or {}
            report.observability_analysis = observability_analysis
            report.code_diffs = code_diffs or {}
            report.past_resolutions = past_resolutions or []
            report.remediation_steps = remediation_steps or []
            report.confidence_score = confidence_score
            report.uncertainty = uncertainty
            self._session.add(report)
            await self._session.flush()
            return report

        report = RootCauseReportModel(
            incident_id=incident_id,
            root_cause=root_cause,
            affected_services=affected_services,
            raw_logs=raw_logs or {},
            raw_metrics=raw_metrics or {},
            observability_analysis=observability_analysis,
            code_diffs=code_diffs or {},
            past_resolutions=past_resolutions or [],
            remediation_steps=remediation_steps or [],
            confidence_score=confidence_score,
            uncertainty=uncertainty,
        )
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_report(
        self, incident_id: str
    ) -> Optional[RootCauseReportModel]:
        """Fetch the report row for an incident, if one exists.

        Args:
            incident_id: Incident whose report to fetch.

        Returns:
            The RootCauseReportModel, or None if absent.
        """
        stmt = select(RootCauseReportModel).where(
            RootCauseReportModel.incident_id == incident_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()
