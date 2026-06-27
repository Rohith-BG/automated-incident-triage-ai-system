"""
Protocol interface for the log provider.

Every implementation (mock JSON, Loki, Elasticsearch, CloudWatch)
must satisfy this contract.  Consumers depend only on this
Protocol — never on a concrete class.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class LogProvider(Protocol):
    """Read-only log source used by the Log Agent."""

    async def search_logs(
        self,
        service: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return logs for *service* matching *query*.

        Case-insensitive substring match on the message field.
        Each dict contains at minimum:
            service, timestamp, level, message.
        """
        ...

    async def get_traces(
        self,
        service: str,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return distributed-trace spans for *service*.

        If *trace_id* is given, filter to that single trace.
        Each dict contains at minimum:
            service, timestamp, trace_id, span_id,
            operation, duration_ms.
        """
        ...

    async def get_errors(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent ERROR-level logs for *service*.

        Ordered newest-first.
        """
        ...
