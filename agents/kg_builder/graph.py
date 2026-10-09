"""
LangGraph workflow for the Knowledge Graph bootstrap agent.

Runs outside the incident orchestrator. Reads the codebase through the
repo_intelligence MCP server (never parses code itself), converts
extracted facts into evidence-carrying mutations, validates them, and
stages the result in the knowledge graph store for human review.

A second workflow (feedback revision) turns free-text reviewer feedback
into verified revision mutations, keeping the staged graph up to date
between feedback rounds (Rule 26: nothing reaches the active graph
without human approval).
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Union

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.config import AgentSettings, agent_settings
from agents.kg_builder.entity_resolver import (
    build_inventory,
    resolve_entity,
)
from agents.kg_builder.feedback_parser import (
    FeedbackParse,
    guess_subject,
    parse_feedback,
)
from agents.kg_builder.mutations import (
    build_add_contains_mutation,
    build_add_dependency_mutation,
    build_add_node_mutation,
    build_remove_dependency_mutation,
    build_remove_node_mutation,
    build_update_metadata_mutation,
    deduplicate_mutations,
    derive_service_id,
    evidence_summary,
    normalize_node_id,
    validate_mutations,
)
from agents.kg_builder.state import KgBootstrapState
from agents.tracing import global_trace_recorder

logger = logging.getLogger(__name__)

_MAX_PARALLEL_TARGETS = 8


# ── Helpers ────────────────────────────────────────────────────────────────


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
            "run_id": config.get("configurable", {}).get("run_id", "kg-bootstrap"),
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
            logger.error("Error executing progress callback: %s", e)


async def _call_repo_tool(
    mcp_client: Any,
    run_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> Any:
    """Call a repo_intelligence tool and record a trace."""
    import time

    start = time.monotonic()
    try:
        result = await mcp_client.call_tool(
            server="repo_intelligence",
            tool_name=tool,
            arguments=arguments,
        )
        global_trace_recorder.record(
            incident_id=run_id,
            agent="kg_bootstrap",
            tool=tool,
            input_data=arguments,
            output_data=result,
            latency_ms=(time.monotonic() - start) * 1000,
            success=True,
        )
        return result
    except Exception as e:
        global_trace_recorder.record(
            incident_id=run_id,
            agent="kg_bootstrap",
            tool=tool,
            input_data=arguments,
            output_data="",
            latency_ms=(time.monotonic() - start) * 1000,
            success=False,
            error=str(e),
        )
        logger.error("repo_intelligence.%s failed: %s", tool, e)
        return None


# ── Initial bootstrap nodes ────────────────────────────────────────────────


async def discover_targets_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: determine which repositories to scan.

    Targets come from the MCP list_repositories tool (github_org),
    the configured single repo (github_repo), or the local
    services.json fixture (dev mode).
    """
    run_id = config.get("configurable", {}).get("run_id", "kg-bootstrap")
    mcp_client = config.get("configurable", {}).get("mcp_client")
    agent_config: AgentSettings = config.get("configurable", {}).get("agent_config") or agent_settings

    await notify_progress(
        config, "kg_discover_started", "Discovering repository targets..."
    )

    targets: list[dict[str, Any]] = []

    if state.source == "github_org":
        result = await _call_repo_tool(
            mcp_client,
            run_id,
            "list_repositories",
            {"org": state.org},
        )
        if result:
            for repo in result:
                repo_slug = repo.get("repo", "")
                targets.append(
                    {
                        "repo": repo_slug,
                        "name": repo.get("name", derive_service_id(repo_slug)),
                        "language": repo.get("language", ""),
                        "service_id": derive_service_id(repo_slug),
                        "description": repo.get("description", ""),
                    }
                )
        else:
            logger.warning("No repositories discovered for org %s", state.org)

    elif state.source == "github_repo":
        repo_slug = state.repo
        targets.append(
            {
                "repo": repo_slug,
                "name": derive_service_id(repo_slug),
                "language": "",
                "service_id": derive_service_id(repo_slug),
                "description": "",
            }
        )

    elif state.source == "services_json":
        # Dev mode: local fixture, no network required.
        fixture = _load_services_fixture(agent_config.SERVICES_JSON_PATH)
        for svc in fixture.get("services", []):
            targets.append(
                {
                    "repo": svc.get("repo", ""),
                    "name": svc.get("id"),
                    "language": svc.get("language", ""),
                    "service_id": svc.get("id"),
                    "owner_team": svc.get("owner_team"),
                    "description": "",
                }
            )

    await notify_progress(
        config,
        "kg_discover_completed",
        f"Discovered {len(targets)} repository target(s).",
        {"targets": targets},
    )
    return {"targets": targets}


