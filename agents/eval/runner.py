"""
RAGAS and benchmark evaluation runner.

Runs golden incidents through the LangGraph orchestrator, computes accuracy metrics,
faithfulness scoring, latency & token cost tracking, and outputs structured JSON
evaluation reports to data/eval/results.json.
"""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from agents.eval.metrics import (
    GoldenIncident,
    compute_faithfulness_score,
    evaluate_incident_result,
)
from agents.orchestrator.graph import run_investigation
from agents.tracing import global_trace_recorder

logger = logging.getLogger(__name__)


async def run_evaluation(
    dataset_path: str = "data/eval/golden_incidents.json",
    output_path: str = "data/eval/results.json",
) -> dict[str, Any]:
    """Execute evaluation benchmark pipeline over golden incident dataset."""
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset file not found: {dataset_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    golden_incidents = [GoldenIncident.model_validate(item) for item in raw_items]
    eval_results = []

    logger.info("Starting evaluation run on %d golden incidents...", len(golden_incidents))

    # Clear traces from any prior run
    global_trace_recorder.clear()

    for golden in golden_incidents:
        logger.info("Evaluating incident %s (%s)...", golden.incident_id, golden.service_id)

        start_time = time.perf_counter()
        state = await run_investigation(
            incident_id=golden.incident_id,
            service_id=golden.service_id,
            alert_message=golden.alert_message,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000

        report = state.report
        pred_root_cause = report.root_cause if report else "No report generated"
        pred_affected = report.affected_services if report else []
        pred_blast = state.blast_radius
        conf_score = report.confidence_score if report else 0.0
        evidence_summary = report.observability_analysis if report else ""

        # Accuracy metrics
        res = evaluate_incident_result(
            golden=golden,
            predicted_root_cause=pred_root_cause,
            predicted_affected_services=pred_affected,
            predicted_blast_radius=pred_blast,
            confidence_score=conf_score,
        )

        # Faithfulness: check evidence grounding
        all_evidence = {
            "log_evidence": state.log_evidence,
            "metrics_evidence": state.metrics_evidence,
            "deploy_evidence": state.deploy_evidence,
            "incident_knowledge_evidence": state.incident_knowledge_evidence,
            "code_evidence": state.code_evidence,
        }
        res["faithfulness_score"] = compute_faithfulness_score(
            observability_analysis=evidence_summary,
            collected_evidence=all_evidence,
        )

        # Latency & token cost from TraceRecorder
        trace_summary = global_trace_recorder.get_summary(golden.incident_id)
        res["latency_ms"] = round(latency_ms, 2)
        res["total_tool_calls"] = trace_summary["total_calls"]
        res["total_tool_latency_ms"] = trace_summary["total_latency_ms"]
        res["total_tokens"] = trace_summary["total_tokens"]
        res["failed_tool_calls"] = trace_summary["failed_calls"]

        eval_results.append(res)

    total_incidents = len(eval_results)
    passed_count = sum(1 for r in eval_results if r["passed_evaluation"])
    avg_blast_acc = (
        sum(r["blast_radius_accuracy"] for r in eval_results) / total_incidents
        if total_incidents > 0
        else 0.0
    )
    avg_root_cause_score = (
        sum(r["root_cause_overlap_score"] for r in eval_results) / total_incidents
        if total_incidents > 0
        else 0.0
    )
    avg_faithfulness = (
        sum(r["faithfulness_score"] for r in eval_results) / total_incidents
        if total_incidents > 0
        else 0.0
    )
    total_latency = sum(r["latency_ms"] for r in eval_results)
    total_tokens = sum(r["total_tokens"] for r in eval_results)

    summary = {
        "total_incidents": total_incidents,
        "passed_incidents": passed_count,
        "pass_rate": round(passed_count / max(total_incidents, 1), 2),
        "average_blast_radius_accuracy": round(avg_blast_acc, 2),
        "average_root_cause_score": round(avg_root_cause_score, 2),
        "average_faithfulness_score": round(avg_faithfulness, 2),
        "total_latency_ms": round(total_latency, 2),
        "total_tokens": total_tokens,
        "results": eval_results,
    }

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(
        "Evaluation complete. Pass rate: %d/%d (%.2f). "
        "Faithfulness: %.2f. Latency: %.0fms. Tokens: %d. Saved to %s",
        passed_count,
        total_incidents,
        summary["pass_rate"],
        avg_faithfulness,
        total_latency,
        total_tokens,
        output_path,
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run incident triage evaluation suite.")
    parser.add_argument("--dataset", default="data/eval/golden_incidents.json")
    parser.add_argument("--output", default="data/eval/results.json")
    args = parser.parse_args()

    asyncio.run(run_evaluation(dataset_path=args.dataset, output_path=args.output))
