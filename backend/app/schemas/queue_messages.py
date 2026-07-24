"""
Queue message contracts for background workers.

Defines Pydantic schemas for SQS alerts-queue and deployments-queue messages.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now_naive() -> datetime:
    """Generate timezone-naive UTC timestamp."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AlertQueueMessage(BaseModel):
    """SQS Alert payload contract emitted by CloudWatch / SNS to alerts-queue."""

    service_id: str = Field(..., description="Service identifier raising the alarm")
    alert_message: str = Field(..., description="Detailed alert error payload / message")
    source: str = Field(default="cloudwatch", description="Alert source (e.g. cloudwatch, datadog, custom)")
    environment: str = Field(default="prod", description="Environment scope (e.g. prod, staging)")
    metric_name: Optional[str] = Field(default=None, description="Triggering metric (e.g. HTTPCode_Target_5XX_Count)")
    timestamp: Optional[datetime] = Field(default_factory=utc_now_naive, description="Alert emission timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary monitor metadata for extensibility")