async def extract_facts_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: extract codebase facts through MCP for every target (bounded concurrency)."""
    run_id = config.get("configurable", {}).get("run_id", "kg-bootstrap")
    mcp_client = config.get("configurable", {}).get("mcp_client")
    architecture_type = state.architecture_type

    await notify_progress(
        config, "kg_extract_started", "Extracting manifests, imports, and dependencies..."
    )

    async def extract_one(target: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        service_id = target["service_id"]
        repo = target["repo"]
        facts: dict[str, Any] = {
            "service_id": service_id,
            "repo": repo,
            "name": target.get("name", service_id),
            "language": target.get("language", ""),
            "description": target.get("description", ""),
            "owner_team": target.get("owner_team", ""),
            "dependencies": [],
            "modules": [],
            "notes": [],
        }
        if not repo:
            facts["notes"].append(f"No repo for service {service_id}")
            return service_id, facts

        dep_result = await _call_repo_tool(
            mcp_client,
            run_id,
            "infer_dependencies",
            {
                "repo": repo,
                "service_id": service_id,
                "architecture_type": architecture_type,
            },
        )
        if dep_result:
            facts["dependencies"] = dep_result.get("dependencies", [])
            facts["notes"].extend(dep_result.get("notes", []))

        arch_result = await _call_repo_tool(
            mcp_client,
            run_id,
            "inspect_architecture",
            {"repo": repo, "architecture_type": architecture_type},
        )
        if arch_result:
            facts["modules"] = arch_result.get("modules", [])

        # Deep structure for hierarchical KG (monoliths).
        if architecture_type == "monolith":
            deep_result = await _call_repo_tool(
                mcp_client,
                run_id,
                "inspect_deep_structure",
                {
                    "repo": repo,
                    "architecture_type": architecture_type,
                },
            )
            if deep_result:
                facts["packages"] = deep_result.get(
                    "packages", []
                )
                facts["files"] = deep_result.get(
                    "files", []
                )
                # Use deep structure modules if available.
                deep_mods = deep_result.get("modules", [])
                if deep_mods:
                    facts["modules"] = [
                        {
                            "path": m,
                            "kind": "module",
                            "evidence": f"{repo}:tree/{m}",
                        }
                        for m in deep_mods
                    ]

        manifest_result = await _call_repo_tool(
            mcp_client,
            run_id,
            "extract_manifests",
            {"repo": repo, "service_id": service_id},
        )
        if manifest_result:
            facts["manifests"] = manifest_result.get("manifests", [])

        return service_id, facts

    sem = asyncio.Semaphore(_MAX_PARALLEL_TARGETS)

    async def bounded(target: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        async with sem:
            return await extract_one(target)

    results = await asyncio.gather(
        *(bounded(t) for t in state.targets), return_exceptions=True
    )

    extracted: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for result in results:
        if isinstance(result, BaseException):
            errors.append(f"Extraction failed: {result}")
            continue
        service_id, facts = result
        extracted[service_id] = facts

    await notify_progress(
        config,
        "kg_extract_completed",
        f"Extracted facts for {len(extracted)} target(s).",
        {"errors": errors},
    )
    return {"extracted": extracted, "errors": errors}


async def build_mutations_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: convert extracted facts into hierarchical mutations.

    Creates a 4-level graph: system → module → package → function
    with CONTAINS edges for hierarchy and DEPENDS_ON edges for
    cross-layer function calls.
    """
    mutations: list[dict[str, Any]] = []
    owner_team_default = state.owner_team

    for service_id, facts in state.extracted.items():
        repo = facts.get("repo", "")

        # Level 0: system node.
        mutations.append(
            build_add_node_mutation(
                node_id=service_id,
                metadata={
                    "owner_team": (
                        facts.get("owner_team") or owner_team_default
                    ),
                    "language": facts.get("language", ""),
                    "repo": repo,
                    "description": facts.get("description", ""),
                    "architecture_type": state.architecture_type,
                    "kind": "system",
                },
                evidence=f"{repo}:repo",
            )
        )

        # Level 1: module nodes + CONTAINS from system.
        for module in facts.get("modules", []):
            module_path = module.get("path", "")
            if not module_path:
                continue
            module_id = module_path  # e.g. "backend"
            mutations.append(
                build_add_node_mutation(
                    node_id=module_id,
                    metadata={
                        "owner_team": owner_team_default,
                        "kind": "module",
                        "repo": repo,
                    },
                    evidence=module.get(
                        "evidence", f"{repo}:tree/{module_path}"
                    ),
                )
            )
            mutations.append(
                build_add_contains_mutation(
                    parent_id=service_id,
                    child_id=module_id,
                    evidence=f"{repo}:tree/{module_path}",
                )
            )

        # Level 2: package nodes + CONTAINS from module.
        pkg_ids: set[str] = set()
        for pkg in facts.get("packages", []):
            pkg_module = pkg.get("module", "")
            pkg_name = pkg.get("name", "")
            if not pkg_module or not pkg_name:
                continue
            pkg_id = f"{pkg_module}.{pkg_name}"
            pkg_ids.add(pkg_id)
            mutations.append(
                build_add_node_mutation(
                    node_id=pkg_id,
                    metadata={
                        "kind": "package",
                        "parent": pkg_module,
                        "display_name": pkg_name,
                        "file_path": pkg.get("path", ""),
                        "repo": repo,
                    },
                    evidence=pkg.get(
                        "evidence",
                        f"{repo}:tree/{pkg.get('path', '')}",
                    ),
                )
            )
            mutations.append(
                build_add_contains_mutation(
                    parent_id=pkg_module,
                    child_id=pkg_id,
                    evidence=pkg.get(
                        "evidence",
                        f"{repo}:tree/{pkg.get('path', '')}",
                    ),
                )
            )

        # Level 3+: file → class → method (or file → function).
        # Build a lookup of function/method node IDs by short
        # name for cross-layer dependency resolution.
        fn_by_name: dict[str, list[str]] = {}
        all_fn_calls: list[tuple[str, str, list[str]]] = []

        for file_rec in facts.get("files", []):
            pkg_id = file_rec.get("package_id", "")
            file_stem = file_rec.get("file_stem", "")
            file_path = file_rec.get("file_path", "")
            if not pkg_id or not file_stem:
                continue

            # Level 3: file node + CONTAINS from package.
            file_id = f"{pkg_id}.{file_stem}"
            mutations.append(
                build_add_node_mutation(
                    node_id=file_id,
                    metadata={
                        "kind": "file",
                        "parent": pkg_id,
                        "display_name": f"{file_stem}.py",
                        "file_path": file_path,
                        "repo": repo,
                    },
                    evidence=f"{repo}:{file_path}",
                )
            )
            mutations.append(
                build_add_contains_mutation(
                    parent_id=pkg_id,
                    child_id=file_id,
                    evidence=f"{repo}:{file_path}",
                )
            )

            # Classes and their methods.
            for cls in file_rec.get("classes", []):
                cls_name = cls.get("name", "")
                if not cls_name:
                    continue
                cls_id = f"{file_id}.{cls_name}"
                mutations.append(
                    build_add_node_mutation(
                        node_id=cls_id,
                        metadata={
                            "kind": "class",
                            "parent": file_id,
                            "display_name": cls_name,
                            "line_number": cls.get(
                                "line_number", 0
                            ),
                            "file_path": file_path,
                            "repo": repo,
                        },
                        evidence=(
                            f"{repo}:{file_path}"
                            f":L{cls.get('line_number', 0)}"
                        ),
                    )
                )
                mutations.append(
                    build_add_contains_mutation(
                        parent_id=file_id,
                        child_id=cls_id,
                        evidence=f"{repo}:{file_path}",
                    )
                )
                for method in cls.get("methods", []):
                    m_name = method.get("name", "")
                    if not m_name:
                        continue
                    m_id = f"{cls_id}.{m_name}"
                    mutations.append(
                        build_add_node_mutation(
                            node_id=m_id,
                            metadata={
                                "kind": "method",
                                "parent": cls_id,
                                "display_name": m_name,
                                "is_async": method.get(
                                    "is_async", False
                                ),
                                "line_number": method.get(
                                    "line_number", 0
                                ),
                                "file_path": file_path,
                                "repo": repo,
                            },
                            evidence=(
                                f"{repo}:{file_path}"
                                f":L{method.get('line_number', 0)}"
                            ),
                        )
                    )
                    mutations.append(
                        build_add_contains_mutation(
                            parent_id=cls_id,
                            child_id=m_id,
                            evidence=(
                                f"{repo}:{file_path}"
                            ),
                        )
                    )
                    fn_by_name.setdefault(
                        m_name, []
                    ).append(m_id)
                    all_fn_calls.append((
                        m_id, pkg_id,
                        method.get("calls", []),
                    ))

            # Standalone functions (no class).
            for fn in file_rec.get("functions", []):
                fn_name = fn.get("name", "")
                if not fn_name:
                    continue
                fn_id = f"{file_id}.{fn_name}"
                mutations.append(
                    build_add_node_mutation(
                        node_id=fn_id,
                        metadata={
                            "kind": "function",
                            "parent": file_id,
                            "display_name": fn_name,
                            "is_async": fn.get(
                                "is_async", False
                            ),
                            "line_number": fn.get(
                                "line_number", 0
                            ),
                            "file_path": file_path,
                            "repo": repo,
                        },
                        evidence=(
                            f"{repo}:{file_path}"
                            f":L{fn.get('line_number', 0)}"
                        ),
                    )
                )
                mutations.append(
                    build_add_contains_mutation(
                        parent_id=file_id,
                        child_id=fn_id,
                        evidence=f"{repo}:{file_path}",
                    )
                )
                fn_by_name.setdefault(
                    fn_name, []
                ).append(fn_id)
                all_fn_calls.append((
                    fn_id, pkg_id, fn.get("calls", []),
                ))

        # Cross-layer DEPENDS_ON edges from call analysis.
        seen_deps: set[tuple[str, str]] = set()
        for fn_id, src_pkg, calls in all_fn_calls:
            for call in calls:
                call_method = call.rsplit(".", 1)[-1]
                if not call_method:
                    continue
                targets = fn_by_name.get(call_method, [])
                for target_id in targets:
                    if target_id == fn_id:
                        continue
                    # Only link across different packages.
                    # Extract package from dotted ID.
                    t_parts = target_id.split(".")
                    target_pkg = (
                        ".".join(t_parts[:2])
                        if len(t_parts) >= 2 else ""
                    )
                    if target_pkg == src_pkg:
                        continue
                    edge_key = (fn_id, target_id)
                    if edge_key in seen_deps:
                        continue
                    seen_deps.add(edge_key)
                    mutations.append(
                        build_add_dependency_mutation(
                            from_id=fn_id,
                            to_id=target_id,
                            evidence=(
                                f"{repo}:call:{call_method}"
                            ),
                        )
                    )

        # Cross-module dependency edges (from import analysis).
        seen_mod_edges: set[tuple[str, str]] = set()
        for dep in facts.get("dependencies", []):
            if dep.get("kind") != "cross_module":
                continue
            source = dep.get("from", "")
            target = dep.get("to", "")
            if (
                not source or not target
                or source == target
            ):
                continue
            edge_key = (source, target)
            if edge_key in seen_mod_edges:
                continue
            seen_mod_edges.add(edge_key)
            mutations.append(
                build_add_dependency_mutation(
                    from_id=source,
                    to_id=target,
                    evidence=dep.get(
                        "evidence", f"{repo}:import"
                    ),
                )
            )

        # Service-level dependency edges (inter-service).
        for dep in facts.get("dependencies", []):
            if dep.get("kind") not in (
                "internal_service", "external",
            ):
                continue
            target = dep.get("to", "")
            if not target or target == service_id:
                continue
            edge_key = (service_id, target)
            if edge_key in seen_mod_edges:
                continue
            seen_mod_edges.add(edge_key)
            mutations.append(
                build_add_dependency_mutation(
                    from_id=service_id,
                    to_id=target,
                    evidence=dep.get(
                        "evidence", f"{repo}:dependency"
                    ),
                )
            )

    return {"mutations": mutations}


