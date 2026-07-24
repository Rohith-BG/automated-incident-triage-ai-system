"""Integration tests for incident resolution endpoints."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.enums import IncidentStatus, UserRole
from backend.app.main import app
from backend.app.models.incident import Incident
from backend.app.models.incident_knowledge import IncidentKnowledge
from backend.app.models.user import User

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


async def get_token_and_user_for_role(email: str, role: UserRole) -> tuple[str, User]:
    """Register, promote in DB, login, and return access token and user object."""
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": f"{role.value.capitalize()} User",
        },
    )

    # Promote role
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalar_one()
        user.role = role.value
        await session.commit()
        # Fetch fresh copy
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalar_one()

    login_resp = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )
    return login_resp.json()["access_token"], user


@pytest.mark.asyncio
async def test_resolve_incident_route() -> None:
    """POST /incidents/{incident_id}/resolution resolves an incident and sets status."""
    token, user = await get_token_and_user_for_role("sre@triage.ai", UserRole.SRE)

    # 1. Create a dummy incident in database
    async with AsyncSessionLocal() as session:
        inc = Incident(
            service_id="payment-service",
            status=IncidentStatus.INVESTIGATING.value,
        )
        session.add(inc)

        # Create incident knowledge to link to
        ik = IncidentKnowledge(
            title="Stripe Timeout Playbook",
            applies_to_services=["payment-service"],
            applies_to_error_types=["stripe_timeout"],
            symptoms="500 errors",
            root_cause_pattern="gateway fail",
            immediate_steps="restart",
            permanent_fix="fix",
            owner_team="payments-team",
            created_by="admin@triage.ai",
        )
        session.add(ik)
        await session.commit()
        await session.refresh(inc)
        await session.refresh(ik)
        inc_id = inc.id
        ik_id = ik.id

    # 2. Call resolution endpoint
    payload = {
        "what_was_root_cause": "Stripe webhook failed to respond within 5 seconds due to a network glitch.",
        "what_fixed_it": "Manually re-queued the payment transaction from SRE panel.",
        "time_to_resolve_min": 10,
        "should_update_incident_knowledge": True,
        "incident_knowledge_id": ik_id,
        "notes": "Stripe team confirmed a transient routing issue on their side.",
    }
    resp = client.post(
        f"/incidents/{inc_id}/resolution",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == inc_id
    assert data["status"] == IncidentStatus.RESOLVED.value
    assert data["resolution"] is not None
    assert data["resolution"]["what_was_root_cause"] == payload["what_was_root_cause"]
    assert data["resolution"]["incident_knowledge_id"] == ik_id

    # 3. Retrieve incident details to confirm resolution maps properly
    get_resp = client.get(
        f"/incidents/{inc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["resolution"] is not None
    assert detail["resolution"]["resolved_by"] == user.id
