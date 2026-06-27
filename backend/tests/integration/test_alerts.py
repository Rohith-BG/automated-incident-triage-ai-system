import asyncio
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

from agents.orchestrator import InvestigationState
from agents.llm.base import LLMResponse
from backend.app.main import app
from backend.app.models.incident import Incident, Alert, RootCauseReportModel
from backend.app.core.database import Base, engine, AsyncSessionLocal

client = TestClient(app)


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Fixture to drop and recreate database tables before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def mock_llm_adapter():
    """Fixture to mock LLM calls globally for all tests in this module."""
    mock_llm_response = LLMResponse(
        content="""{
            "root_cause": "Mocked Redis failure.",
            "evidence_summary": "Errors in cart-service log.",
            "affected_services": ["cart-service"],
            "remediation_steps": ["Restart Redis container."],
            "confidence_score": 0.95
        }""",
        usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    )
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = mock_llm_response
    with patch("agents.orchestrator.graph.create_llm_adapter", return_value=mock_llm):
        yield mock_llm


@pytest.mark.asyncio
async def test_alert_webhook_creates_new_incident() -> None:
    # 1. Post a new alert
    response = client.post(
        "/alerts/webhook",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis connection lost: ECONNREFUSED",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "investigating"
    assert data["is_duplicate"] is False
    incident_id = data["incident_id"]
    assert incident_id is not None

    # 2. Verify it's created and processed in the DB
    # Note: TestClient runs background tasks synchronously, so status will be 'completed'
    async with AsyncSessionLocal() as session:
        stmt = select(Incident).where(Incident.id == incident_id)
        result = await session.execute(stmt)
        incident = result.scalars().first()
        assert incident is not None
        assert incident.service_id == "cart-service"
        assert incident.status == "completed"
        assert len(incident.alerts) == 1
        assert incident.alerts[0].alert_message == "Redis connection lost: ECONNREFUSED"


@pytest.mark.asyncio
async def test_alert_webhook_deduplicates_active_incident() -> None:
    # 1. Manually insert an active incident into the DB
    async with AsyncSessionLocal() as session:
        active_incident = Incident(
            service_id="cart-service",
            status="investigating",
        )
        session.add(active_incident)
        await session.commit()
        await session.refresh(active_incident)
        inc1_id = active_incident.id

    # 2. Post alert for the same service (should deduplicate)
    resp2 = client.post(
        "/alerts/webhook",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis read timeout error",
        },
    )

    assert resp2.status_code == 202
    data2 = resp2.json()
    assert data2["success"] is True
    assert data2["incident_id"] == inc1_id
    assert data2["is_duplicate"] is True

    # 3. Verify alerts in DB are grouped under the active incident
    async with AsyncSessionLocal() as session:
        stmt = select(Incident).where(Incident.id == inc1_id)
        result = await session.execute(stmt)
        incident = result.scalars().first()
        assert incident is not None
        assert len(incident.alerts) == 1
        assert incident.alerts[0].alert_message == "Redis read timeout error"


@pytest.mark.asyncio
async def test_alert_webhook_triggers_orchestrator() -> None:
    # Post alert
    response = client.post(
        "/alerts/webhook",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis connection lost: ECONNREFUSED",
        },
    )
    assert response.status_code == 202
    incident_id = response.json()["incident_id"]

    # Verify background task results
    async with AsyncSessionLocal() as session:
        stmt = select(Incident).where(Incident.id == incident_id)
        result = await session.execute(stmt)
        incident = result.scalars().first()
        assert incident is not None
        assert incident.status == "completed"
        assert incident.report is not None
        assert incident.report.root_cause == "Mocked Redis failure."
        assert incident.report.confidence_score == 0.95
