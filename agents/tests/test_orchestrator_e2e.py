"""Integration test for full LangGraph orchestrator pipeline execution."""

import pytest
from agents.orchestrator.graph import run_investigation


@pytest.mark.asyncio
async def test_run_investigation_e2e() -> None:
    """Run full LangGraph incident investigation workflow with mock MCP tools and LLM."""
    progress_events = []

    def on_progress(event: dict) -> None:
        progress_events.append(event)

    final_state = await run_investigation(
        incident_id="inc-e2e-test",
        service_id="payment-service",
        alert_message="High latency and 500 error rate on /checkout",
        progress_callback=on_progress,
    )

    assert final_state.incident_id == "inc-e2e-test"
    assert final_state.service_id == "payment-service"
    assert len(final_state.blast_radius) >= 1
    assert "payment-service" in final_state.log_evidence
    assert "payment-service" in final_state.metrics_evidence
    assert "payment-service" in final_state.deploy_evidence
    assert "matching_runbooks" in final_state.incident_knowledge_evidence
    assert final_state.report is not None
    assert final_state.report.confidence_score > 0.0
    assert final_state.confidence_gate_passed is not None
    assert len(progress_events) > 0
