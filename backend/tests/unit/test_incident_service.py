"""Unit tests for IncidentService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.enums import IncidentStatus
from backend.app.exceptions import NotFoundException
from backend.app.services.incident import IncidentService


def _make_incident(
    incident_id: str = "inc-1",
    service_id: str = "cart-service",
    status: str = IncidentStatus.INVESTIGATING,
) -> MagicMock:
    """Create a mock Incident object."""
    inc = MagicMock()
    inc.id = incident_id
    inc.service_id = service_id
    inc.status = status
    inc.alerts = []
    inc.report = None
    inc.resolution = None
    return inc


def _make_alert(
    alert_id: str = "alert-1",
    incident_id: str = "inc-1",
) -> MagicMock:
    """Create a mock Alert object."""
    alert = MagicMock()
    alert.id = alert_id
    alert.incident_id = incident_id
    return alert


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provide a fully-mocked IncidentRepository."""
    return AsyncMock()


@pytest.fixture
def service(mock_repo: AsyncMock) -> IncidentService:
    """Provide an IncidentService with a mocked repository."""
    return IncidentService(repository=mock_repo)


@pytest.mark.asyncio
async def test_ingest_alert_creates_new_incident(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """When no active incident exists, a new one is created."""
    mock_repo.find_active_by_service.return_value = None
    new_inc = _make_incident()
    mock_repo.create.return_value = new_inc
    mock_repo.attach_alert.return_value = _make_alert()

    incident, is_new = await service.ingest_alert(
        "cart-service", "Redis ECONNREFUSED"
    )

    assert is_new is True
    assert incident.id == "inc-1"
    mock_repo.create.assert_called_once_with("cart-service")
    mock_repo.attach_alert.assert_called_once_with(
        incident_id="inc-1",
        alert_message="Redis ECONNREFUSED",
    )


@pytest.mark.asyncio
async def test_ingest_alert_deduplicates(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """When an active incident exists, alert attaches to it."""
    active = _make_incident(incident_id="existing-inc")
    mock_repo.find_active_by_service.return_value = active
    mock_repo.attach_alert.return_value = _make_alert()

    incident, is_new = await service.ingest_alert(
        "cart-service", "Redis timeout"
    )

    assert is_new is False
    assert incident.id == "existing-inc"
    mock_repo.create.assert_not_called()
    mock_repo.attach_alert.assert_called_once_with(
        incident_id="existing-inc",
        alert_message="Redis timeout",
    )


@pytest.mark.asyncio
async def test_get_incident_found(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """get_incident() returns the incident when found."""
    inc = _make_incident()
    mock_repo.get_by_id.return_value = inc

    result = await service.get_incident("inc-1")
    assert result.id == "inc-1"


@pytest.mark.asyncio
async def test_get_incident_not_found(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """get_incident() raises NotFoundException for unknown IDs."""
    mock_repo.get_by_id.return_value = None

    with pytest.raises(NotFoundException):
        await service.get_incident("nonexistent")


@pytest.mark.asyncio
async def test_list_incidents(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """list_incidents() delegates to repo.list_all()."""
    incs = [_make_incident(), _make_incident(incident_id="inc-2")]
    mock_repo.list_all.return_value = (incs, "cursor-abc", True)

    result, next_cursor, has_more = await service.list_incidents(
        limit=20
    )
    assert len(result) == 2
    assert next_cursor == "cursor-abc"
    assert has_more is True
    mock_repo.list_all.assert_called_once_with(
        limit=20, cursor=None, service_id=None, status=None
    )


@pytest.mark.asyncio
async def test_complete_investigation(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """complete_investigation() saves report and updates status."""
    report = MagicMock()
    report.root_cause = "Redis crashed"
    report.evidence_summary = "ECONNREFUSED"
    report.affected_services = ["cart-service"]
    report.remediation_steps = ["Restart Redis"]
    report.confidence_score = 0.92

    await service.complete_investigation("inc-1", report)

    mock_repo.save_report.assert_called_once_with(
        incident_id="inc-1",
        root_cause="Redis crashed",
        evidence_summary="ECONNREFUSED",
        affected_services=["cart-service"],
        remediation_steps=["Restart Redis"],
        confidence_score=0.92,
    )
    mock_repo.update_status.assert_called_once_with(
        "inc-1", IncidentStatus.COMPLETED
    )


@pytest.mark.asyncio
async def test_fail_investigation(
    service: IncidentService, mock_repo: AsyncMock
) -> None:
    """fail_investigation() updates status to FAILED."""
    await service.fail_investigation("inc-1", "Orchestrator error")

    mock_repo.update_status.assert_called_once_with(
        "inc-1", IncidentStatus.FAILED
    )
