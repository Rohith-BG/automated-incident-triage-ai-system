"""Unit tests for IncidentRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.database import Base
from backend.app.enums import IncidentStatus
from backend.app.models.incident import (
    Alert,
    Incident,
    RootCauseReportModel,
)
from backend.app.repositories.incident import IncidentRepository

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


@pytest.mark.asyncio
async def test_create_incident(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """create() returns an incident in INVESTIGATING status."""
    incident = await repo.create("cart-service")
    await session.commit()

    assert incident.id is not None
    assert incident.service_id == "cart-service"
    assert incident.status == IncidentStatus.INVESTIGATING


@pytest.mark.asyncio
async def test_get_by_id(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """get_by_id() retrieves an existing incident."""
    incident = await repo.create("cart-service")
    await session.commit()

    fetched = await repo.get_by_id(incident.id)
    assert fetched is not None
    assert fetched.id == incident.id


@pytest.mark.asyncio
async def test_get_by_id_not_found(
    repo: IncidentRepository,
) -> None:
    """get_by_id() returns None for unknown IDs."""
    result = await repo.get_by_id("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_find_active_by_service(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """find_active_by_service() finds investigating incidents."""
    await repo.create("cart-service")
    await session.commit()

    active = await repo.find_active_by_service("cart-service")
    assert active is not None
    assert active.service_id == "cart-service"
    assert active.status == IncidentStatus.INVESTIGATING


@pytest.mark.asyncio
async def test_find_active_by_service_ignores_completed(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """find_active_by_service() ignores completed incidents."""
    incident = await repo.create("cart-service")
    await repo.update_status(incident.id, IncidentStatus.COMPLETED)
    await session.commit()

    active = await repo.find_active_by_service("cart-service")
    assert active is None


@pytest.mark.asyncio
async def test_find_active_by_service_wrong_service(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """find_active_by_service() returns None for different service."""
    await repo.create("cart-service")
    await session.commit()

    active = await repo.find_active_by_service("payment-service")
    assert active is None


@pytest.mark.asyncio
async def test_attach_alert(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """attach_alert() creates an alert linked to the incident."""
    incident = await repo.create("cart-service")
    alert = await repo.attach_alert(
        incident.id, "Redis connection refused"
    )
    await session.commit()

    assert alert.id is not None
    assert alert.incident_id == incident.id
    assert alert.alert_message == "Redis connection refused"


@pytest.mark.asyncio
async def test_save_report(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """save_report() persists a root-cause report with uncertainty and model_used."""
    incident = await repo.create("cart-service")
    report = await repo.save_report(
        incident_id=incident.id,
        root_cause="Redis crashed",
        evidence_summary="ECONNREFUSED in logs",
        affected_services=["cart-service", "checkout-service"],
        remediation_steps=["Restart Redis"],
        confidence_score=0.92,
        uncertainty="No deploy logs available",
        model_used="gemini-2.5-flash",
    )
    await session.commit()

    assert report.id is not None
    assert report.incident_id == incident.id
    assert report.confidence_score == 0.92
    assert report.affected_services == [
        "cart-service",
        "checkout-service",
    ]
    assert report.uncertainty == "No deploy logs available"
    assert report.model_used == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_update_status(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """update_status() transitions the incident status."""
    incident = await repo.create("cart-service")
    await session.commit()

    updated = await repo.update_status(
        incident.id, IncidentStatus.COMPLETED
    )
    await session.commit()

    assert updated is not None
    assert updated.status == IncidentStatus.COMPLETED


@pytest.mark.asyncio
async def test_list_all_cursor_pagination(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """list_all() returns cursor-paginated results with has_more."""
    for i in range(5):
        await repo.create(f"service-{i}")
    await session.commit()

    # First page
    incidents, next_cursor, has_more = await repo.list_all(
        limit=3
    )
    assert len(incidents) == 3
    assert has_more is True
    assert next_cursor is not None

    # Second page via cursor
    incidents2, next_cursor2, has_more2 = await repo.list_all(
        limit=3, cursor=next_cursor
    )
    assert len(incidents2) == 2
    assert has_more2 is False
    assert next_cursor2 is None

    # No overlap between pages
    page1_ids = {inc.id for inc in incidents}
    page2_ids = {inc.id for inc in incidents2}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_list_all_filter_by_service(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """list_all() filters by service_id."""
    await repo.create("cart-service")
    await repo.create("payment-service")
    await repo.create("cart-service")
    await session.commit()

    incidents, _, _ = await repo.list_all(
        service_id="cart-service"
    )
    assert len(incidents) == 2
    assert all(
        inc.service_id == "cart-service" for inc in incidents
    )


@pytest.mark.asyncio
async def test_list_all_filter_by_status(
    repo: IncidentRepository, session: AsyncSession
) -> None:
    """list_all() filters by status."""
    inc1 = await repo.create("cart-service")
    await repo.create("payment-service")
    await repo.update_status(inc1.id, IncidentStatus.COMPLETED)
    await session.commit()

    incidents, _, _ = await repo.list_all(
        status=IncidentStatus.COMPLETED
    )
    assert len(incidents) == 1
    assert incidents[0].status == IncidentStatus.COMPLETED
