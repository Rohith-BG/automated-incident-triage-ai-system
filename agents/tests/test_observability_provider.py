"""Unit tests for the MockObservabilityProvider."""

import pytest
from pathlib import Path
from agents.config import AgentSettings
from agents.mcp_servers.observability.mock import MockObservabilityProvider

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def provider() -> MockObservabilityProvider:
    """Provide a configured MockObservabilityProvider."""
    return MockObservabilityProvider(data_dir=PROJECT_ROOT / "data")


@pytest.mark.asyncio
async def test_search_logs(provider: MockObservabilityProvider) -> None:
    """search_logs() finds log entries matching the query."""
    logs = await provider.search_logs("payment-service", "Stripe")
    assert len(logs) > 0
    for log in logs:
        assert log["service"] == "payment-service"
        assert "stripe" in log["message"].lower()


@pytest.mark.asyncio
async def test_get_errors(provider: MockObservabilityProvider) -> None:
    """get_errors() returns error logs only."""
    logs = await provider.get_errors("payment-service")
    assert len(logs) > 0
    for log in logs:
        assert log["service"] == "payment-service"
        assert log["level"] == "ERROR"


@pytest.mark.asyncio
async def test_get_traces(provider: MockObservabilityProvider) -> None:
    """get_traces() fetches trace spans."""
    traces = await provider.get_traces("payment-service")
    assert len(traces) > 0
    for trace in traces:
        assert trace["service"] == "payment-service"
        assert trace["type"] == "trace"


@pytest.mark.asyncio
async def test_get_metrics(provider: MockObservabilityProvider) -> None:
    """get_metrics() fetches simulated metrics."""
    metrics = await provider.get_metrics("payment-service")
    assert len(metrics) > 0
    for metric in metrics:
        assert metric["service"] == "payment-service"


@pytest.mark.asyncio
async def test_get_anomalies(provider: MockObservabilityProvider) -> None:
    """get_anomalies() filters metrics to anomalous values."""
    anomalies = await provider.get_anomalies("checkout-service")
    # For checkout-service, we have a mock latency of 210ms, which exceeds baseline 200ms
    assert len(anomalies) > 0
    for anomaly in anomalies:
        assert anomaly["service"] == "checkout-service"
        assert "latency" in anomaly["metric"]
