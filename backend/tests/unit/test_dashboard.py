"""Unit tests for the dashboard summary repository queries and service."""

import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.database import Base
from backend.app.enums import IncidentStatus
from backend.app.models.incident import Incident
from backend.app.repositories.incident import IncidentRepository
from backend.app.schemas.dashboard import DashboardSummaryResponse
from backend.app.services.dashboard import DashboardService

ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:", echo=False
)
TestSession = async_sessionmaker(
    bind=ENGINE, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create and tear down tables for every test."""
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    """Provide a fresh async session per test."""
    async with TestSession() as sess:
        yield sess


@pytest_asyncio.fixture
async def repo(session: AsyncSession):
    """Provide an IncidentRepository bound to the test session."""
    return IncidentRepository(session=session)


def _utc_now_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_count_active_counts_only_active(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """count_active() ignores resolved/completed incidents."""
    inc1 = await repo.create("cart-service")
    await repo.create("payment-service")
    await repo.update_status(inc1.id, IncidentStatus.COMPLETED)
    await session.commit()

    assert await repo.count_active() == 1


@pytest.mark.asyncio
async def test_count_resolved_since(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """count_resolved_since() counts only resolved incidents after start."""
    inc1 = await repo.create("cart-service")
    inc2 = await repo.create("payment-service")
    await repo.update_status(inc1.id, IncidentStatus.RESOLVED)
    await repo.update_status(inc2.id, IncidentStatus.ROOT_CAUSE_IDENTIFIED)
    await session.commit()

    assert await repo.count_resolved_since(_utc_now_naive() - datetime.timedelta(days=1)) == 1


@pytest.mark.asyncio
async def test_count_active_by_service_groups(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """count_active_by_service() groups active incidents per service."""
    inc1 = await repo.create("cart-service")
    await repo.create("cart-service")
    await repo.create("payment-service")
    await repo.update_status(inc1.id, IncidentStatus.RESOLVED)
    await session.commit()

    by_service = await repo.count_active_by_service()
    assert by_service["cart-service"] == 1
    assert by_service["payment-service"] == 1


class FakeIncidentRepository:
    """Deterministic stand-in for IncidentRepository."""

    def __init__(
        self,
        active_count: int,
        resolved_since: int,
        active_by_service: dict[str, int],
    ) -> None:
        self._active_count = active_count
        self._resolved_since = resolved_since
        self._active_by_service = active_by_service

    async def count_active(self) -> int:
        return self._active_count

    async def count_resolved_since(self, start: datetime.datetime) -> int:
        return self._resolved_since

    async def count_active_by_service(self) -> dict[str, int]:
        return self._active_by_service


@pytest.mark.asyncio
async def test_dashboard_service_classifies_service_health() -> None:
    """DashboardService classifies healthy/degraded/critical per active count."""
    fake = FakeIncidentRepository(
        active_count=4,
        resolved_since=2,
        active_by_service={
            "cart-service": 2,
            "payment-service": 1,
        },
    )
    service = DashboardService(incident_repository=fake)

    summary = await service.get_summary()

    assert isinstance(summary, DashboardSummaryResponse)
    assert summary.incident_summary.active == 4
    assert summary.incident_summary.resolved_today == 2
    # 11 services in the catalog fixture; cart degraded→critical, payment→degraded.
    assert summary.service_health.healthy == 9
    assert summary.service_health.degraded == 1
    assert summary.service_health.critical == 1
    assert summary.service_health.total == 11
