"""
LangGraph orchestrator definition.

Wires together the nodes (intake, knowledge_graph_query, parallel_investigation,
synthesize, confidence_gate) to execute the incident triage pipeline.
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional, Union

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from agents.config import agent_settings
from agents.knowledge_graph.factory import create_kg_store
from agents.llm.base import LLMMessage
from agents.llm.factory import create_llm_adapter
from agents.mcp_client.factory import create_mcp_client
from agents.orchestrator.prompts import (
    SYNTHESIZER_SYSTEM_PROMPT,
    SYNTHESIZER_USER_TEMPLATE,
)
from agents.orchestrator.state import InvestigationState, RootCauseReport

logger = logging.getLogger(__name__)


# ── Helper for progress updates ──────────────────────────────────────────


async def notify_progress(
    config: RunnableConfig,
    event_type: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Invoke progress_callback if configured in RunnableConfig."""
    cb = config.get("configurable", {}).get("progress_callback")
    if cb:
        event = {
            "incident_id": config.get("configurable", {}).get("incident_id", "unknown"),
            "event_type": event_type,
            "message": message,
            "details": details or {},
        }
        try:
            if asyncio.iscoroutinefunction(cb):
                await cb(event)
            else:
                cb(event)
        except Exception as e:
            logger.error(f"Error executing progress callback: {e}")


# ── Retry logic helper ───────────────────────────────────────────────────


async def _call_tool_with_retry(
    client: Any,
    server: str,
    tool_name: str,
    arguments: dict[str, Any],
    max_retries: int = 2,
) -> Any:
    """Call an MCP tool with exponential backoff retries."""
    last_error = None
    for attempt in range(1, max_retries + 2):
        try:
            return await client.call_tool(
                server=server, tool_name=tool_name, arguments=arguments
            )
        except Exception as e:
            last_error = e
            logger.warning(
                f"MCP tool call {server}.{tool_name} failed (attempt {attempt}/{max_retries + 1}): {e}"
            )
            if attempt <= max_retries:
                await asyncio.sleep(2**attempt)
    raise last_error  # type: ignore[misc]


# ── LangGraph Nodes ───────────────────────────────────────────────────────


async def intake_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Initial alert intake and validation."""
    logger.info(f"Intake Node started for incident {state.incident_id}")
    await notify_progress(
        config,
        event_type="intake_started",
        message="Starting incident investigation intake...",
        details={"service_id": state.service_id},
    )

    await notify_progress(
        config,
        event_type="intake_completed",
        message="Incident intake validation completed.",
        details={
            "incident_id": state.incident_id,
            "service_id": state.service_id,
        },
    )
    return {}


async def knowledge_graph_query_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Scope blast radius and dependencies via Knowledge Graph."""
    logger.info("Knowledge Graph Query Node started")
    await notify_progress(
        config,
        event_type="kg_started",
        message="Querying knowledge graph for service topology and owner information...",
    )

    kg_store = create_kg_store(agent_settings)
    service_id = state.service_id

    try:
        blast_radius = await kg_store.get_blast_radius(service_id)
        # Ensure alerting service is part of blast radius
        if service_id not in blast_radius:
            blast_radius = [service_id] + blast_radius

        dependencies = await kg_store.get_dependencies(service_id)
        owner_team = await kg_store.get_owner_team(service_id)
        historical_incidents = await kg_store.get_historical_incidents(service_id)

    except Exception as e:
        logger.error(f"Error querying knowledge graph: {e}")
        # Fallback values
        blast_radius = [service_id]
        dependencies = []
        owner_team = {"id": "unknown", "oncall_slack": "#oncall-fallback"}
        historical_incidents = []

    await notify_progress(
        config,
        event_type="kg_completed",
        message="Knowledge graph details retrieved.",
        details={
            "blast_radius": blast_radius,
            "dependencies": dependencies,
            "owner_team": owner_team,
        },
    )

    return {
        "blast_radius": blast_radius,
        "dependencies": dependencies,
        "owner_team": owner_team,
        "historical_incidents": historical_incidents,
    }


async def log_investigation_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Collect recent logs, errors, and traces in parallel."""
    logger.info("Log Investigation Node started")
    await notify_progress(
        config,
        event_type="logs_started",
        message="Collecting logs and traces for services in blast radius...",
        details={"blast_radius": state.blast_radius},
    )

    mcp_client = create_mcp_client(agent_settings)
    await mcp_client.initialize()

    log_evidence: dict[str, Any] = {}

    # Query logs/errors/traces for all services in blast radius
    for service in state.blast_radius:
        log_evidence[service] = {}

        # 1. Fetch errors
        try:
            errors = await _call_tool_with_retry(
                client=mcp_client,
                server="logs",
                tool_name="get_errors",
                arguments={"service": service, "limit": 10},
                max_retries=agent_settings.TOOL_MAX_RETRIES,
            )
            log_evidence[service]["errors"] = errors
        except Exception as e:
            logger.error(f"Failed to fetch errors for {service}: {e}")
            log_evidence[service]["errors"] = "unavailable"

        # 2. Fetch traces
        try:
            traces = await _call_tool_with_retry(
                client=mcp_client,
                server="logs",
                tool_name="get_traces",
                arguments={"service": service},
                max_retries=agent_settings.TOOL_MAX_RETRIES,
            )
            log_evidence[service]["traces"] = traces
        except Exception as e:
            logger.error(f"Failed to fetch traces for {service}: {e}")
            log_evidence[service]["traces"] = "unavailable"

    await mcp_client.shutdown()

    await notify_progress(
        config,
        event_type="logs_completed",
        message="Log and trace evidence collection complete.",
        details={"services_investigated": list(log_evidence.keys())},
    )

    return {"log_evidence": log_evidence}


async def github_investigation_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Placeholder for code change investigation (Step 9 implementation)."""
    logger.info("GitHub Investigation Node started (stub)")
    await notify_progress(
        config,
        event_type="github_started",
        message="Searching recently deployed commits and pull requests (Placeholder)...",
    )

    # Empty placeholder for now
    code_evidence: dict[str, Any] = {}

    await notify_progress(
        config,
        event_type="github_completed",
        message="Code deployment history search complete (Placeholder).",
    )

    return {"code_evidence": code_evidence}


