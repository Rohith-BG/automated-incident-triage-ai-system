"""
Trace service — backend-side adapter for agent trace data.

Bridges the backend↔agent boundary (Rule 6) by providing a
service layer that backend routes call. The actual TraceRecorder
lives in agents/; this service accesses it through a clean import
boundary rather than letting routes import agent internals directly.
"""

from typing import Any, Protocol


class ITraceProvider(Protocol):
    """Interface for trace data providers (DIP — Dependency Inversion)."""

    def get_traces(self, incident_id: str) -> list[Any]:
        """Return raw traces for an incident."""
        ...

    def get_summary(self, incident_id: str) -> dict[str, Any]:
        """Return aggregate summary for an incident."""
        ...


class TraceService:
    """Service layer exposing agent trace data to backend routes."""

    def __init__(self, provider: ITraceProvider) -> None:
        """Initialise with trace data provider."""
        self._provider = provider

    def get_incident_traces(self, incident_id: str) -> dict[str, Any]:
        """Return formatted traces and summary for a given incident."""
        traces = self._provider.get_traces(incident_id)
        summary = self._provider.get_summary(incident_id)

        return {
            "incident_id": incident_id,
            "summary": summary,
            "traces": [
                t.to_dict() if hasattr(t, "to_dict") else t
                for t in traces
            ],
        }
