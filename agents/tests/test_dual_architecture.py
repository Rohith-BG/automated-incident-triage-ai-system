"""
Unit tests for dual architecture support.

Validates:
- InvestigationState carries architecture_type and entry_point fields
- _extract_module_entry_point helper extracts dotted paths
- KG blast radius works for both microservice and monolith module nodes
"""

import pytest

from agents.orchestrator.graph import _extract_module_entry_point
from agents.orchestrator.state import InvestigationState


class TestInvestigationStateArchitecture:
    """InvestigationState dual architecture fields."""

    def test_default_architecture_type(self) -> None:
        state = InvestigationState(
            incident_id="inc-1",
            service_id="cart-service",
            alert_message="High error rate",
        )
        assert state.architecture_type == "microservice"
        assert state.entry_point == ""

    def test_monolith_architecture_type(self) -> None:
        state = InvestigationState(
            incident_id="inc-2",
            service_id="monolith-app",
            alert_message="Error in payments.stripe_client",
            architecture_type="monolith",
            entry_point="payments.stripe_client",
        )
        assert state.architecture_type == "monolith"
        assert state.entry_point == "payments.stripe_client"


class TestModuleEntryPointExtraction:
    """_extract_module_entry_point regex helper."""

    def test_extracts_dotted_module(self) -> None:
        msg = "Error in payments.stripe_client: connection timeout"
        assert _extract_module_entry_point(msg, "fallback") == "payments.stripe_client"

    def test_extracts_deep_module(self) -> None:
        msg = "NullPointerException at com.app.checkout.views.CartController"
        assert _extract_module_entry_point(msg, "fallback") == "com.app.checkout.views.CartController"

    def test_fallback_when_no_module(self) -> None:
        msg = "Redis connection refused ECONNREFUSED"
        assert _extract_module_entry_point(msg, "cart-service") == "cart-service"

    def test_first_match_returned(self) -> None:
        msg = "auth.middleware failed, also payments.client"
        assert _extract_module_entry_point(msg, "x") == "auth.middleware"


@pytest.mark.asyncio
async def test_in_memory_kg_monolith_module_blast_radius() -> None:
    """InMemoryGraphStore blast radius works for module-level nodes."""
    from agents.knowledge_graph.in_memory import InMemoryGraphStore
    from agents.config import agent_settings

    store = InMemoryGraphStore(agent_settings.SERVICES_JSON_PATH)

    # Add monolith module nodes
    await store.add_node("payments.stripe_client", {
        "owner_team": "payments-team",
        "dependencies": ["payments.db_client"],
        "architecture_type": "monolith",
    })
    await store.add_node("payments.db_client", {
        "owner_team": "payments-team",
        "dependencies": [],
        "architecture_type": "monolith",
    })
    await store.add_node("checkout.views", {
        "owner_team": "checkout-team",
        "dependencies": ["payments.stripe_client"],
        "architecture_type": "monolith",
    })

    # Blast radius of payments.stripe_client should include checkout.views
    blast = await store.get_blast_radius("payments.stripe_client")
    assert "payments.stripe_client" in blast
    assert "checkout.views" in blast

    # Blast radius of payments.db_client should include both
    blast_db = await store.get_blast_radius("payments.db_client")
    assert "payments.db_client" in blast_db
    assert "payments.stripe_client" in blast_db
    assert "checkout.views" in blast_db

    # Dependencies for checkout.views
    deps = await store.get_dependencies("checkout.views")
    assert "payments.stripe_client" in deps

    # architecture_type stored correctly
    info = await store.get_service_info("payments.stripe_client")
    assert info["architecture_type"] == "monolith"
