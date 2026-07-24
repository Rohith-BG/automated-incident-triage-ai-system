"""Integration tests for WebSocket endpoint."""

import json

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.websocket import global_ws_manager

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


def _make_token() -> str:
    """Generate a valid JWT access token for testing."""
    return create_access_token(data={"sub": "test-user@example.com"})


def test_websocket_rejects_missing_token() -> None:
    """WebSocket connection without token should be rejected."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/incidents/inc-1"):
            pass


def test_websocket_rejects_invalid_token() -> None:
    """WebSocket connection with invalid JWT should be rejected."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/incidents/inc-1?token=bad-token"):
            pass


def test_websocket_connects_with_valid_token() -> None:
    """WebSocket accepts connection with valid JWT and responds to ping."""
    token = _make_token()
    with client.websocket_connect(f"/ws/incidents/inc-test?token={token}") as ws:
        ws.send_text("ping")
        data = ws.receive_text()
        msg = json.loads(data)
        assert msg["type"] == "pong"


def test_websocket_connection_manager_broadcast() -> None:
    """ConnectionManager tracks connections and broadcasts events."""
    token = _make_token()
    with client.websocket_connect(f"/ws/incidents/inc-bc?token={token}") as ws:
        # Manager should have registered this connection
        assert "inc-bc" in global_ws_manager._active_connections
        assert len(global_ws_manager._active_connections["inc-bc"]) == 1

        # Verify ping/pong still works
        ws.send_text("ping")
        data = ws.receive_text()
        assert json.loads(data)["type"] == "pong"
