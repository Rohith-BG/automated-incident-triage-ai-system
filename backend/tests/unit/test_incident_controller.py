"""Unit tests for IncidentController."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from backend.app.controllers.incident import IncidentController
from backend.app.enums import IncidentStatus
from backend.app.schemas.incidents import IngestAlertRequest


def _make_incident(
    incident_id: str = "inc-1",
    service_id: str = "cart-service",
    status: str = IncidentStatus.INVESTIGATING,
    alerts: list | None = None,
    report: object | None = None,
) -> MagicMock:
    """Create a mock Incident with required attributes."""
    inc = MagicMock()
    inc.id = incident_id
    inc.service_id = service_id
    inc.status = status
    inc.created_at = datetime(2026, 7, 13, 10, 0, 0)
    inc.updated_at = datetime(2026, 7, 13, 10, 5, 0)
    inc.alerts = alerts or []
    inc.report = report
    inc.resolution = None
    return inc


def _make_alert(
    alert_id: str = "alert-1",
    incident_id: str = "inc-1",
    message: str = "Redis ECONNREFUSED",
) -> MagicMock:
    """Create a mock Alert."""
    alert = MagicMock()
    alert.id = alert_id
    alert.incident_id = incident_id
    alert.alert_message = message
    alert.created_at = datetime(2026, 7, 13, 10, 0, 0)
    return alert


def _make_report(
    report_id: str = "rpt-1",
    confidence: float = 0.92,
) -> MagicMock:
    """Create a mock RootCauseReportModel."""
    rpt = MagicMock()
    rpt.id = report_id
    rpt.root_cause = "Redis crashed"
    rpt.evidence_summary = "ECONNREFUSED in logs"
    rpt.affected_services = ["cart-service"]
    rpt.remediation_steps = ["Restart Redis"]
    rpt.confidence_score = confidence
    rpt.created_at = datetime(2026, 7, 13, 10, 5, 0)
    return rpt


@pytest.fixture
def mock_service() -> AsyncMock:
    """Provide a mocked IncidentService."""
    return AsyncMock()


@pytest.fixture
def controller(mock_service: AsyncMock) -> IncidentController:
    """Provide an IncidentController with a mocked service."""
    return IncidentController(service=mock_service)


@pytest.mark.asyncio
async def test_ingest_alert_new(
    controller: IncidentController, mock_service: AsyncMock
) -> None:
    """ingest_alert() returns is_new=True for new incidents."""
    mock_service.ingest_alert.return_value = (
        _make_incident(),
        True,
    )

    payload = IngestAlertRequest(
        service_id="cart-service",
        alert_message="Redis ECONNREFUSED",
    )
    response = await controller.ingest_alert(payload)

    assert response.incident_id == "inc-1"
    assert response.is_new is True
    assert response.status == IncidentStatus.INVESTIGATING


@pytest.mark.asyncio
async def test_ingest_alert_duplicate(
    controller: IncidentController, mock_service: AsyncMock
) -> None:
    """ingest_alert() returns is_new=False for deduped alerts."""
    mock_service.ingest_alert.return_value = (
        _make_incident(),
        False,
    )

    payload = IngestAlertRequest(
        service_id="cart-service",
        alert_message="Redis timeout",
    )
    response = await controller.ingest_alert(payload)

    assert response.is_new is False


@pytest.mark.asyncio
async def test_get_incident_with_report(
    controller: IncidentController, mock_service: AsyncMock
) -> None:
    """get_incident() returns full detail including report."""
    alert = _make_alert()
    report = _make_report()
    incident = _make_incident(
        alerts=[alert], report=report
    )
    mock_service.get_incident.return_value = incident

    response = await controller.get_incident("inc-1")

    assert response.id == "inc-1"
    assert len(response.alerts) == 1
    assert response.alerts[0].alert_message == "Redis ECONNREFUSED"
    assert response.report is not None
    assert response.report.confidence_score == 0.92


@pytest.mark.asyncio
async def test_get_incident_without_report(
    controller: IncidentController, mock_service: AsyncMock
) -> None:
    """get_incident() returns detail with report=None when absent."""
    incident = _make_incident()
    mock_service.get_incident.return_value = incident

    response = await controller.get_incident("inc-1")

    assert response.report is None
    assert response.alerts == []


@pytest.mark.asyncio
async def test_list_incidents(
    controller: IncidentController, mock_service: AsyncMock
) -> None:
    """list_incidents() returns cursor-paginated response."""
    incs = [
        _make_incident(incident_id="inc-1"),
        _make_incident(incident_id="inc-2"),
    ]
    mock_service.list_incidents.return_value = (
        incs, "cursor-xyz", True
    )

    response = await controller.list_incidents(limit=20)

    assert len(response.items) == 2
    assert response.has_more is True
    assert response.next_cursor == "cursor-xyz"
    assert response.limit == 20


@pytest.mark.asyncio
async def test_list_incidents_summary_includes_alert_count(
    controller: IncidentController, mock_service: AsyncMock
) -> None:
    """list_incidents() summary items include alert_count."""
    alerts = [_make_alert(), _make_alert(alert_id="alert-2")]
    inc = _make_incident(alerts=alerts)
    mock_service.list_incidents.return_value = (
        [inc], None, False
    )

    response = await controller.list_incidents()

    assert response.items[0].alert_count == 2
