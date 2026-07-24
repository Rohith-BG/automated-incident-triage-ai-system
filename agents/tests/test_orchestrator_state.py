"""Unit tests for updated LangGraph orchestrator state models."""

from agents.orchestrator.state import InvestigationState, RootCauseReport


def test_root_cause_report_schema() -> None:
    """Verify RootCauseReport contains uncertainty and model_used fields."""
    report = RootCauseReport(
        root_cause="Database connection pool exhaustion.",
        evidence_summary="Log shows ConnectionRefusedError on db-service.",
        affected_services=["payment-service", "db-service"],
        remediation_steps=["Scale up DB connections"],
        confidence_score=0.92,
        uncertainty="No recent deployment logs found.",
        model_used="gemini-2.5-flash",
    )
    assert report.confidence_score == 0.92
    assert report.uncertainty == "No recent deployment logs found."
    assert report.model_used == "gemini-2.5-flash"


def test_investigation_state_schema() -> None:
    """Verify InvestigationState initializes all 5 evidence fields."""
    state = InvestigationState(
        incident_id="inc-1",
        service_id="payment-service",
        alert_message="High latency detected",
    )
    assert state.log_evidence == {}
    assert state.metrics_evidence == {}
    assert state.deploy_evidence == {}
    assert state.incident_knowledge_evidence == {}
    assert state.code_evidence == {}
