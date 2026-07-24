"""
WebSocket ConnectionManager and real-time streaming endpoint.

Provides real-time incident investigation progress streaming to dashboard clients,
authenticated via JWT token query parameters.
"""

import json
import logging
from typing import Any
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from backend.app.core.security import decode_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Manages active WebSocket connections per incident ID."""

    def __init__(self) -> None:
        """Initialise active connections dict."""
        self._active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, incident_id: str, websocket: WebSocket) -> None:
        """Accept connection and register under incident_id."""
        await websocket.accept()
        if incident_id not in self._active_connections:
            self._active_connections[incident_id] = []
        self._active_connections[incident_id].append(websocket)
        logger.info("WebSocket connected for incident %s", incident_id)

    def disconnect(self, incident_id: str, websocket: WebSocket) -> None:
        """Remove connection upon disconnect."""
        if incident_id in self._active_connections:
            if websocket in self._active_connections[incident_id]:
                self._active_connections[incident_id].remove(websocket)
            if not self._active_connections[incident_id]:
                del self._active_connections[incident_id]
        logger.info("WebSocket disconnected for incident %s", incident_id)

    async def broadcast_event(self, incident_id: str, event: dict[str, Any]) -> None:
        """Broadcast progress event to all clients watching an incident."""
        connections = self._active_connections.get(incident_id, [])
        if not connections:
            return

        payload = json.dumps(event)
        disconnected = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning("Failed to send WebSocket message to client: %s", e)
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(incident_id, ws)


global_ws_manager = ConnectionManager()


@router.websocket("/ws/incidents/{incident_id}")
async def websocket_incident_stream(
    websocket: WebSocket,
    incident_id: str,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """WebSocket endpoint streaming real-time investigation progress."""
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await global_ws_manager.connect(incident_id, websocket)
    try:
        while True:
            # Keep-alive loop receiving client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        global_ws_manager.disconnect(incident_id, websocket)
