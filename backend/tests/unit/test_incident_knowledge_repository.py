"""Unit tests for IncidentKnowledgeRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.incident_knowledge import IncidentKnowledge
from backend.app.repositories.incident_knowledge import IncidentKnowledgeRepository

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
    """Provide an IncidentKnowledgeRepository bound to the test session."""
    return IncidentKnowledgeRepository(session=session)


@pytest.mark.asyncio
async def test_create_knowledge(repo: IncidentKnowledgeRepository, session: AsyncSession) -> None:
    """create() successfully inserts a knowledge entry."""
    ik = await repo.create(
        title="Database connection timeout",
        applies_to_services=["payment-service", "inventory-service"],
        applies_to_error_types=["db_connection_timeout"],
        symptoms="High latency and 500 errors on payment endpoints.",
        root_cause_pattern="Database pool exhaustion due to slow queries.",
        immediate_steps="Restart DB pods or scale connections.",
        permanent_fix="Optimize queries and add index on transaction_id.",
        escalate_if="Timeout persists after pod restart.",
        owner_team="payments-team",
        created_by="admin@triage.ai",
    )
    await session.commit()

    assert ik.id is not None
    assert ik.title == "Database connection timeout"
    assert ik.applies_to_services == ["payment-service", "inventory-service"]
    assert ik.applies_to_error_types == ["db_connection_timeout"]
    assert ik.owner_team == "payments-team"


@pytest.mark.asyncio
async def test_get_by_id(repo: IncidentKnowledgeRepository, session: AsyncSession) -> None:
    """get_by_id() returns the correct entry or None."""
    ik = await repo.create(
        title="Redis down",
        applies_to_services=["cart-service"],
        applies_to_error_types=["redis_error"],
        symptoms="Symptom details",
        root_cause_pattern="Cause details",
        immediate_steps="Fix steps",
        permanent_fix="Remediation steps",
        owner_team="cart-team",
        created_by="admin@triage.ai",
    )
    await session.commit()

    fetched = await repo.get_by_id(ik.id)
    assert fetched is not None
    assert fetched.id == ik.id
    assert fetched.title == "Redis down"

    missing = await repo.get_by_id("unknown-id")
    assert missing is None


@pytest.mark.asyncio
async def test_update_and_delete(repo: IncidentKnowledgeRepository, session: AsyncSession) -> None:
    """update() and delete() work correctly."""
    ik = await repo.create(
        title="Stripe down",
        applies_to_services=["payment-service"],
        applies_to_error_types=["stripe_error"],
        symptoms="Symptom details",
        root_cause_pattern="Cause details",
        immediate_steps="Fix steps",
        permanent_fix="Remediation steps",
        owner_team="payments-team",
        created_by="admin@triage.ai",
    )
    await session.commit()

    updated = await repo.update(ik.id, title="Stripe API down")
    await session.commit()
    assert updated is not None
    assert updated.title == "Stripe API down"

    deleted = await repo.delete(ik.id)
    await session.commit()
    assert deleted is True

    fetched = await repo.get_by_id(ik.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_find_matching(repo: IncidentKnowledgeRepository, session: AsyncSession) -> None:
    """find_matching() filters correctly by service, error_type, and query string."""
    ik1 = await repo.create(
        title="Database connection timeout",
        applies_to_services=["payment-service", "inventory-service"],
        applies_to_error_types=["db_connection_timeout"],
        symptoms="High latency and 500 errors on payment endpoints.",
        root_cause_pattern="Database pool exhaustion due to slow queries.",
        immediate_steps="Restart DB pods or scale connections.",
        permanent_fix="Optimize queries and add index on transaction_id.",
        escalate_if="Timeout persists after pod restart.",
        owner_team="payments-team",
        created_by="admin@triage.ai",
    )
    ik2 = await repo.create(
        title="Stripe connection error",
        applies_to_services=["payment-service"],
        applies_to_error_types=["stripe_api_timeout"],
        symptoms="Stripe gateway timeout.",
        root_cause_pattern="External payment provider down.",
        immediate_steps="Check stripe status page.",
        permanent_fix="Implement circuit breaker.",
        owner_team="payments-team",
        created_by="admin@triage.ai",
    )
    await session.commit()

    # Match by service only
    matches = await repo.find_matching("inventory-service")
    assert len(matches) == 1
    assert matches[0].id == ik1.id

    # Match by service and error type
    matches = await repo.find_matching("payment-service", error_type="stripe_api_timeout")
    assert len(matches) == 1
    assert matches[0].id == ik2.id

    # Match by service and query substring
    matches = await repo.find_matching("payment-service", query_str="gateway")
    assert len(matches) == 1
    assert matches[0].id == ik2.id

    # No match for wrong service
    matches = await repo.find_matching("cart-service")
    assert len(matches) == 0
