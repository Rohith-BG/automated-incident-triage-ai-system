"""Integration tests for authentication and authorization routes."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi import APIRouter, Depends

from backend.app.core.database import Base, engine, AsyncSessionLocal
from backend.app.enums import UserRole
from backend.app.main import app
from backend.app.models.user import User
from backend.app.dependencies import require_role

client = TestClient(app)

# ── Temporary testing routes ──────────────────────────────

test_router = APIRouter(prefix="/auth-test", tags=["auth-test"])


@test_router.get("/admin-only")
async def admin_only_route(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict[str, str]:
    return {"message": f"Hello Admin {current_user.full_name}"}


@test_router.get("/sre-only")
async def sre_only_route(
    current_user: User = Depends(require_role(UserRole.SRE)),
) -> dict[str, str]:
    return {"message": f"Hello SRE {current_user.full_name}"}


# Include testing routes
app.include_router(test_router)


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate tables for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_route_success() -> None:
    """POST /auth/register creates a user with default role team_member."""
    resp = client.post(
        "/auth/register",
        json={
            "email": "developer@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "developer@example.com"
    assert data["full_name"] == "Dev User"
    assert data["role"] == UserRole.TEAM_MEMBER.value
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_register_route_duplicate_email() -> None:
    """POST /auth/register returns 409 for duplicate emails."""
    payload = {
        "email": "developer@example.com",
        "password": "securepassword123",
        "full_name": "Dev User",
    }
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/register", json=payload)

    assert resp.status_code == 409
    assert "already registered" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_login_route_success_sets_refresh_cookie() -> None:
    """POST /auth/login returns access token and sets HTTP-only refresh cookie."""
    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
    )

    resp = client.post(
        "/auth/login",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify refresh token cookie is set
    assert "refresh_token" in resp.cookies
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "path=/auth" in set_cookie.lower()


@pytest.mark.asyncio
async def test_login_route_invalid_credentials() -> None:
    """POST /auth/login returns 401 for bad passwords or emails."""
    resp = client.post(
        "/auth/login",
        json={
            "email": "missing@example.com",
            "password": "wrongpassword",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_route_success() -> None:
    """POST /auth/refresh rotates access token and refresh cookie."""
    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
    )

    login_resp = client.post(
        "/auth/login",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
        },
    )
    assert login_resp.status_code == 200
    old_cookie = login_resp.cookies["refresh_token"]

    # Request rotation
    client.cookies.set("refresh_token", old_cookie, path="/auth")
    refresh_resp = client.post("/auth/refresh")

    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    assert "refresh_token" in refresh_resp.cookies
    assert refresh_resp.cookies["refresh_token"] != old_cookie


@pytest.mark.asyncio
async def test_logout_clears_cookie() -> None:
    """POST /auth/logout deletes the refresh cookie."""
    client.cookies.set("refresh_token", "some-token-value", path="/auth")
    resp = client.post("/auth/logout")

    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out successfully."
    # Cookie should be deleted/expired (empty or missing)
    cookie = resp.cookies.get("refresh_token")
    assert cookie is None or cookie == ""


@pytest.mark.asyncio
async def test_me_route_requires_auth() -> None:
    """GET /auth/me returns 401 without bearer token."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_route_success() -> None:
    """GET /auth/me returns user profile when authenticated."""
    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
    )

    login_resp = client.post(
        "/auth/login",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
        },
    )
    token = login_resp.json()["access_token"]

    resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "dev@example.com"
    assert data["full_name"] == "Dev User"


@pytest.mark.asyncio
async def test_rbac_restrictions() -> None:
    """Test role-based access restrictions on test routes."""
    # Register default user (developer/team_member)
    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
    )
    login_resp = client.post(
        "/auth/login",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
        },
    )
    token = login_resp.json()["access_token"]

    # Dev/team_member cannot access SRE or Admin route
    resp = client.get(
        "/auth-test/sre-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    resp = client.get(
        "/auth-test/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    # Promote user manually in DB to test SRE access
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.email == "dev@example.com"))
        user = res.scalar_one()
        user.role = UserRole.SRE.value
        await session.commit()

    # SRE can now access SRE route, but not Admin route
    resp = client.get(
        "/auth-test/sre-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "Hello SRE" in resp.json()["message"]

    resp = client.get(
        "/auth-test/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
