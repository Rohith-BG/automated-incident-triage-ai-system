"""Regression tests for incidents wedged in INVESTIGATING.

An incident stuck in INVESTIGATING is not cosmetic: INVESTIGATING is an
active status, so ``find_active_by_service`` keeps matching it and the
service can never raise a fresh incident again. These tests pin the
guarantee that the background orchestrator always reaches a terminal
status, even when report persistence fails.
"""

import asyncio
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError

from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.enums import IncidentStatus
from backend.app.repositories.incident import IncidentRepository
from backend.app.routes import incidents as incidents_route


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate tables for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _new_incident(service_id: str) -> str:
    """Create an INVESTIGATING incident with one alert attached."""
    async with AsyncSessionLocal() as session:
        repo = IncidentRepository(session=session)
        incident = await repo.create(service_id)
        await repo.attach_alert(incident.id, "boom")
        await session.commit()
        return str(incident.id)


async def _status_of(incident_id: str) -> str | None:
    """Read an incident's status straight from the database."""
    async with AsyncSessionLocal() as session:
        repo = IncidentRepository(session=session)
        incident = await repo.get_by_id(incident_id)
        return incident.status if incident else None


class _FakeReport:
    """Minimal stand-in for the orchestrator's RootCauseReport."""

    root_cause = "dependency timeout"
    affected_services = ["frontend"]
    raw_logs = {"frontend": {"errors": "upstream returned 504"}}
    raw_metrics = {}
    observability_analysis = "upstream returned 504"
    code_diffs = {}
    past_resolutions = []
    remediation_steps = ["raise the upstream timeout"]
    confidence_score = 0.82
    uncertainty = ""


@pytest.mark.asyncio
async def test_orchestrator_task_completes_incident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A produced report moves the incident to COMPLETED."""
    incident_id = await _new_incident("svc-happy")

    class _State:
        report = _FakeReport()

    async def _fake_run(**_kwargs: Any) -> _State:
        return _State()

    monkeypatch.setattr(
        "agents.orchestrator.run_investigation", _fake_run
    )

    await incidents_route._run_orchestrator_task(
        incident_id=incident_id,
        service_id="svc-happy",
        alert_message="boom",
    )

    assert await _status_of(incident_id) == IncidentStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_report_persist_failure_still_reaches_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGRESSION: a report that cannot be written must not strand the incident.

    Reproduces the production failure where
    ``INSERT INTO root_cause_reports`` raised
    ``sqlite3.OperationalError: database is locked``. The old code caught
    that error and rolled back without ever updating the status, leaving the
    incident in INVESTIGATING forever.
    """

    class _State:
        report = _FakeReport()

    async def _fake_run(**_kwargs: Any) -> _State:
        return _State()

    monkeypatch.setattr(
        "agents.orchestrator.run_investigation", _fake_run
    )

    original_save_report = IncidentRepository.save_report
    calls: list[str] = []

    async def _always_locked(self: IncidentRepository, *a: Any, **k: Any):
        calls.append("save_report")
        raise OperationalError(
            "INSERT INTO root_cause_reports", {}, Exception("database is locked")
        )

    monkeypatch.setattr(IncidentRepository, "save_report", _always_locked)

    try:
        incident_id = await _new_incident("svc-locked")
        await incidents_route._run_orchestrator_task(
            incident_id=incident_id,
            service_id="svc-locked",
            alert_message="boom",
        )

        assert calls, "expected the failing report write to be attempted"
        assert await _status_of(incident_id) == IncidentStatus.FAILED.value
    finally:
        monkeypatch.setattr(
            IncidentRepository, "save_report", original_save_report
        )


