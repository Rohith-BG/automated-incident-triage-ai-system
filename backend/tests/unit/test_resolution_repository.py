"""Unit tests for IncidentResolutionRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.incident import Incident
from backend.app.models.incident_knowledge import IncidentKnowledge
from backend.app.models.incident_resolution import IncidentResolution
from backend.app.models.user import User
from backend.app.repositories.incident_resolution import IncidentResolutionRepository

ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestSession = async_sessionmaker(bind=ENGINE, class_=AsyncSession, expire_on_commit=False)


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
    """Provide an IncidentResolutionRepository bound to the test session."""
    return IncidentResolutionRepository(session=session)


@pytest.mark.asyncio
async def test_create_and_get_resolution(
    repo: IncidentResolutionRepository, session: AsyncSession
) -> None:
    """create() and get_by_incident() work correctly."""
    # 1. Create a dummy User
    user = User(
        email="engineer@triage.ai",
        hashed_password="hash",
        full_name="Resolving Engineer",
        role="sre",
    )
    session.add(user)

    # 2. Create a dummy Incident
    incident = Incident(service_id="payment-service")
    session.add(incident)

    # 3. Create IncidentKnowledge
    ik = IncidentKnowledge(
        title="Payment gateway error",
        applies_to_services=["payment-service"],
        applies_to_error_types=["gateway_error"],
        symptoms="500 errors",
        root_cause_pattern="gateway timeout",
        immediate_steps="steps",
        permanent_fix="fix",
        owner_team="payments-team",
        created_by="admin@triage.ai",
    )
    session.add(ik)
    await session.commit()

    # 4. Create resolution
    res = await repo.create(
        incident_id=incident.id,
        resolved_by=user.id,
        what_was_root_cause="Stripe API gateway timed out during webhook processing.",
        what_fixed_it="Re-routed network request and restarted checkout worker.",
        time_to_resolve_min=15,
        should_update_incident_knowledge=False,
        incident_knowledge_id=ik.id,
        notes="All systems recovered immediately.",
    )
    await session.commit()

    assert res.id is not None
    assert res.incident_id == incident.id
    assert res.resolved_by == user.id
    assert res.incident_knowledge_id == ik.id

    # 5. Fetch resolution by incident ID
    fetched = await repo.get_by_incident(incident.id)
    assert fetched is not None
    assert fetched.id == res.id
    assert fetched.what_was_root_cause == "Stripe API gateway timed out during webhook processing."
    assert fetched.what_fixed_it == "Re-routed network request and restarted checkout worker."
