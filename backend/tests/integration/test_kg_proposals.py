"""Integration tests for KG Proposal review, feedback, approval, and rejection workflow."""

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
async def test_kg_proposals_workflow() -> None:
    """Test listing proposals endpoint."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.get("/kg-proposals", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
