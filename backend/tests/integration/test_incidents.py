"""Integration tests for /incidents routes."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from agents.llm.base import LLMResponse
from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.enums import IncidentStatus
from backend.app.main import app
from backend.app.models.incident import Incident

client = TestClient(app)


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate tables for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def mock_llm_adapter():
    """Mock LLM globally so orchestrator runs don't hit real APIs."""
    mock_response = LLMResponse(
        content="""{
            "root_cause": "Redis crashed",
            "evidence_summary": "ECONNREFUSED in cart-service logs",
            "affected_services": ["cart-service"],
            "remediation_steps": ["Restart Redis container"],
            "confidence_score": 0.92
        }""",
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "total_tokens": 20,
        },
    )
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = mock_response
    with patch(
        "agents.orchestrator.graph.create_llm_adapter",
        return_value=mock_llm,
    ):
        yield mock_llm


# ── POST /incidents/ingest ───────────────────────────────


@pytest.mark.asyncio
async def test_ingest_creates_new_incident() -> None:
    """New alert creates a new incident and returns is_new=True."""
    resp = client.post(
        "/incidents/ingest",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis ECONNREFUSED",
        },
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["is_new"] is True
    assert data["status"] == IncidentStatus.INVESTIGATING
    assert data["incident_id"] is not None


@pytest.mark.asyncio
async def test_ingest_deduplicates_active_incident() -> None:
    """Second alert for same service attaches to existing incident."""
    # Create first
    resp1 = client.post(
        "/incidents/ingest",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis ECONNREFUSED",
        },
    )
    inc_id = resp1.json()["incident_id"]

    # After background task, incident is completed — create
    # a fresh investigating one manually
    async with AsyncSessionLocal() as session:
        active = Incident(
            service_id="payment-service",
            status=IncidentStatus.INVESTIGATING,
        )
        session.add(active)
        await session.commit()
        await session.refresh(active)
        active_id = active.id

    # Second alert for same service should dedup
    resp2 = client.post(
        "/incidents/ingest",
        json={
            "service_id": "payment-service",
            "alert_message": "Stripe 500 error",
        },
    )
    assert resp2.status_code == 202
    data2 = resp2.json()
    assert data2["is_new"] is False
    assert data2["incident_id"] == active_id


@pytest.mark.asyncio
async def test_ingest_triggers_orchestrator() -> None:
    """New incident triggers background investigation and saves report."""
    resp = client.post(
        "/incidents/ingest",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis ECONNREFUSED",
        },
    )
    inc_id = resp.json()["incident_id"]

    # TestClient runs background tasks synchronously
    async with AsyncSessionLocal() as session:
        stmt = select(Incident).where(Incident.id == inc_id)
        result = await session.execute(stmt)
        incident = result.scalars().first()
        assert incident is not None
        assert incident.status == IncidentStatus.COMPLETED
        assert incident.report is not None
        assert incident.report.root_cause == "Redis crashed"


# ── GET /incidents ───────────────────────────────────────


@pytest.mark.asyncio
async def test_list_incidents_empty() -> None:
    """Empty database returns zero items."""
    resp = client.get("/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_more"] is False
    assert data["items"] == []
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_incidents_cursor_pagination() -> None:
    """Cursor pagination chains through pages."""
    # Create 3 incidents
    for svc in ["svc-1", "svc-2", "svc-3"]:
        async with AsyncSessionLocal() as session:
            session.add(Incident(
                service_id=svc,
                status=IncidentStatus.INVESTIGATING,
            ))
            await session.commit()

    # First page: limit=2
    resp = client.get("/incidents?limit=2")
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["has_more"] is True
    assert data["next_cursor"] is not None

    # Second page via cursor
    cursor = data["next_cursor"]
    resp2 = client.get(f"/incidents?limit=2&cursor={cursor}")
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["has_more"] is False
    assert data2["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_incidents_filter_by_service() -> None:
    """service_id filter returns only matching incidents."""
    async with AsyncSessionLocal() as session:
        session.add(Incident(
            service_id="cart-service",
            status=IncidentStatus.INVESTIGATING,
        ))
        session.add(Incident(
            service_id="payment-service",
            status=IncidentStatus.INVESTIGATING,
        ))
        await session.commit()

    resp = client.get("/incidents?service_id=cart-service")
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["service_id"] == "cart-service"


@pytest.mark.asyncio
async def test_list_incidents_filter_by_status() -> None:
    """Status filter returns only matching incidents."""
    async with AsyncSessionLocal() as session:
        session.add(Incident(
            service_id="cart-service",
            status=IncidentStatus.INVESTIGATING,
        ))
        session.add(Incident(
            service_id="payment-service",
            status=IncidentStatus.COMPLETED,
        ))
        await session.commit()

    resp = client.get("/incidents?status=completed")
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "completed"


# ── GET /incidents/{id} ──────────────────────────────────


@pytest.mark.asyncio
async def test_get_incident_detail() -> None:
    """Returns full detail with alerts after ingestion."""
    resp = client.post(
        "/incidents/ingest",
        json={
            "service_id": "cart-service",
            "alert_message": "Redis ECONNREFUSED",
        },
    )
    inc_id = resp.json()["incident_id"]

    detail = client.get(f"/incidents/{inc_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == inc_id
    assert data["service_id"] == "cart-service"
    assert len(data["alerts"]) >= 1
    # Report should exist since TestClient runs bg tasks sync
    assert data["report"] is not None
    assert data["report"]["confidence_score"] == 0.92


@pytest.mark.asyncio
async def test_get_incident_not_found() -> None:
    """Returns 404 for unknown incident ID."""
    resp = client.get("/incidents/nonexistent-id")
    assert resp.status_code == 404