async def validate_mutations_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: validate + deduplicate mutations; record dropped ones as uncertainty."""
    valid, dropped = validate_mutations(state.mutations)
    valid = deduplicate_mutations(valid)
    uncertainty = list(state.uncertainty)
    for reason in dropped:
        uncertainty.append(f"Dropped unverifiable mutation: {reason}")
    return {"mutations": valid, "uncertainty": uncertainty}


async def stage_graph_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: write the validated mutations into the store's staging graph."""
    kg_store = config.get("configurable", {}).get("kg_store")
    if kg_store is None:
        return {"errors": state.errors + ["No kg_store provided"]}

    await notify_progress(
        config,
        "kg_stage_started",
        "Writing staged graph for human review...",
    )
    summary = await kg_store.staging_replace(state.mutations)
    await notify_progress(
        config,
        "kg_stage_completed",
        f"Staged {summary.get('applied', 0)} mutation(s).",
        summary,
    )
    if summary.get("errors"):
        return {"errors": state.errors + list(summary["errors"])}
    return {}


async def summarize_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: build the human-readable diff summary."""
    diff_summary = evidence_summary(state.mutations)
    if state.uncertainty:
        diff_summary += (
            f". {len(state.uncertainty)} note(s) requiring review."
        )
    return {"diff_summary": diff_summary}


# ── Feedback revision nodes ────────────────────────────────────────────────


async def parse_feedback_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: parse free-text feedback into intent + entities (deterministic)."""
    parse: FeedbackParse = parse_feedback(state.feedback_text)
    return {
        "feedback_intent": parse.intent,
        "feedback_entities": parse.entities,
    }


