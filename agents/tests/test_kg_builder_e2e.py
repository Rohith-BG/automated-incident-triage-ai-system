"""End-to-end tests for the KG bootstrap agent workflow."""

import pytest
import pytest_asyncio

from agents.config import AgentSettings
from agents.kg_builder.graph import (
    apply_feedback_revision,
    run_kg_bootstrap,
)
from agents.knowledge_graph.in_memory import InMemoryGraphStore
from agents.mcp_client.client import InProcessMCPClient


@pytest.fixture
def config() -> AgentSettings:
    """Dev AgentSettings using mock providers."""
    return AgentSettings(
        ENVIRONMENT="dev",
        KG_BACKEND="in_memory",
        REPO_INTELLIGENCE_BACKEND="mock",
        OBSERVABILITY_BACKEND="mock",
        DEPLOY_BACKEND="mock",
        INCIDENT_KNOWLEDGE_BACKEND="mock",
        CODE_DIFF_BACKEND="mock",
        KG_BOOTSTRAP_SOURCE="services_json",
        KG_BOOTSTRAP_ARCHITECTURE="microservice",
        KG_IN_MEMORY_START_EMPTY=False,
    )


@pytest.fixture
def store(config: AgentSettings) -> InMemoryGraphStore:
    """Fresh in-memory graph store."""
    return InMemoryGraphStore(config.SERVICES_JSON_PATH)


@pytest_asyncio.fixture
async def mcp_client(config: AgentSettings):
    """Initialized mock MCP client."""
    client = InProcessMCPClient(config)
    await client.initialize()
    yield client
    await client.shutdown()


@pytest.mark.asyncio
async def test_bootstrap_builds_staged_graph(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Bootstrap extracts fixture facts into a staged graph."""
    state = await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )

    assert state.errors == []
    assert len(state.mutations) > 0
    assert "dependency edge" in state.diff_summary

    snapshot = await store.staging_snapshot()
    node_ids = {n["id"] for n in snapshot["nodes"]}
    edges = {(e["from"], e["to"]) for e in snapshot["edges"]}

    assert "frontend" in node_ids
    assert "cart-service" in node_ids
    assert ("frontend", "cart-service") in edges


@pytest.mark.asyncio
async def test_bootstrap_never_writes_active_graph_without_approval(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Staging must not touch the active graph (Rule 26)."""
    active_before = await store.get_all_services()

    await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )

    assert await store.get_all_services() == active_before


@pytest.mark.asyncio
async def test_feedback_updates_staged_metadata(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Conversational feedback revises the staged graph via update_metadata."""
    state = await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )
    updated = await apply_feedback_revision(
        kg_store=store,
        mcp_client=mcp_client,
        feedback_text="checkout-service owner_team should be payments-team",
        parent_state=state,
        config=config,
    )

    assert updated.feedback_intent == "update_metadata"
    assert updated.uncertainty == []

    snapshot = await store.staging_snapshot()
    checkout = next(
        n for n in snapshot["nodes"] if n["id"] == "checkout-service"
    )
    assert checkout["properties"].get("owner_team") == "payments-team"


@pytest.mark.asyncio
async def test_feedback_verifies_dependency_claims(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Unverifiable dependency claims are skipped, not fabricated."""
    state = await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )
    updated = await apply_feedback_revision(
        kg_store=store,
        mcp_client=mcp_client,
        feedback_text="frontend depends on email-service",
        parent_state=state,
        config=config,
    )

    # email-service is not a frontend dependency in the fixture,
    # so the claim cannot be verified and must be reported, not applied.
    assert any("could not be verified" in u for u in updated.uncertainty)
    snapshot = await store.staging_snapshot()
    edges = {(e["from"], e["to"]) for e in snapshot["edges"]}
    assert ("frontend", "email-service") not in edges


@pytest.mark.asyncio
async def test_unknown_feedback_asks_for_clarification(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Unrecognized feedback yields an ask-when-unsure uncertainty note."""
    state = await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )
    updated = await apply_feedback_revision(
        kg_store=store,
        mcp_client=mcp_client,
        feedback_text="hmm i am not sure about this",
        parent_state=state,
        config=config,
    )
    assert any("not recognized" in u for u in updated.uncertainty)


@pytest.mark.asyncio
async def test_feedback_removes_staged_node(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Conversational feedback removes a staged service via remove_node."""
    state = await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )
    before = await store.staging_snapshot()
    assert any(n["id"] == "load-generator" for n in before["nodes"])

    updated = await apply_feedback_revision(
        kg_store=store,
        mcp_client=mcp_client,
        feedback_text="remove the load-generator service",
        parent_state=state,
        config=config,
    )

    assert updated.feedback_intent == "remove_node"
    assert updated.uncertainty == []

    snapshot = await store.staging_snapshot()
    node_ids = {n["id"] for n in snapshot["nodes"]}
    assert "load-generator" not in node_ids


@pytest.mark.asyncio
async def test_remove_node_clears_incident_edges_in_store(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Removing a node in the active graph also drops its incident edges."""
    await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )
    await store.promote_staging()

    await store.remove_node("cart-service")
    services = await store.get_all_services()
    assert "cart-service" not in services
    for svc_id in services:
        deps = await store.get_dependencies(svc_id)
        assert "cart-service" not in deps
    dependents = await store.get_dependents("cart-service")
    assert dependents == []


@pytest.mark.asyncio
async def test_promote_staging_moves_graph_to_active(
    config: AgentSettings, store: InMemoryGraphStore, mcp_client: InProcessMCPClient
) -> None:
    """Approval (promote_staging) moves the staged graph into the active graph."""
    await run_kg_bootstrap(
        kg_store=store,
        mcp_client=mcp_client,
        config=config,
        source="services_json",
    )
    assert await store.staging_has_content()

    summary = await store.promote_staging()
    assert summary["errors"] == []

    assert await store.staging_has_content() is False
    services = await store.get_all_services()
    assert "frontend" in services
    assert "cart-service" in services
    deps = await store.get_dependencies("frontend")
    assert "cart-service" in deps
