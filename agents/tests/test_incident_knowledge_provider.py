"""Unit tests for the MockIncidentKnowledgeProvider."""

import pytest
from agents.mcp_servers.incident_knowledge.mock import MockIncidentKnowledgeProvider


@pytest.fixture
def provider() -> MockIncidentKnowledgeProvider:
    """Provide a MockIncidentKnowledgeProvider."""
    return MockIncidentKnowledgeProvider()


@pytest.mark.asyncio
async def test_search_incident_knowledge(provider: MockIncidentKnowledgeProvider) -> None:
    """search_incident_knowledge() finds matching playbooks."""
    books = await provider.search_incident_knowledge("payment-service", error_type="stripe_api_timeout")
    assert len(books) == 1
    assert books[0]["id"] == "rb-1"
    assert "Stripe" in books[0]["title"]


@pytest.mark.asyncio
async def test_get_incident_knowledge(provider: MockIncidentKnowledgeProvider) -> None:
    """get_incident_knowledge() fetches detail by ID."""
    book = await provider.get_incident_knowledge("rb-2")
    assert book is not None
    assert book["title"] == "Redis cache pool exhaustion"


@pytest.mark.asyncio
async def test_get_past_resolutions(provider: MockIncidentKnowledgeProvider) -> None:
    """get_past_resolutions() returns resolutions for service."""
    res = await provider.get_past_resolutions("payment-service")
    assert len(res) == 1
    assert res[0]["incident_id"] == "inc-99"


@pytest.mark.asyncio
async def test_get_similar_incidents(provider: MockIncidentKnowledgeProvider) -> None:
    """get_similar_incidents() returns completed similar incidents."""
    incidents = await provider.get_similar_incidents("payment-service")
    assert len(incidents) == 1
    assert incidents[0]["id"] == "inc-99"
    assert incidents[0]["status"] == "completed"