async def resolve_entities_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: deterministically resolve feedback entities against graph inventory."""
    kg_store = config.get("configurable", {}).get("kg_store")
    active_services: list[str] = []
    staged_nodes: list[dict[str, Any]] = []
    if kg_store is not None:
        try:
            active_services = await kg_store.get_all_services()
            snapshot = await kg_store.staging_snapshot()
            staged_nodes = snapshot.get("nodes", [])
        except Exception as e:
            logger.warning("Could not load inventory for entity resolution: %s", e)

    extra = [str(t["service_id"]) for t in state.targets if t.get("service_id")]
    inventory = build_inventory(
        active_services=active_services,
        staged_nodes=staged_nodes,
        extra=extra,
    )

    resolution: dict[str, Any] = {}
    for mention in state.feedback_entities:
        outcome = resolve_entity(mention, inventory)
        resolution[mention] = outcome
    return {"feedback_resolution": resolution}


async def verify_claims_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: verify reviewer claims against the codebase via MCP before applying.

    Produces ``revision_mutations`` (only verified changes) and appends
    unverified claims to uncertainty. approve/reject intents are passed
    through without mutations.
    """
    run_id = config.get("configurable", {}).get("run_id", "kg-bootstrap")
    mcp_client = config.get("configurable", {}).get("mcp_client")
    intent = state.feedback_intent
    uncertainty = list(state.uncertainty)
    revision_mutations: list[dict[str, Any]] = []
    resolution = state.feedback_resolution

    inventory = build_inventory(
        active_services=[t.get("service_id", "") for t in state.targets],
        staged_nodes=[],
    )

    if intent in ("approve", "reject"):
        return {"uncertainty": uncertainty}

    subject = guess_subject(
        FeedbackParse(
            intent=intent,
            entities=state.feedback_entities,
            metadata_updates={},
        ),
        inventory,
    )

    if intent in ("add_dependency", "remove_dependency"):
        if not subject:
            uncertainty.append(
                "Could not identify the subject service for feedback; please clarify."
            )
            return {"uncertainty": uncertainty}

        # Pick the target: second resolved entity mention.
        target: Optional[str] = None
        for mention in state.feedback_entities:
            outcome = resolution.get(mention, {})
            if outcome.get("resolved") and outcome["match"] != subject:
                target = outcome["match"]
                break
        if not target:
            uncertainty.append(
                f"Could not resolve a target dependency for {subject}; please clarify."
            )
            return {"uncertainty": uncertainty}

        # Verify the claim with a targeted MCP re-read.
        repo = _repo_for_service(state.extracted, subject)
        verified = False
        evidence = ""
        if repo:
            dep_result = await _call_repo_tool(
                mcp_client,
                run_id,
                "infer_dependencies",
                {
                    "repo": repo,
                    "service_id": subject,
                    "architecture_type": state.architecture_type,
                },
            )
            if dep_result:
                dep_ids = {d.get("to", "") for d in dep_result.get("dependencies", [])}
                if intent == "add_dependency" and target in dep_ids:
                    verified = True
                    evidence = f"{repo}:verified-dependency:{target}"
                elif intent == "remove_dependency" and target in dep_ids:
                    verified = True
                    evidence = f"{repo}:verified-dependency:{target}"
                elif intent == "remove_dependency" and target not in dep_ids:
                    uncertainty.append(
                        f"{subject} does not depend on {target} in the current repo; nothing to remove."
                    )

        if not verified:
            if intent == "add_dependency" and repo:
                uncertainty.append(
                    f"Claim '{subject} depends on {target}' could not be verified in {repo}; skipped."
                )
            return {"uncertainty": uncertainty}

        if intent == "add_dependency":
            revision_mutations.append(
                build_add_dependency_mutation(subject, target, evidence)
            )
        else:
            revision_mutations.append(
                build_remove_dependency_mutation(subject, target, evidence)
            )

    elif intent == "update_metadata":
        if not subject:
            uncertainty.append(
                "Could not identify the service to update; please clarify."
            )
            return {"uncertainty": uncertainty}
        parse = parse_feedback(state.feedback_text)
        for field, value in parse.metadata_updates.items():
            revision_mutations.append(
                build_update_metadata_mutation(
                    node_id=subject,
                    field=field,
                    value=value,
                    evidence="reviewer-feedback",
                )
            )

    elif intent == "add_node":
        # Unresolved entities may be brand-new services; verify the repo exists.
        for mention in state.feedback_entities:
            outcome = resolution.get(mention, {})
            if outcome.get("resolved"):
                continue
            candidate = normalize_node_id(mention)
            exists = await _repo_exists(mcp_client, run_id, state, candidate)
            if exists:
                revision_mutations.append(
                    build_add_node_mutation(
                        node_id=candidate,
                        metadata={
                            "owner_team": state.owner_team,
                            "kind": "service",
                            "repo": f"{state.org}/{candidate}",
                            "architecture_type": state.architecture_type,
                        },
                        evidence=f"reviewer-feedback:{mention}",
                    )
                )
            else:
                uncertainty.append(
                    f"Could not verify repo for new service '{mention}'; not added."
                )

    elif intent == "remove_node":
        # Reviewer wants a staged/active service gone. Verify the entity
        # resolves to a known graph node before staging the removal.
        if not subject:
            uncertainty.append(
                "Could not identify the service to remove; please clarify."
            )
            return {"uncertainty": uncertainty}
        resolved_subject = None
        for mention in state.feedback_entities:
            outcome = resolution.get(mention, {})
            if outcome.get("resolved") and outcome["match"] == subject:
                resolved_subject = outcome["match"]
                break
        if not resolved_subject:
            uncertainty.append(
                f"Could not resolve '{subject}' to a known graph node; not removed."
            )
        else:
            revision_mutations.append(
                build_remove_node_mutation(
                    node_id=resolved_subject,
                    evidence="reviewer-feedback",
                )
            )

    else:
        uncertainty.append(
            "Feedback intent not recognized. Please use phrases like "
            "'add dependency X on Y', 'remove dependency X on Y', "
            "'add service X', 'remove service X', or 'approve'."
        )

    return {"uncertainty": uncertainty, "revision_mutations": revision_mutations}