async def synthesize_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Synthesizes all gathered evidence into a structured Root Cause Report."""
    logger.info("Synthesize Node started")
    await notify_progress(
        config,
        event_type="synthesis_started",
        message="Synthesizing incident root cause using generative AI model...",
    )

    llm = create_llm_adapter(agent_settings)

    # Build prompt content
    user_content = SYNTHESIZER_USER_TEMPLATE.format(
        incident_id=state.incident_id,
        service_id=state.service_id,
        alert_message=state.alert_message,
        blast_radius=state.blast_radius,
        dependencies=state.dependencies,
        owner_team=state.owner_team,
        historical_incidents=state.historical_incidents,
        log_evidence=json.dumps(state.log_evidence, indent=2),
        code_evidence=json.dumps(state.code_evidence, indent=2),
    )

    messages = [
        LLMMessage(role="system", content=SYNTHESIZER_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    content = ""
    try:
        response = await llm.generate(messages)
        content = response.content or ""
        logger.debug(f"Raw LLM synthesis response: {content}")

        # Clean JSON markdown markup if LLM outputs it
        if "```" in content:
            match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)
            else:
                match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

        report_dict = json.loads(content.strip())
        report = RootCauseReport.model_validate(report_dict)

    except Exception as e:
        logger.error(f"Error parsing LLM response or validating report: {e}. Raw response: {content}")
        # Build a safe fallback report
        report = RootCauseReport(
            root_cause=f"AI synthesis failed to produce structured JSON report. Exception: {str(e)}",
            evidence_summary="No structured log evidence could be parsed from synthesizer.",
            affected_services=[state.service_id],
            remediation_steps=["Check the system logs for LLM parser errors."],
            confidence_score=0.1,
        )

    await notify_progress(
        config,
        event_type="synthesis_completed",
        message="AI Root Cause Synthesis completed.",
        details={"confidence_score": report.confidence_score},
    )

    return {"report": report}


async def confidence_gate_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Validates report confidence score against the threshold."""
    logger.info("Confidence Gate Node started")
    await notify_progress(
        config,
        event_type="gate_started",
        message="Applying confidence threshold gate checks...",
    )

    report = state.report
    if not report:
        confidence_gate_passed = False
    else:
        confidence_gate_passed = (
            report.confidence_score >= agent_settings.CONFIDENCE_THRESHOLD
        )

    await notify_progress(
        config,
        event_type="gate_completed",
        message="Confidence gate execution finished.",
        details={
            "confidence_score": report.confidence_score if report else 0.0,
            "threshold": agent_settings.CONFIDENCE_THRESHOLD,
            "passed": confidence_gate_passed,
        },
    )

    return {"confidence_gate_passed": confidence_gate_passed}


# ── StateGraph Construction ────────────────────────────────────────────────


def _build_workflow() -> StateGraph:
    """Build and wire the LangGraph StateGraph."""
    workflow = StateGraph(InvestigationState)

    # Register nodes
    workflow.add_node("intake", intake_node)
    workflow.add_node("knowledge_graph_query", knowledge_graph_query_node)
    workflow.add_node("log_investigation", log_investigation_node)
    workflow.add_node("github_investigation", github_investigation_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("confidence_gate", confidence_gate_node)

    # Flow edges
    workflow.set_entry_point("intake")
    workflow.add_edge("intake", "knowledge_graph_query")

    # Parallel fan-out
    workflow.add_edge("knowledge_graph_query", "log_investigation")
    workflow.add_edge("knowledge_graph_query", "github_investigation")

    # Parallel fan-in / merge
    workflow.add_edge("log_investigation", "synthesize")
    workflow.add_edge("github_investigation", "synthesize")

    # Gate verification
    workflow.add_edge("synthesize", "confidence_gate")
    workflow.add_edge("confidence_gate", END)

    return workflow


# Compiled singleton graph
_graph = _build_workflow().compile()


# ── Public orchestrator entrypoint ──────────────────────────────────────────


async def run_investigation(
    incident_id: str,
    service_id: str,
    alert_message: str,
    progress_callback: Optional[Union[Callable[[dict[str, Any]], Any], Callable[[dict[str, Any]], Any]]] = None,
) -> InvestigationState:
    """Execute the incident triage workflow end-to-end.

    Args:
        incident_id: Unique ID of the incident.
        service_id: Service reporting the issue.
        alert_message: Exact message/error raised in the alert.
        progress_callback: Optional sync or async function receiving state transition updates.

    Returns:
        The final InvestigationState.
    """
    initial_state = InvestigationState(
        incident_id=incident_id,
        service_id=service_id,
        alert_message=alert_message,
    )

    config: RunnableConfig = {
        "configurable": {
            "progress_callback": progress_callback,
            "incident_id": incident_id,
        }
    }

    # Run LangGraph Graph
    final_state_dict = await _graph.ainvoke(
        initial_state.model_dump(), config=config
    )

    return InvestigationState.model_validate(final_state_dict)
