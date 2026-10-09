"""Unit and integration test for evaluation runner."""

import pytest
from agents.eval.metrics import (
    GoldenIncident,
    compute_faithfulness_score,
    evaluate_incident_result,
)
from agents.eval.runner import run_evaluation


def test_evaluate_incident_result_scoring() -> None:
    """Test metrics evaluation result calculation."""
    golden = GoldenIncident(
        incident_id="inc-100",
        service_id="payment-service",
        alert_message="Redis error",
        expected_root_cause="Redis cache node failure",
        expected_affected_services=["payment-service"],
        expected_blast_radius=["payment-service", "redis-cache"],
    )

    res = evaluate_incident_result(
        golden=golden,
        predicted_root_cause="Redis cache node connection failure",
        predicted_affected_services=["payment-service"],
        predicted_blast_radius=["payment-service", "redis-cache"],
        confidence_score=0.9,
    )

    assert res["blast_radius_accuracy"] == 1.0
    assert res["affected_services_accuracy"] == 1.0
    assert res["passed_evaluation"] is True


def test_faithfulness_score_grounded() -> None:
    """Faithfulness score is high when observability_analysis references collected evidence."""
    evidence = {
        "log_evidence": {"payment-service": {"errors": "ECONNREFUSED redis-cache"}},
    }
    score = compute_faithfulness_score(
        observability_analysis="ECONNREFUSED error from redis-cache in payment-service logs",
        collected_evidence=evidence,
    )
    assert score > 0.3


def test_faithfulness_score_empty() -> None:
    """Faithfulness score is 0.0 when no evidence is collected."""
    score = compute_faithfulness_score(
        observability_analysis="Redis crashed due to memory pressure",
        collected_evidence={},
    )
    assert score == 0.0


@pytest.mark.asyncio
async def test_run_evaluation_e2e() -> None:
    """Run full evaluation suite over golden incidents."""
    summary = await run_evaluation(
        dataset_path="data/eval/golden_incidents.json",
        output_path="data/eval/results.json",
    )

    assert summary["total_incidents"] == 7
    assert summary["pass_rate"] > 0.0
    assert len(summary["results"]) == 7
    # Verify latency/token tracking is present
    assert "total_latency_ms" in summary
    assert "total_tokens" in summary
    assert "average_faithfulness_score" in summary
    # Each result has per-incident latency
    for r in summary["results"]:
        assert "latency_ms" in r
        assert "faithfulness_score" in r
