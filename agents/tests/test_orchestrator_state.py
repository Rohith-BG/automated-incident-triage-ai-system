"""Unit tests for updated LangGraph orchestrator state models."""

from agents.orchestrator.state import InvestigationState, RootCauseReport


def test_root_cause_report_schema() -> None:
    """Verify RootCauseReport contains structured evidence fields."""
    report = RootCauseReport(
        root_cause="Database connection pool exhaustion.",
        affected_services=["payment-service", "db-service"],
        raw_logs={"payment-service": {"errors": "ConnectionRefusedError"}},
        raw_metrics={"payment-service": {"metrics": "latency_p99: 5000ms"}},
        observability_analysis="Log shows ConnectionRefusedError on db-service.",
        code_diffs={"payment-service": {"recent_commits": []}},
        past_resolutions=[],
        remediation_steps=["Scale up DB connections"],
        confidence_score=0.92,
        uncertainty="No recent deployment logs found.",
    )
    assert report.confidence_score == 0.92
    assert report.uncertainty == "No recent deployment logs found."
    assert report.observability_analysis == "Log shows ConnectionRefusedError on db-service."
    assert report.raw_logs == {"payment-service": {"errors": "ConnectionRefusedError"}}
    assert report.past_resolutions == []


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
