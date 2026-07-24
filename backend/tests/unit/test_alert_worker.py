"""Unit test for SQS AlertWorker."""

import pytest
import pytest_asyncio
from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.schemas.queue_messages import AlertQueueMessage
from backend.app.workers.alert_worker import AlertWorker


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate tables for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_alert_worker_process_new_alert() -> None:
    """AlertWorker processes a new alert, creates incident, and runs investigation."""
    worker = AlertWorker(session_factory=AsyncSessionLocal)
    msg = AlertQueueMessage(
        service_id="payment-service",
        alert_message="Redis connection failure: ECONNREFUSED",
    )

    res = await worker.process_alert(msg)
    assert res["is_duplicate"] is False
    assert res["incident_id"] is not None
    assert res["status"] in ("root_cause_identified", "investigating")


@pytest.mark.asyncio
async def test_alert_worker_deduplicates_active_incident() -> None:
    """AlertWorker attaches alert to active incident if already investigating (Rule 13)."""
    worker = AlertWorker(session_factory=AsyncSessionLocal)
    msg1 = AlertQueueMessage(
        service_id="cart-service",
        alert_message="High error rate 500",
    )
    res1 = await worker.process_alert(msg1)
    assert res1["is_duplicate"] is False

    msg2 = AlertQueueMessage(
        service_id="cart-service",
        alert_message="Duplicate High error rate 500",
    )
    res2 = await worker.process_alert(msg2)
    assert res2["is_duplicate"] is True
    assert res2["incident_id"] == res1["incident_id"]
