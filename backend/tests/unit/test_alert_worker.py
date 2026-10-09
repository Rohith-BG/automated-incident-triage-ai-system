"""Unit tests for SQS AlertWorker — including CloudWatch payload handling."""

import json

import json

import pytest
import pytest_asyncio
from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.enums import IncidentStatus
from backend.app.schemas.queue_messages import AlertQueueMessage
from backend.app.workers.alert_worker import (
    AlertWorker,
    _build_alert_message_from_alarm,
    _is_cloudwatch_envelope,
    _parse_cloudwatch_envelope,
)
from backend.app.schemas.queue_messages import CloudWatchAlarmPayload


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate tables for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Existing AlertQueueMessage tests (backward compat) ──────


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
    assert res["status"] in (
        IncidentStatus.ROOT_CAUSE_IDENTIFIED.value,
        IncidentStatus.INVESTIGATING.value,
    )


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


class _FakeSQS:
    """In-memory SQS double recording send/delete calls."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    async def send_message(self, QueueUrl: str, MessageBody: str) -> None:
        self.sent.append((QueueUrl, MessageBody))

    async def delete_message(self, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)


@pytest.mark.asyncio
async def test_alert_worker_routes_poison_message_to_dlq() -> None:
    """A malformed SQS payload is forwarded to the DLQ and deleted (Rule 10)."""
    worker = AlertWorker(
        session_factory=AsyncSessionLocal,
        queue_url="https://sqs/alerts",
        dlq_url="https://sqs/alerts-dlq",
    )
    fake = _FakeSQS()
    body = json.dumps({"service_id": "missing-alert-message"})

    await worker._send_to_dlq(fake, body, "receipt-1")

    assert fake.sent == [("https://sqs/alerts-dlq", body)]
    assert fake.deleted == ["receipt-1"]


@pytest.mark.asyncio
async def test_alert_worker_skips_dlq_when_unconfigured() -> None:
    """Without a DLQ URL, poison messages are left to the visibility timeout."""
    worker = AlertWorker(session_factory=AsyncSessionLocal)
    fake = _FakeSQS()

    await worker._send_to_dlq(fake, "{}", "receipt-1")

    assert fake.sent == []
    assert fake.deleted == []


# ── CloudWatch envelope detection ───────────────────────────


def test_is_cloudwatch_direct_alarm() -> None:
    """Direct CloudWatch alarm JSON is detected."""
    data = {"AlarmName": "my-alarm", "Trigger": {}}
    assert _is_cloudwatch_envelope(data) is True


def test_is_cloudwatch_sns_envelope() -> None:
    """SNS-wrapped CloudWatch alarm is detected."""
    data = {
        "Type": "Notification",
        "Message": '{"AlarmName": "my-alarm"}',
    }
    assert _is_cloudwatch_envelope(data) is True


def test_is_not_cloudwatch_internal_message() -> None:
    """Internal AlertQueueMessage is not mis-detected as CloudWatch."""
    data = {
        "service_id": "cart-service",
        "alert_message": "test",
    }
    assert _is_cloudwatch_envelope(data) is False


# ── CloudWatch envelope parsing ─────────────────────────────


def test_parse_sns_envelope() -> None:
    """SNS envelope Message string is unwrapped to alarm dict."""
    inner = {"AlarmName": "test-alarm", "NewStateValue": "ALARM"}
    raw = {
        "Type": "Notification",
        "Message": json.dumps(inner),
    }
    result = _parse_cloudwatch_envelope(raw)
    assert result["AlarmName"] == "test-alarm"


def test_parse_direct_alarm() -> None:
    """Direct alarm payload passes through unchanged."""
    raw = {"AlarmName": "test-alarm", "Trigger": {}}
    result = _parse_cloudwatch_envelope(raw)
    assert result is raw  # same object, no copy


# ── Alert message construction ──────────────────────────────


def test_build_alert_message_basic() -> None:
    alarm = CloudWatchAlarmPayload(
        AlarmName="cart-service-5xx-alarm",
        AlarmDescription="High 5xx rate on cart-service",
        NewStateReason="Threshold Crossed: 15 > 10",
        Trigger={
            "MetricName": "HTTPCode_Target_5XX_Count",
            "Namespace": "AWS/ApplicationELB",
        },
    )
    msg = _build_alert_message_from_alarm(alarm)
    assert "cart-service-5xx-alarm" in msg
    assert "High 5xx rate" in msg
    assert "Threshold Crossed" in msg
    assert "HTTPCode_Target_5XX_Count" in msg


def test_build_alert_message_no_description() -> None:
    alarm = CloudWatchAlarmPayload(
        AlarmName="alarm-xyz",
        NewStateReason="Threshold crossed",
    )
    msg = _build_alert_message_from_alarm(alarm)
    assert "alarm-xyz" in msg
    assert "Threshold crossed" in msg


# ── AlertQueueMessage backward compatibility ────────────────


def test_alert_queue_message_with_service_id_only() -> None:
    """Legacy callers with service_id continue to work."""
    msg = AlertQueueMessage(
        service_id="cart-service",
        alert_message="test error",
    )
    assert msg.service_id == "cart-service"


def test_alert_queue_message_with_service_name_only() -> None:
    """CloudWatch-resolved path with service_name only."""
    msg = AlertQueueMessage(
        service_name="cart-service",
        alert_message="test error",
    )
    assert msg.service_name == "cart-service"
    assert msg.service_id is None


def test_alert_queue_message_requires_at_least_one() -> None:
    """Validation fails if neither service_id nor service_name."""
    with pytest.raises(ValueError, match="service_id"):
        AlertQueueMessage(alert_message="test error")


# ── CloudWatchAlarmPayload parsing ──────────────────────────


def test_cloudwatch_payload_parses_full_alarm() -> None:
    raw = {
        "AlarmName": "cart-service-5xx-alarm",
        "AlarmDescription": "High 5xx rate",
        "AWSAccountId": "123456789012",
        "NewStateValue": "ALARM",
        "NewStateReason": "Threshold Crossed",
        "StateChangeTime": "2026-10-01T12:00:00.000+0000",
        "Region": "us-east-1",
        "OldStateValue": "OK",
        "Trigger": {
            "MetricName": "HTTPCode_Target_5XX_Count",
            "Namespace": "AWS/ApplicationELB",
            "Dimensions": [
                {
                    "name": "TargetGroup",
                    "value": "tg/cart-service/abc",
                },
            ],
            "Period": 60,
            "Threshold": 10.0,
            "ComparisonOperator": "GreaterThanThreshold",
        },
    }
    alarm = CloudWatchAlarmPayload(**raw)
    assert alarm.AlarmName == "cart-service-5xx-alarm"
    assert alarm.Trigger.Namespace == "AWS/ApplicationELB"
    assert len(alarm.Trigger.Dimensions) == 1
    assert alarm.Trigger.Dimensions[0].name == "TargetGroup"
    assert alarm.Trigger.Dimensions[0].value == "tg/cart-service/abc"


def test_cloudwatch_payload_minimal() -> None:
    """Only AlarmName is required."""
    alarm = CloudWatchAlarmPayload(AlarmName="test")
    assert alarm.AlarmName == "test"
    assert alarm.NewStateValue == "ALARM"
    assert alarm.Trigger.Dimensions == []
