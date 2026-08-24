"""Unit tests for the KG bootstrap agent modules."""

from agents.kg_builder.entity_resolver import build_inventory, resolve_entity
from agents.kg_builder.feedback_parser import parse_feedback
from agents.kg_builder.mutations import (
    build_add_dependency_mutation,
    build_add_node_mutation,
    build_remove_node_mutation,
    deduplicate_mutations,
    normalize_node_id,
    validate_mutations,
)


# ── Mutations ─────────────────────────────────────────────


class TestMutationBuilder:
    def test_build_add_node_mutation_carries_evidence(self) -> None:
        mutation = build_add_node_mutation(
            node_id="cart-service",
            metadata={"owner_team": "cart-team", "language": "C#"},
            evidence="googlecloudplatform/microservices-demo:cart-service",
        )
        assert mutation["action"] == "add_node"
        assert mutation["node"] == "cart-service"
        assert mutation["metadata"]["evidence"] == (
            "googlecloudplatform/microservices-demo:cart-service"
        )

    def test_build_add_dependency_mutation(self) -> None:
        mutation = build_add_dependency_mutation(
            from_id="frontend",
            to_id="cart-service",
            evidence="docker-compose.yml:services.frontend.depends_on",
        )
        assert mutation["action"] == "add_dependency"
        assert mutation["from"] == "frontend"
        assert mutation["to"] == "cart-service"

    def test_build_remove_node_mutation(self) -> None:
        mutation = build_remove_node_mutation(
            node_id="cart-service",
            evidence="reviewer-feedback",
        )
        assert mutation["action"] == "remove_node"
        assert mutation["node"] == "cart-service"
        assert mutation["evidence"] == "reviewer-feedback"

    def test_normalize_node_id(self) -> None:
        assert normalize_node_id("Cart Service") == "cart"
        assert normalize_node_id("cart_service") == "cart"
        assert normalize_node_id("cart-service") == "cart"
        assert normalize_node_id("frontend") == "frontend"


class TestValidateMutations:
    def test_valid_mutations_pass(self) -> None:
        valid, dropped = validate_mutations(
            [
                build_add_node_mutation(
                    "cart-service", {"owner_team": "cart-team"}, "repo:path"
                ),
                build_add_dependency_mutation(
                    "frontend", "cart-service", "repo:compose"
                ),
            ]
        )
        assert len(valid) == 2
        assert dropped == []

    def test_add_node_evidence_from_metadata(self) -> None:
        mutation = build_add_node_mutation(
            "cart-service", {"owner_team": "cart-team"}, "repo:path"
        )
        mutation.pop("evidence", None)  # evidence lives in metadata
        valid, dropped = validate_mutations([mutation])
        assert len(valid) == 1
        assert dropped == []

    def test_missing_evidence_dropped(self) -> None:
        valid, dropped = validate_mutations(
            [{"action": "add_dependency", "from": "a", "to": "b"}]
        )
        assert valid == []
        assert len(dropped) == 1
        assert "Missing evidence" in dropped[0]

    def test_unknown_action_dropped(self) -> None:
        valid, dropped = validate_mutations(
            [{"action": "explode", "evidence": "x"}]
        )
        assert valid == []
        assert "Unsupported action" in dropped[0]

    def test_remove_node_missing_node_dropped(self) -> None:
        valid, dropped = validate_mutations(
            [{"action": "remove_node", "evidence": "reviewer-feedback"}]
        )
        assert valid == []
        assert "Invalid remove_node" in dropped[0]

    def test_remove_node_valid_with_evidence(self) -> None:
        mutation = build_remove_node_mutation("cart-service", "reviewer-feedback")
        valid, dropped = validate_mutations([mutation])
        assert len(valid) == 1
        assert dropped == []

    def test_deduplicate_mutations(self) -> None:
        mutations = [
            build_add_dependency_mutation("a", "b", "e1"),
            build_add_dependency_mutation("a", "b", "e2"),
        ]
        deduped = deduplicate_mutations(mutations)
        assert len(deduped) == 1
        assert deduped[0]["evidence"] == "e2"


# ── Entity resolver ───────────────────────────────────────


class TestEntityResolver:
    INVENTORY = [
        "frontend",
        "cart-service",
        "product-catalog-service",
        "checkout-service",
    ]

    def test_exact_match(self) -> None:
        result = resolve_entity("cart-service", self.INVENTORY)
        assert result["resolved"] is True
        assert result["match"] == "cart-service"

    def test_normalized_match(self) -> None:
        result = resolve_entity("Cart Service", self.INVENTORY)
        assert result["resolved"] is True
        assert result["match"] == "cart-service"

    def test_unresolved(self) -> None:
        result = resolve_entity("mystery-app", self.INVENTORY)
        assert result["resolved"] is False
        assert result["match"] is None

    def test_build_inventory_dedupes(self) -> None:
        inventory = build_inventory(
            active_services=["frontend", "cart-service"],
            staged_nodes=[{"id": "checkout-service"}, {"id": "cart-service"}],
            extra=["frontend"],
        )
        assert inventory == [
            "cart-service",
            "checkout-service",
            "frontend",
        ]


# ── Feedback parser ───────────────────────────────────────


class TestFeedbackParser:
    def test_approve_intent(self) -> None:
        parse = parse_feedback("Looks good, approve it")
        assert parse.intent == "approve"

    def test_reject_intent(self) -> None:
        parse = parse_feedback("No, this is wrong. Reject it")
        assert parse.intent == "reject"

    def test_add_dependency_intent(self) -> None:
        parse = parse_feedback("frontend depends on checkout-service")
        assert parse.intent == "add_dependency"
        assert "frontend" in parse.entities
        assert "checkout-service" in parse.entities

    def test_remove_dependency_intent_not_confused_with_add(self) -> None:
        parse = parse_feedback("cart-service does not depend on product-catalog-service")
        assert parse.intent == "remove_dependency"

    def test_remove_node_intent_with_named_service(self) -> None:
        parse = parse_feedback("remove the load-generator service")
        assert parse.intent == "remove_node"
        assert "load-generator" in parse.entities

    def test_update_metadata_intent(self) -> None:
        parse = parse_feedback("cart-service owner_team should be cart-team")
        assert parse.intent == "update_metadata"
        assert parse.metadata_updates.get("owner_team") == "cart-team"

    def test_unknown_intent(self) -> None:
        parse = parse_feedback("hello there, how are you")
        assert parse.intent == "unknown"
