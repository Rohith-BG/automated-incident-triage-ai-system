"""
Mock observability provider — logs + metrics simulation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MockObservabilityProvider:
    """Mock provider serving logs and metrics from JSON fixtures."""

    def __init__(self, data_dir: Path) -> None:
        """Initialise with the data directory path."""
        self._data_dir = data_dir
        self._logs_path = data_dir / "mock_logs.json"
        self._metrics_path = data_dir / "mock_metrics.json"
        self._logs_cache: Optional[list[dict[str, Any]]] = None
        self._metrics_cache: Optional[list[dict[str, Any]]] = None

    async def _load_logs(self) -> list[dict[str, Any]]:
        """Load and cache mock logs."""
        if self._logs_cache is None:
            logger.debug("Loading mock logs from %s", self._logs_path)
            with open(self._logs_path, "r", encoding="utf-8") as f:
                self._logs_cache = json.load(f)
        return self._logs_cache

    async def _load_metrics(self) -> list[dict[str, Any]]:
        """Load and cache mock metrics."""
        if self._metrics_cache is None:
            logger.debug("Loading mock metrics from %s", self._metrics_path)
            with open(self._metrics_path, "r", encoding="utf-8") as f:
                self._metrics_cache = json.load(f)
        return self._metrics_cache

    async def search_logs(
        self,
        service: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search logs for service containing query string."""
        logs = await self._load_logs()
        q = query.lower()
        matches = [
            entry
            for entry in logs
            if entry.get("service") == service
            and entry.get("type") == "log"
            and q in entry.get("message", "").lower()
        ]
        return matches[:limit]

    async def get_errors(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent ERROR-level logs for service."""
        logs = await self._load_logs()
        errors = [
            entry
            for entry in logs
            if entry.get("service") == service
            and entry.get("type") == "log"
            and entry.get("level") == "ERROR"
        ]
        # Fixture is pre-sorted newest first or sorted by timestamp
        return errors[:limit]

    async def get_traces(
        self,
        service: str,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get distributed trace spans for service."""
        logs = await self._load_logs()
        traces = [
            entry
            for entry in logs
            if entry.get("service") == service
            and entry.get("type") == "trace"
        ]
        if trace_id:
            traces = [t for t in traces if t.get("trace_id") == trace_id]
        return traces

    async def get_metrics(
        self,
        service: str,
        metric_name: Optional[str] = None,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Get time-series metrics for service."""
        metrics = await self._load_metrics()
        results = []
        for m in metrics:
            if m.get("service") != service:
                continue
            if metric_name and m.get("metric") != metric_name:
                continue
            # Simplistic time window filtering could go here; returning all for mock
            results.append(m)
        return results

    async def get_anomalies(
        self,
        service: str,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Get anomalies for service. In mock, latency > 200 or error_rate > 0.02 is anomalous."""
        metrics = await self.get_metrics(service, minutes=minutes)
        anomalies = []
        for m in metrics:
            metric = m.get("metric")
            val = m.get("value", 0)
            is_anomaly = False
            desc = ""
            if metric == "latency_ms" and val > 200:
                is_anomaly = True
                desc = f"Latency spike: {val}ms exceeds baseline"
            elif metric == "error_rate" and val > 0.02:
                is_anomaly = True
                desc = f"Error rate spike: {val * 100}% errors"
            elif metric == "cpu_usage" and val > 80.0:
                is_anomaly = True
                desc = f"CPU utilization spike: {val}%"

            if is_anomaly:
                anomalies.append({
                    "service": service,
                    "timestamp": m.get("timestamp"),
                    "metric": metric,
                    "value": val,
                    "unit": m.get("unit"),
                    "description": desc,
                })
        return anomalies