async def apply_revision_node(
    state: KgBootstrapState, config: RunnableConfig
) -> dict[str, Any]:
    """Node: apply verified revision mutations on top of the staged graph."""
    kg_store = config.get("configurable", {}).get("kg_store")
    revision = state.revision_mutations
    if not revision:
        return {"mutations": state.mutations}

    if kg_store is None:
        return {"errors": state.errors + ["No kg_store provided"]}

    summary = await kg_store.staging_apply(revision)
    if summary.get("errors"):
        return {
            "errors": state.errors + list(summary["errors"]),
            "mutations": state.mutations,
        }

    combined = deduplicate_mutations(state.mutations + revision)
    return {
        "mutations": combined,
        "diff_summary": evidence_summary(combined),
    }


# ── Workflow construction ──────────────────────────────────────────────────


def _build_bootstrap_workflow() -> CompiledStateGraph:
    """Build the initial-bootstrap LangGraph workflow."""
    workflow = StateGraph(KgBootstrapState)
    workflow.add_node("discover_targets", discover_targets_node)
    workflow.add_node("extract_facts", extract_facts_node)
    workflow.add_node("build_mutations", build_mutations_node)
    workflow.add_node("validate_mutations", validate_mutations_node)
    workflow.add_node("stage_graph", stage_graph_node)
    workflow.add_node("summarize", summarize_node)

    workflow.set_entry_point("discover_targets")
    workflow.add_edge("discover_targets", "extract_facts")
    workflow.add_edge("extract_facts", "build_mutations")
    workflow.add_edge("build_mutations", "validate_mutations")
    workflow.add_edge("validate_mutations", "stage_graph")
    workflow.add_edge("stage_graph", "summarize")
    workflow.add_edge("summarize", END)
    return workflow.compile()


