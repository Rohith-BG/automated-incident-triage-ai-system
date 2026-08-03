"""
LangGraph orchestrator definition.

Wires together the nodes (intake, knowledge_graph_query, observability_investigation,
deploy_investigation, incident_knowledge_code_diff, synthesize, confidence_gate)
to execute the incident triage pipeline.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, Optional, Union

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

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
from agents.tracing import global_trace_recorder

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


# ── Helper for MCP tool calls with retry & tracing ────────────────────────


async def _call_mcp_tool(
    client: Any,
    server: str,
    tool_name: str,
    arguments: dict[str, Any],
    incident_id: str,
    agent_name: str,
    max_retries: int = 2,
) -> Any:
    """Call an MCP tool with exponential backoff retries and trace recording."""
    start_time = time.perf_counter()
    last_error = None
    for attempt in range(1, max_retries + 2):
        try:
            res = await client.call_tool(
                server=server, tool_name=tool_name, arguments=arguments
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            global_trace_recorder.record(
                incident_id=incident_id,
                agent=agent_name,
                tool=f"{server}.{tool_name}",
                input_data=arguments,
                output_data=res,
                latency_ms=latency_ms,
                success=True,
            )
            return res
        except Exception as e:
            last_error = e
            logger.warning(
                f"MCP tool call {server}.{tool_name} failed (attempt {attempt}/{max_retries + 1}): {e}"
            )
            if attempt <= max_retries:
                await asyncio.sleep(2**attempt)

    latency_ms = (time.perf_counter() - start_time) * 1000
    global_trace_recorder.record(
        incident_id=incident_id,
        agent=agent_name,
        tool=f"{server}.{tool_name}",
        input_data=arguments,
        output_data=None,
        latency_ms=latency_ms,
        success=False,
        error=str(last_error),
    )
    raise last_error  # type: ignore[misc]


# ── LangGraph Nodes ───────────────────────────────────────────────────────


def _extract_module_entry_point(
    alert_message: str, fallback: str
) -> str:
    """Extract a dotted module path from an alert message.

    Looks for patterns like 'module.submodule' in the alert text.
    Falls back to the given fallback (service_id) if no module
    path is found.
    """
    # Match dotted identifiers like "payments.stripe_client"
    match = re.search(
        r"\b([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+)\b",
        alert_message,
    )
    return match.group(1) if match else fallback


async def intake_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Initial alert intake, architecture detection, and entry point resolution.

    Resolves architecture_type from the KG service metadata and
    derives the graph entry_point for downstream KG queries (Rule 25).
    """
    logger.info(f"Intake Node started for incident {state.incident_id}")
    await notify_progress(
        config,
        event_type="intake_started",
        message="Starting incident investigation intake...",
        details={"service_id": state.service_id},
    )

    # Resolve architecture type from KG metadata
    architecture_type = "microservice"
    entry_point = state.service_id
    try:
        kg_store = create_kg_store(agent_settings)
        svc_info = await kg_store.get_service_info(state.service_id)
        architecture_type = svc_info.get(
            "architecture_type", "microservice"
        )

        if architecture_type == "monolith":
            # For monoliths, extract module path from alert message
            # e.g. "Error in payments.stripe_client: timeout"
            # → entry_point = "payments.stripe_client"
            entry_point = _extract_module_entry_point(
                state.alert_message, state.service_id
            )
        # microservice: entry_point stays as service_id
    except KeyError:
        logger.warning(
            "Service %s not in KG, defaulting to microservice",
            state.service_id,
        )
    except Exception as e:
        logger.error(
            "Error resolving architecture for %s: %s",
            state.service_id,
            e,
        )

    await notify_progress(
        config,
        event_type="intake_completed",
        message="Incident intake validation completed.",
        details={
            "incident_id": state.incident_id,
            "service_id": state.service_id,
            "architecture_type": architecture_type,
            "entry_point": entry_point,
        },
    )
    return {
        "architecture_type": architecture_type,
        "entry_point": entry_point,
    }


