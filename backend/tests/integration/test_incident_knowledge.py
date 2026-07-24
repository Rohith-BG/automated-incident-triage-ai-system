"""Integration tests for SRE incident knowledge (/incident-knowledge) endpoints."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.enums import UserRole
from backend.app.main import app
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


async def get_token_for_role(email: str, role: UserRole) -> str:
    """Register, promote in DB, login, and return access token."""
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

    login_resp = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )
    return login_resp.json()["access_token"]


@pytest.mark.asyncio
async def test_incident_knowledge_crud_permissions() -> None:
    """Validate CRUD operations and role-based permissions."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    sre_token = await get_token_for_role("sre@triage.ai", UserRole.SRE)

    # 1. Create a knowledge entry (Admin is authorized)
    payload = {
        "title": "Stripe API down",
        "applies_to_services": ["payment-service"],
        "applies_to_error_types": ["stripe_api_timeout"],
        "symptoms": "Stripe gateway timeout.",
        "root_cause_pattern": "External payment provider down.",
        "immediate_steps": "Check stripe status page.",
        "permanent_fix": "Implement circuit breaker.",
        "owner_team": "payments-team",
    }
    create_resp = client.post(
        "/incident-knowledge",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    ik_id = create_resp.json()["id"]
    assert create_resp.json()["title"] == "Stripe API down"

    # 2. SRE trying to create knowledge entry -> 403 Forbidden
    sre_create_resp = client.post(
        "/incident-knowledge",
        json=payload,
        headers={"Authorization": f"Bearer {sre_token}"},
    )
    assert sre_create_resp.status_code == 403

    # 3. Read knowledge list (Authorized for SRE and Admin)
    list_resp = client.get(
        "/incident-knowledge",
        headers={"Authorization": f"Bearer {sre_token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1

    # 4. Get knowledge detail
    detail_resp = client.get(
        f"/incident-knowledge/{ik_id}",
        headers={"Authorization": f"Bearer {sre_token}"},
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == ik_id

    # 5. Update knowledge entry (Admin is authorized)
    update_resp = client.put(
        f"/incident-knowledge/{ik_id}",
        json={"title": "Stripe API Webhook down"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Stripe API Webhook down"

    # SRE trying to update -> 403 Forbidden
    sre_update_resp = client.put(
        f"/incident-knowledge/{ik_id}",
        json={"title": "Fail Title"},
        headers={"Authorization": f"Bearer {sre_token}"},
    )
    assert sre_update_resp.status_code == 403

    # 6. Delete knowledge entry (Admin is authorized)
    # SRE trying to delete -> 403 Forbidden
    sre_delete_resp = client.delete(
        f"/incident-knowledge/{ik_id}",
        headers={"Authorization": f"Bearer {sre_token}"},
    )
    assert sre_delete_resp.status_code == 403

    # Admin delete -> 204 No Content
    delete_resp = client.delete(
        f"/incident-knowledge/{ik_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 204