def _build_feedback_workflow() -> CompiledStateGraph:
    """Build the feedback-revision LangGraph workflow."""
    workflow = StateGraph(KgBootstrapState)
    workflow.add_node("parse_feedback", parse_feedback_node)
    workflow.add_node("resolve_entities", resolve_entities_node)
    workflow.add_node("verify_claims", verify_claims_node)
    workflow.add_node("apply_revision", apply_revision_node)

    workflow.set_entry_point("parse_feedback")
    workflow.add_edge("parse_feedback", "resolve_entities")
    workflow.add_edge("resolve_entities", "verify_claims")
    workflow.add_edge("verify_claims", "apply_revision")
    workflow.add_edge("apply_revision", END)
    return workflow.compile()


_bootstrap_graph = _build_bootstrap_workflow()
_feedback_graph = _build_feedback_workflow()


# ── Public entrypoints ─────────────────────────────────────────────────────


async def run_kg_bootstrap(
    kg_store: Any,
    mcp_client: Any,
    config: Optional[AgentSettings] = None,
    source: Optional[str] = None,
    org: Optional[str] = None,
    repo: Optional[str] = None,
    progress_callback: Optional[
        Union[Callable[[dict[str, Any]], Any], Callable[[dict[str, Any]], Any]]
    ] = None,
) -> KgBootstrapState:
    """Execute the KG bootstrap workflow end-to-end.

    Reads the codebase via the repo_intelligence MCP server, builds
    evidence-carrying mutations, and stages the graph for human review.

    Args:
        kg_store: KnowledgeGraphStore with staging methods.
        mcp_client: Initialized in-process MCP client.
        config: Agent settings (defaults to the singleton).
        source: 'github_org', 'github_repo', or 'services_json'.
        org: GitHub org when source == 'github_org'.
        repo: Repo slug when source == 'github_repo'.
        progress_callback: Optional sync or async progress event receiver.

    Returns:
        Final KgBootstrapState including mutations and diff_summary.
    """
    agent_config = config or agent_settings
    source = source or agent_config.KG_BOOTSTRAP_SOURCE
    org = org or agent_config.KG_BOOTSTRAP_ORG or ""
    repo = repo or agent_config.KG_BOOTSTRAP_REPO or ""

    initial = KgBootstrapState(
        architecture_type=agent_config.KG_BOOTSTRAP_ARCHITECTURE,
        source=source,
        org=org,
        repo=repo,
        owner_team=agent_config.KG_BOOTSTRAP_OWNER_TEAM,
    )

    run_id = "kg-bootstrap"
    run_config: RunnableConfig = {
        "configurable": {
            "progress_callback": progress_callback,
            "run_id": run_id,
            "kg_store": kg_store,
            "mcp_client": mcp_client,
            "agent_config": agent_config,
        }
    }

    result = await _bootstrap_graph.ainvoke(
        initial.model_dump(), config=run_config
    )
    return KgBootstrapState.model_validate(result)


