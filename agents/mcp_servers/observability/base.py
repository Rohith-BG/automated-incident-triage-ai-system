"""
Protocol interface for the observability provider.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class ObservabilityProvider(Protocol):
    """Observability data source: logs + metrics."""

    async def search_logs(
        self,
        service: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return logs for *service* matching *query*."""
        ...

    async def get_errors(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent ERROR-level logs for *service*."""
        ...

    async def get_traces(
        self,
        service: str,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return log-based distributed trace spans for *service*."""
        ...

    async def get_metrics(
        self,
        service: str,
        metric_name: Optional[str] = None,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Return time-series metrics for *service* over the last *minutes*."""
        ...

    async def get_anomalies(
        self,
        service: str,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Return detected metric anomalies for *service* over the last *minutes*."""
        ...