@pytest.mark.asyncio
async def test_status_update_retries_transient_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGRESSION: the terminal status write survives a transient lock.

    The status update runs in its own session per attempt, so a lock held by
    a partially applied report insert cannot prevent the incident from
    leaving INVESTIGATING.
    """
    incident_id = await _new_incident("svc-retry")
    original_update_status = IncidentRepository.update_status
    attempts: list[int] = []

    async def _lock_once(self: IncidentRepository, *a: Any, **k: Any):
        attempts.append(1)
        if len(attempts) < 3:
            raise OperationalError(
                "UPDATE incidents", {}, Exception("database is locked")
            )
        return await original_update_status(self, *a, **k)

    monkeypatch.setattr(IncidentRepository, "update_status", _lock_once)
    monkeypatch.setattr(
        incidents_route, "_PERSIST_RETRY_BASE_DELAY_SECONDS", 0.0
    )

    try:
        applied = await incidents_route._force_terminal_status(
            incident_id, IncidentStatus.FAILED
        )
        assert applied is True
        assert len(attempts) == 3
        assert await _status_of(incident_id) == IncidentStatus.FAILED.value
    finally:
        monkeypatch.setattr(
            IncidentRepository, "update_status", original_update_status
        )


@pytest.mark.asyncio
async def test_orchestrator_exception_reaches_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crashed orchestrator marks the incident FAILED, not INVESTIGATING."""

    async def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("mcp server exploded")

    monkeypatch.setattr("agents.orchestrator.run_investigation", _boom)

    incident_id = await _new_incident("svc-crash")
    await incidents_route._run_orchestrator_task(
        incident_id=incident_id,
        service_id="svc-crash",
        alert_message="boom",
    )

    assert await _status_of(incident_id) == IncidentStatus.FAILED.value


@pytest.mark.asyncio
async def test_no_report_reaches_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An orchestrator run yielding no report marks the incident FAILED."""

    class _State:
        report = None

    async def _fake_run(**_kwargs: Any) -> _State:
        return _State()

    monkeypatch.setattr(
        "agents.orchestrator.run_investigation", _fake_run
    )

    incident_id = await _new_incident("svc-noreport")
    await incidents_route._run_orchestrator_task(
        incident_id=incident_id,
        service_id="svc-noreport",
        alert_message="boom",
    )

    assert await _status_of(incident_id) == IncidentStatus.FAILED.value


@pytest.mark.asyncio
async def test_retrigger_updates_existing_report() -> None:
    """REGRESSION: re-running an investigation does not violate the UNIQUE index.

    ``root_cause_reports.incident_id`` is UNIQUE, so an INSERT on
    re-trigger raised IntegrityError, which aborted the transaction and
    stranded the incident in INVESTIGATING.
    """
    incident_id = await _new_incident("svc-retrigger")

    async with AsyncSessionLocal() as session:
        repo = IncidentRepository(session=session)
        await repo.save_report(
            incident_id=incident_id,
            root_cause="first cause",
            affected_services=["svc-retrigger"],
            observability_analysis="first evidence",
            remediation_steps=["first fix"],
            confidence_score=0.4,
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        repo = IncidentRepository(session=session)
        report = await repo.save_report(
            incident_id=incident_id,
            root_cause="second cause",
            affected_services=["svc-retrigger"],
            observability_analysis="second evidence",
            remediation_steps=["second fix"],
            confidence_score=0.9,
        )
        await session.commit()
        assert report.root_cause == "second cause"
        assert report.confidence_score == 0.9

    async with AsyncSessionLocal() as session:
        repo = IncidentRepository(session=session)
        report = await repo.get_report(incident_id)
        assert report is not None
        assert report.root_cause == "second cause"


@pytest.mark.asyncio
async def test_terminal_incident_does_not_wedge_the_service() -> None:
    """After a terminal status the service can raise a fresh incident again."""
    incident_id = await _new_incident("svc-wedged")
    await incidents_route._force_terminal_status(
        incident_id, IncidentStatus.FAILED
    )

    async with AsyncSessionLocal() as session:
        repo = IncidentRepository(session=session)
        assert await repo.find_active_by_service("svc-wedged") is None

    second_id = await _new_incident("svc-wedged")
    assert second_id != incident_id


@pytest.mark.asyncio
async def test_concurrent_investigation_writes_do_not_lock_sqlite() -> None:
    """Concurrent status writes against SQLite all succeed (WAL + busy_timeout)."""
    incident_ids = [await _new_incident(f"svc-par-{i}") for i in range(8)]

    await asyncio.gather(
        *[
            incidents_route._force_terminal_status(
                iid, IncidentStatus.COMPLETED
            )
            for iid in incident_ids
        ]
    )

    statuses = [await _status_of(iid) for iid in incident_ids]
    assert statuses == [IncidentStatus.COMPLETED.value] * len(incident_ids)