async def apply_feedback_revision(
    kg_store: Any,
    mcp_client: Any,
    feedback_text: str,
    parent_state: KgBootstrapState,
    config: Optional[AgentSettings] = None,
    progress_callback: Optional[
        Union[Callable[[dict[str, Any]], Any], Callable[[dict[str, Any]], Any]]
    ] = None,
) -> KgBootstrapState:
    """Apply free-text reviewer feedback to the staged graph.

    Parses intent + entities, resolves them deterministically, verifies
    claims via targeted MCP re-reads, and stages only verified revisions.

    Returns:
        Updated KgBootstrapState with combined mutations.
    """
    agent_config = config or agent_settings
    revision_state = parent_state.model_copy(
        update={"feedback_text": feedback_text}
    )

    run_config: RunnableConfig = {
        "configurable": {
            "progress_callback": progress_callback,
            "run_id": parent_state.proposal_id or "kg-bootstrap",
            "kg_store": kg_store,
            "mcp_client": mcp_client,
            "agent_config": agent_config,
        }
    }

    result = await _feedback_graph.ainvoke(
        revision_state.model_dump(), config=run_config
    )
    return KgBootstrapState.model_validate(result)


# ── Internal helpers ───────────────────────────────────────────────────────


def _load_services_fixture(path: Path) -> dict[str, Any]:
    """Load the services.json fixture deterministically."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _repo_for_service(
    extracted: dict[str, dict[str, Any]], service_id: str
) -> str:
    """Return the repo slug for a service id from extracted facts."""
    facts = extracted.get(service_id, {})
    return facts.get("repo", "")


async def _repo_exists(
    mcp_client: Any,
    run_id: str,
    state: KgBootstrapState,
    repo_name: str,
) -> bool:
    """Check whether a repo name exists in the target org via MCP."""
    if not state.org:
        return False
    result = await _call_repo_tool(
        mcp_client,
        run_id,
        "list_repositories",
        {"org": state.org},
    )
    if not result:
        return False
    normalized = normalize_node_id(repo_name)
    for repo in result:
        slug = repo.get("repo", "")
        if normalize_node_id(derive_service_id(slug)) == normalized:
            return True
    return False