async def knowledge_graph_query_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Scope blast radius and dependencies via Knowledge Graph.

    Uses state.entry_point (set by intake_node) as the graph
    lookup key. For microservices this equals service_id; for
    monoliths it is the module path. Graph queries remain
    type-agnostic (Rule 25).
    """
    logger.info("Knowledge Graph Query Node started")
    await notify_progress(
        config,
        event_type="kg_started",
        message="Querying knowledge graph for service topology and owner information...",
    )

    kg_store = create_kg_store(agent_settings)
    # Use entry_point for graph queries; fall back to service_id
    lookup_id = state.entry_point or state.service_id

    try:
        blast_radius = await kg_store.get_blast_radius(lookup_id)
        if lookup_id not in blast_radius:
            blast_radius = [lookup_id] + blast_radius

        dependencies = await kg_store.get_dependencies(lookup_id)

        # Owner team is always resolved at service level
        owner_team = await kg_store.get_owner_team(state.service_id)
        historical_incidents = await kg_store.get_historical_incidents(
            state.service_id
        )

    except Exception as e:
        logger.error(f"Error querying knowledge graph: {e}")
        blast_radius = [lookup_id]
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
            "architecture_type": state.architecture_type,
        },
    )

    return {
        "blast_radius": blast_radius,
        "dependencies": dependencies,
        "owner_team": owner_team,
        "historical_incidents": historical_incidents,
    }


async def observability_investigation_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Collect logs, errors, traces, metrics, and anomalies in parallel via observability MCP server."""
    logger.info("Observability Investigation Node started")
    await notify_progress(
        config,
        event_type="observability_started",
        message="Collecting logs, errors, traces, metrics, and anomalies across blast radius...",
        details={"blast_radius": state.blast_radius},
    )

    mcp_client = create_mcp_client(agent_settings)
    await mcp_client.initialize()

    log_evidence: dict[str, Any] = {}
    metrics_evidence: dict[str, Any] = {}
    semaphore = asyncio.Semaphore(5)

    async def _investigate_service(svc: str) -> None:
        async with semaphore:
            log_evidence[svc] = {}
            metrics_evidence[svc] = {}

            # Parallel calls per service
            async def _fetch_errors() -> None:
                try:
                    res = await _call_mcp_tool(
                        client=mcp_client,
                        server="observability",
                        tool_name="get_errors",
                        arguments={"service": svc, "limit": 10},
                        incident_id=state.incident_id,
                        agent_name="observability",
                        max_retries=agent_settings.TOOL_MAX_RETRIES,
                    )
                    log_evidence[svc]["errors"] = res
                except Exception as e:
                    logger.error(f"Failed to fetch errors for {svc}: {e}")
                    log_evidence[svc]["errors"] = "unavailable"

            async def _fetch_traces() -> None:
                try:
                    res = await _call_mcp_tool(
                        client=mcp_client,
                        server="observability",
                        tool_name="get_traces",
                        arguments={"service": svc},
                        incident_id=state.incident_id,
                        agent_name="observability",
                        max_retries=agent_settings.TOOL_MAX_RETRIES,
                    )
                    log_evidence[svc]["traces"] = res
                except Exception as e:
                    logger.error(f"Failed to fetch traces for {svc}: {e}")
                    log_evidence[svc]["traces"] = "unavailable"

            async def _fetch_metrics() -> None:
                try:
                    res = await _call_mcp_tool(
                        client=mcp_client,
                        server="observability",
                        tool_name="get_metrics",
                        arguments={"service": svc, "minutes": 60},
                        incident_id=state.incident_id,
                        agent_name="observability",
                        max_retries=agent_settings.TOOL_MAX_RETRIES,
                    )
                    metrics_evidence[svc]["metrics"] = res
                except Exception as e:
                    logger.error(f"Failed to fetch metrics for {svc}: {e}")
                    metrics_evidence[svc]["metrics"] = "unavailable"

            async def _fetch_anomalies() -> None:
                try:
                    res = await _call_mcp_tool(
                        client=mcp_client,
                        server="observability",
                        tool_name="get_anomalies",
                        arguments={"service": svc, "minutes": 60},
                        incident_id=state.incident_id,
                        agent_name="observability",
                        max_retries=agent_settings.TOOL_MAX_RETRIES,
                    )
                    metrics_evidence[svc]["anomalies"] = res
                except Exception as e:
                    logger.error(f"Failed to fetch anomalies for {svc}: {e}")
                    metrics_evidence[svc]["anomalies"] = "unavailable"

            await asyncio.gather(
                _fetch_errors(), _fetch_traces(), _fetch_metrics(), _fetch_anomalies()
            )

    await asyncio.gather(*[_investigate_service(s) for s in state.blast_radius])
    await mcp_client.shutdown()

    await notify_progress(
        config,
        event_type="observability_completed",
        message="Observability logs and metrics collection complete.",
        details={"services_investigated": list(log_evidence.keys())},
    )

    return {"log_evidence": log_evidence, "metrics_evidence": metrics_evidence}


