"""Integration tests for authentication and authorization routes."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi import APIRouter, Depends

from backend.app.core.database import Base, engine, AsyncSessionLocal
from backend.app.core.security import hash_password
from backend.app.enums import UserRole
from backend.app.main import app
from backend.app.models.user import User
from backend.app.dependencies import require_role
from backend.app.repositories.user import UserRepository

client = TestClient(app)

# ── Temporary testing routes ──────────────────────────────

test_router = APIRouter(prefix="/auth-test", tags=["auth-test"])


@test_router.get("/admin-only")
async def admin_only_route(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict[str, str]:
    return {"message": f"Hello Admin {current_user.full_name}"}


@test_router.get("/developer-only")
async def developer_only_route(
    current_user: User = Depends(require_role(UserRole.DEVELOPER)),
) -> dict[str, str]:
    return {"message": f"Hello Developer {current_user.full_name}"}


# Include testing routes
app.include_router(test_router)


async def _seed_admin(
    email: str = "admin@example.com",
    password: str = "securepassword123",
    full_name: str = "Admin User",
) -> None:
    """Insert an admin user directly via the repository."""
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session=session)
        await repo.create(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.ADMIN,
        )
        await session.commit()


def _login(email: str, password: str) -> str:
    """Login and return the access token."""
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate tables for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Registration tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_register_without_auth_returns_401() -> None:
    """POST /auth/register without token returns 401."""
    resp = client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "securepassword123",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_with_developer_token_returns_403() -> None:
    """POST /auth/register with a developer token returns 403."""
    await _seed_admin()

    # Admin creates a developer
    admin_token = _login("admin@example.com", "securepassword123")
    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Developer tries to register another user
    dev_token = _login("dev@example.com", "securepassword123")
    resp = client.post(
        "/auth/register",
        json={
            "email": "another@example.com",
            "password": "securepassword123",
            "full_name": "Another User",
        },
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_with_admin_creates_developer() -> None:
    """POST /auth/register with admin token creates a developer."""
    await _seed_admin()
    admin_token = _login("admin@example.com", "securepassword123")

    resp = client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "dev@example.com"
    assert data["full_name"] == "Dev User"
    assert data["role"] == UserRole.DEVELOPER.value
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_register_with_admin_creates_admin() -> None:
    """POST /auth/register with admin token can create another admin."""
    await _seed_admin()
    admin_token = _login("admin@example.com", "securepassword123")

    resp = client.post(
        "/auth/register",
        json={
            "email": "admin2@example.com",
            "password": "securepassword123",
            "full_name": "Second Admin",
            "role": "admin",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 201
    assert resp.json()["role"] == UserRole.ADMIN.value


@pytest.mark.asyncio
async def test_register_duplicate_email() -> None:
    """POST /auth/register returns 409 for duplicate emails."""
    await _seed_admin()
    admin_token = _login("admin@example.com", "securepassword123")

    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 409
    assert "already registered" in resp.json()["message"].lower()


# ── Login tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success_sets_refresh_cookie() -> None:
    """POST /auth/login returns access token and sets HTTP-only refresh cookie."""
    await _seed_admin()

    resp = client.post(
        "/auth/login",
        json={
            "email": "admin@example.com",
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
async def test_login_invalid_credentials() -> None:
    """POST /auth/login returns 401 for bad passwords or emails."""
    resp = client.post(
        "/auth/login",
        json={
            "email": "missing@example.com",
            "password": "wrongpassword",
        },
    )
    assert resp.status_code == 401


# ── Token refresh tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_success() -> None:
    """POST /auth/refresh rotates access token and refresh cookie."""
    await _seed_admin()

    login_resp = client.post(
        "/auth/login",
        json={
            "email": "admin@example.com",
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


# ── Logout tests ─────────────────────────────────────────


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


# ── Profile tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_route_requires_auth() -> None:
    """GET /auth/me returns 401 without bearer token."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_route_success() -> None:
    """GET /auth/me returns user profile when authenticated."""
    await _seed_admin()
    token = _login("admin@example.com", "securepassword123")

    resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@example.com"
    assert data["full_name"] == "Admin User"


# ── RBAC tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_rbac_restrictions() -> None:
    """Test role-based access restrictions on test routes."""
    # Seed admin directly, then admin creates developer via API
    await _seed_admin()
    admin_token = _login("admin@example.com", "securepassword123")

    client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepassword123",
            "full_name": "Dev User",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # ── Developer: allowed on developer-only, denied on admin-only ──
    dev_token = _login("dev@example.com", "securepassword123")

    resp = client.get(
        "/auth-test/developer-only",
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert resp.status_code == 200
    assert "Hello Developer" in resp.json()["message"]

    resp = client.get(
        "/auth-test/admin-only",
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert resp.status_code == 403

    # ── Admin: allowed on admin-only, denied on developer-only ──
    resp = client.get(
        "/auth-test/admin-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "Hello Admin" in resp.json()["message"]

    resp = client.get(
        "/auth-test/developer-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403
