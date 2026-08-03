"""Integration tests for /onboarding REST API endpoints."""

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
async def test_discover_topology_endpoint() -> None:
    """POST /onboarding/discover registers topology and returns proposal ID."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "architecture_type": "microservice",
        "source_type": "inline",
        "owner_team_id": "platform-team",
        "services": [
            {
                "service_id": "test-cart-service",
                "repo": "demo/cart",
                "architecture_type": "microservice",
                "owner_team_id": "cart-team",
                "dependencies": ["redis-cart"],
            }
        ],
    }

    response = client.post(
        "/onboarding/discover",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["discovered_count"] == 1
    assert data["registered_count"] == 1
    assert data["proposal_id"] is not None
    assert "Generated Knowledge Graph proposal" in data["message"]


@pytest.mark.asyncio
async def test_onboarding_status_endpoint() -> None:
    """GET /onboarding/status returns onboarding platform status."""
    # Any authenticated user can view status
    user_token = await get_token_for_role("user@triage.ai", UserRole.TEAM_MEMBER)
    headers = {"Authorization": f"Bearer {user_token}"}

    response = client.get("/onboarding/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_registered_services" in data
    assert "pending_proposals_count" in data
    assert "active_services_count" in data