async def deploy_investigation_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Collect recent deployments via deploy MCP server."""
    logger.info("Deploy Investigation Node started")
    await notify_progress(
        config,
        event_type="deploy_started",
        message="Checking recent deployment history for alerting service and dependencies...",
    )

    mcp_client = create_mcp_client(agent_settings)
    await mcp_client.initialize()

    deploy_evidence: dict[str, Any] = {}

    for service in [state.service_id] + state.dependencies:
        try:
            res = await _call_mcp_tool(
                client=mcp_client,
                server="deploy",
                tool_name="get_recent_deploys",
                arguments={"service": service, "limit": 5},
                incident_id=state.incident_id,
                agent_name="deploy",
                max_retries=agent_settings.TOOL_MAX_RETRIES,
            )
            deploy_evidence[service] = res
        except Exception as e:
            logger.error(f"Failed to fetch deployments for {service}: {e}")
            deploy_evidence[service] = "unavailable"

    await mcp_client.shutdown()

    await notify_progress(
        config,
        event_type="deploy_completed",
        message="Deployment history check completed.",
        details={"deployments_found": list(deploy_evidence.keys())},
    )

    return {"deploy_evidence": deploy_evidence}


async def incident_knowledge_code_diff_node(
    state: InvestigationState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: Search playbooks/runbooks, resolutions, and recent code commit diffs."""
    logger.info("Incident Knowledge & Code Diff Node started")
    await notify_progress(
        config,
        event_type="knowledge_diff_started",
        message="Searching incident knowledge base and code commit diffs...",
    )

    mcp_client = create_mcp_client(agent_settings)
    await mcp_client.initialize()

    incident_knowledge_evidence: dict[str, Any] = {}
    code_evidence: dict[str, Any] = {}

    # 1. Search incident knowledge base (runbooks, playbooks, resolutions)
    try:
        kb_res = await _call_mcp_tool(
            client=mcp_client,
            server="incident_knowledge",
            tool_name="search_incident_knowledge",
            arguments={"service": state.service_id, "query": state.alert_message, "limit": 5},
            incident_id=state.incident_id,
            agent_name="incident_knowledge",
            max_retries=agent_settings.TOOL_MAX_RETRIES,
        )
        incident_knowledge_evidence["matching_runbooks"] = kb_res
    except Exception as e:
        logger.error(f"Failed to search incident knowledge: {e}")
        incident_knowledge_evidence["matching_runbooks"] = []

    try:
        res_res = await _call_mcp_tool(
            client=mcp_client,
            server="incident_knowledge",
            tool_name="get_past_resolutions",
            arguments={"service": state.service_id, "limit": 5},
            incident_id=state.incident_id,
            agent_name="incident_knowledge",
            max_retries=agent_settings.TOOL_MAX_RETRIES,
        )
        incident_knowledge_evidence["past_resolutions"] = res_res
    except Exception as e:
        logger.error(f"Failed to fetch past resolutions: {e}")
        incident_knowledge_evidence["past_resolutions"] = []

    # 2. Fetch code commit diffs for alerting service
    try:
        commits = await _call_mcp_tool(
            client=mcp_client,
            server="code_diff",
            tool_name="get_recent_commits",
            arguments={"service": state.service_id, "limit": 5},
            incident_id=state.incident_id,
            agent_name="code_diff",
            max_retries=agent_settings.TOOL_MAX_RETRIES,
        )
        code_evidence[state.service_id] = {"recent_commits": commits}

        if isinstance(commits, list) and len(commits) > 0:
            latest_sha = commits[0].get("commit_sha") or commits[0].get("sha")
            if latest_sha:
                diff = await _call_mcp_tool(
                    client=mcp_client,
                    server="code_diff",
                    tool_name="get_commit_diff",
                    arguments={"service": state.service_id, "commit_sha": latest_sha},
                    incident_id=state.incident_id,
                    agent_name="code_diff",
                    max_retries=agent_settings.TOOL_MAX_RETRIES,
                )
                code_evidence[state.service_id]["latest_commit_diff"] = diff
    except Exception as e:
        logger.error(f"Failed to fetch code diffs for {state.service_id}: {e}")
        code_evidence[state.service_id] = "unavailable"

    await mcp_client.shutdown()

    await notify_progress(
        config,
        event_type="knowledge_diff_completed",
        message="Incident knowledge and code diff search complete.",
    )

    return {
        "incident_knowledge_evidence": incident_knowledge_evidence,
        "code_evidence": code_evidence,
    }


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

    user_content = SYNTHESIZER_USER_TEMPLATE.format(
        incident_id=state.incident_id,
        service_id=state.service_id,
        alert_message=state.alert_message,
        blast_radius=state.blast_radius,
        dependencies=state.dependencies,
        owner_team=state.owner_team,
        historical_incidents=state.historical_incidents,
        log_evidence=json.dumps(state.log_evidence, indent=2),
        metrics_evidence=json.dumps(state.metrics_evidence, indent=2),
        deploy_evidence=json.dumps(state.deploy_evidence, indent=2),
        incident_knowledge_evidence=json.dumps(state.incident_knowledge_evidence, indent=2),
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

        if "```" in content:
            match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)
            else:
                match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

        report_dict = json.loads(content.strip())
        report_dict["model_used"] = agent_settings.LLM_MODEL
        report = RootCauseReport.model_validate(report_dict)

    except Exception as e:
        logger.error(f"Error parsing LLM response or validating report: {e}. Raw response: {content}")
        report = RootCauseReport(
            root_cause=f"AI synthesis failed to produce structured JSON report. Exception: {str(e)}",
            evidence_summary="No structured evidence could be parsed from synthesizer.",
            affected_services=[state.service_id],
            remediation_steps=["Check system logs for LLM parser errors."],
            confidence_score=0.1,
            uncertainty=f"Failed LLM synthesis: {str(e)}",
            model_used=agent_settings.LLM_MODEL,
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
    """Node: Validates report confidence score against threshold."""
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
    workflow.add_node("observability_investigation", observability_investigation_node)
    workflow.add_node("deploy_investigation", deploy_investigation_node)
    workflow.add_node("incident_knowledge_code_diff", incident_knowledge_code_diff_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("confidence_gate", confidence_gate_node)

    # Flow edges
    workflow.set_entry_point("intake")
    workflow.add_edge("intake", "knowledge_graph_query")

    # Parallel fan-out after knowledge graph query
    workflow.add_edge("knowledge_graph_query", "observability_investigation")
    workflow.add_edge("knowledge_graph_query", "deploy_investigation")
    workflow.add_edge("knowledge_graph_query", "incident_knowledge_code_diff")

    # Fan-in to synthesis
    workflow.add_edge("observability_investigation", "synthesize")
    workflow.add_edge("deploy_investigation", "synthesize")
    workflow.add_edge("incident_knowledge_code_diff", "synthesize")

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

    final_state_dict = await _graph.ainvoke(
        initial_state.model_dump(), config=config
    )

    return InvestigationState.model_validate(final_state_dict)
