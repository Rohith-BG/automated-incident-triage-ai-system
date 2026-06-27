"""
Mock log provider — MVP implementation.

Reads from ``data/mock_logs.json`` and filters in memory.
Satisfies the ``LogProvider`` protocol.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MockLogProvider:
    """In-memory log provider backed by a JSON fixture file."""

    def __init__(self, data_path: Path) -> None:
        """Initialise with path to the mock_logs.json file.

        Args:
            data_path: Absolute path to mock_logs.json.
        """
        self._data_path = data_path
        self._cache: Optional[list[dict[str, Any]]] = None

    # ── Private helpers ──────────────────────────────────

    async def _load(self) -> list[dict[str, Any]]:
        """Load and cache the JSON fixture.

        First call reads from disk; subsequent calls return
        the cached list.
        """
        if self._cache is None:
            logger.debug("Loading mock logs from %s", self._data_path)
            with open(self._data_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        return self._cache  # type: ignore[return-value]

    # ── Protocol methods ─────────────────────────────────

    async def search_logs(
        self,
        service: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return logs for *service* matching *query*.

        Case-insensitive substring match on the ``message``
        field.  Only includes entries whose ``type`` is
        ``"log"`` (not traces).
        """
        logs = await self._load()
        q = query.lower()
        matches = [
            entry
            for entry in logs
            if (
                entry.get("service") == service
                and entry.get("type", "log") == "log"
                and q in entry.get("message", "").lower()
            )
        ]
        return matches[:limit]

    async def get_traces(
        self,
        service: str,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return trace spans for *service*.

        If *trace_id* is given, filter to that single trace.
        """
        logs = await self._load()
        traces = [
            entry
            for entry in logs
            if (
                entry.get("service") == service
                and entry.get("type") == "trace"
            )
        ]
        if trace_id:
            traces = [
                t for t in traces
                if t.get("trace_id") == trace_id
            ]
        return traces

    async def get_errors(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return most recent ERROR-level log entries."""
        logs = await self._load()
        errors = [
            entry
            for entry in logs
            if (
                entry.get("service") == service
                and entry.get("level") == "ERROR"
            )
        ]
        return errors[:limit]
