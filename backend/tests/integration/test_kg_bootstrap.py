"""Integration tests for KG bootstrap + notifications flow.

Covers: bootstrap trigger via background dispatch, proposal listing,
staging snapshot, feedback revision through the agent, approval that
promotes the staged graph, and notification persistence.
"""

import os

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# Bootstrap agent must be enabled for the run endpoint (defaults to False).
os.environ.setdefault("KG_BOOTSTRAP_ENABLED", "true")

from backend.app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from backend.app.enums import UserRole  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models.user import User  # noqa: E402

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
    """Insert user directly in DB, login, and return access token."""
    from backend.app.core.security import hash_password
    from backend.app.repositories.user import UserRepository

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session=session)
        await repo.create(
            email=email,
            hashed_password=hash_password("password123"),
            full_name=f"{role.value.capitalize()} User",
            role=role,
        )
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
async def test_bootstrap_dispatch_and_proposal() -> None:
    """Bootstrap background task creates a pending kg-bootstrap proposal."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Status: the in-memory graph may be pre-seeded from services.json or
    # start empty (KG_IN_MEMORY_START_EMPTY); either way no bootstrap is
    # pending yet and the payload shape must be correct.
    resp = client.get("/kg-bootstrap/status", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["has_active_graph"], bool)
    assert isinstance(body["bootstrap_enabled"], bool)
    assert body["pending_proposal_id"] is None
    assert body["needs_bootstrap"] == (
        not body["has_active_graph"] and body["pending_proposal_id"] is None
    )

    # Dispatch bootstrap (background task runs synchronously in TestClient)
    resp = client.post(
        "/kg-bootstrap/run",
        json={
            "source": "services_json",
            "architecture_type": "microservice",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "started"

    # Background task completed -> pending proposal exists
    resp = client.get("/kg-bootstrap/status", headers=admin_headers)
    body = resp.json()
    assert body["pending_proposal_id"] is not None


@pytest.mark.asyncio
async def test_bootstrap_staging_snapshot() -> None:
    """Staging snapshot exposes staged nodes and edges."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    client.post(
        "/kg-bootstrap/run",
        json={"source": "services_json"},
        headers=admin_headers,
    )

    resp = client.get("/kg-bootstrap/staging", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["nodes"], list)
    assert len(body["nodes"]) > 0
    assert isinstance(body["edges"], list)


@pytest.mark.asyncio
async def test_feedback_and_approval_flow() -> None:
    """Feedback revises the staged graph; approval promotes it to active."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    client.post(
        "/kg-bootstrap/run",
        json={"source": "services_json"},
        headers=admin_headers,
    )

    # Find the pending bootstrap proposal
    resp = client.get("/kg-proposals", headers=admin_headers)
    proposals = resp.json()
    bootstrap = next(
        p for p in proposals if p["component_id"] == "kg-bootstrap"
    )
    proposal_id = bootstrap["id"]

    # Feedback revision creates a replacement proposal linked to parent
    resp = client.post(
        f"/kg-proposals/{proposal_id}/feedback",
        json={"feedback": "cart-service owner_team should be cart-team"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    revision = resp.json()
    assert revision["parent_proposal_id"] == proposal_id

    # Approve the latest revision -> promotes staged graph to active
    resp = client.post(
        f"/kg-proposals/{revision['id']}/approve",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # Regression: approval must actually promote the staged graph
    # (previously the route-level KGProposalService had no kg_store, so
    # promote_staging was silently skipped). Staging is cleared after
    # promotion and the active graph becomes available.
    staging = client.get("/kg-bootstrap/staging", headers=admin_headers).json()
    assert len(staging["nodes"]) == 0, "staging should be cleared after approval"

    status = client.get("/kg-bootstrap/status", headers=admin_headers).json()
    assert status["has_active_graph"] is True
    assert status["approved_proposal_id"] == revision["id"]

    # Notifications were created for the admin
    resp = client.get("/notifications", headers=admin_headers)
    body = resp.json()
    assert body["total"] > 0
    assert any(n["category"] == "kg_bootstrap" for n in body["notifications"])


@pytest.mark.asyncio
async def test_developer_cannot_approve_bootstrap() -> None:
    """RBAC: only admins may approve or trigger the bootstrap flow."""
    developer_token = await get_token_for_role("member@triage.ai", UserRole.DEVELOPER)
    member_headers = {"Authorization": f"Bearer {developer_token}"}

    # Non-admin cannot trigger the build
    resp = client.post(
        "/kg-bootstrap/run",
        json={"source": "services_json"},
        headers=member_headers,
    )
    assert resp.status_code == 403

    # Non-admin cannot approve a pending proposal
    admin_token = await get_token_for_role("admin2@triage.ai", UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(
        "/kg-bootstrap/run",
        json={"source": "services_json"},
        headers=admin_headers,
    )
    proposals = client.get("/kg-proposals", headers=member_headers).json()
    bootstrap = next(
        p for p in proposals if p["component_id"] == "kg-bootstrap"
    )
    resp = client.post(
        f"/kg-proposals/{bootstrap['id']}/approve",
        headers=member_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reject_proposal_clears_staging() -> None:
    """Rejecting a bootstrap proposal clears the staged graph."""
    admin_token = await get_token_for_role("admin@triage.ai", UserRole.ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    client.post(
        "/kg-bootstrap/run",
        json={"source": "services_json"},
        headers=admin_headers,
    )

    # Staging should have content after a build.
    staging = client.get("/kg-bootstrap/staging", headers=admin_headers).json()
    assert len(staging["nodes"]) > 0, "staging should have content before reject"

    proposals = client.get("/kg-proposals", headers=admin_headers).json()
    bootstrap = next(
        p for p in proposals if p["component_id"] == "kg-bootstrap"
    )

    resp = client.post(
        f"/kg-proposals/{bootstrap['id']}/reject",
        params={"reason": "not the right topology"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    # After rejection, staging must be empty.
    staging = client.get("/kg-bootstrap/staging", headers=admin_headers).json()
    assert len(staging["nodes"]) == 0, "staging should be cleared after reject"
    assert len(staging["edges"]) == 0, "staging edges should be cleared after reject"
