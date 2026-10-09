"""
Queue message contracts for background workers.

Defines Pydantic schemas for SQS alerts-queue and deployments-queue messages.
Includes CloudWatchAlarmPayload for parsing raw CloudWatch SNS alarm envelopes.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


def utc_now_naive() -> datetime:
    """Generate timezone-naive UTC timestamp."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AlertQueueMessage(BaseModel):
    """SQS Alert payload contract.

    Accepts either ``service_id`` (from internal callers who
    already know the service) or ``service_name`` (resolved from
    CloudWatch alarm metadata).  At least one must be provided.
    """

    service_id: Optional[str] = Field(
        default=None,
        description=(
            "Service identifier raising the alarm.  "
            "Required for internal/programmatic callers."
        ),
    )
    service_name: Optional[str] = Field(
        default=None,
        description=(
            "Service name extracted from CloudWatch alarm "
            "metadata.  Used when service_id is unavailable."
        ),
    )
    alert_message: str = Field(
        ...,
        description="Detailed alert error payload / message",
    )
    source: str = Field(
        default="cloudwatch",
        description="Alert source (e.g. cloudwatch, datadog, custom)",
    )
    environment: str = Field(
        default="prod",
        description="Environment scope (e.g. prod, staging)",
    )
    metric_name: Optional[str] = Field(
        default=None,
        description=(
            "Triggering metric "
            "(e.g. HTTPCode_Target_5XX_Count)"
        ),
    )
    timestamp: Optional[datetime] = Field(
        default_factory=utc_now_naive,
        description="Alert emission timestamp",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary monitor metadata for extensibility",
    )

    @model_validator(mode="after")
    def _require_service_identity(self) -> "AlertQueueMessage":
        """Ensure at least one service identifier is present."""
        if not self.service_id and not self.service_name:
            raise ValueError(
                "At least one of 'service_id' or "
                "'service_name' must be provided."
            )
        return self


# ── CloudWatch alarm envelope ───────────────────────────────


class CloudWatchTriggerDimension(BaseModel):
    """Single dimension in a CloudWatch alarm trigger."""

    name: str = Field(
        default="",
        alias="Name",
        description="Dimension name (e.g. ServiceName, TargetGroup)",
    )
    value: str = Field(
        default="",
        alias="Value",
        description="Dimension value",
    )

    model_config = {"populate_by_name": True}


class CloudWatchTrigger(BaseModel):
    """Trigger section of a CloudWatch alarm notification."""

    MetricName: str = Field(
        default="",
        description="CloudWatch metric name",
    )
    Namespace: str = Field(
        default="",
        description="Metric namespace (e.g. AWS/ECS, AWS/ApiGateway)",
    )
    Dimensions: list[CloudWatchTriggerDimension] = Field(
        default_factory=list,
        description="Metric dimensions identifying the resource",
    )
    Period: int = Field(default=300)
    Threshold: float = Field(default=0.0)
    ComparisonOperator: str = Field(default="")
    Statistic: str = Field(default="")


class CloudWatchAlarmPayload(BaseModel):
    """Parsed inner ``Message`` from a CloudWatch → SNS → SQS alarm.

    This matches the JSON structure documented in AWS docs after
    parsing the SNS envelope's ``Message`` string field.
    """

    AlarmName: str = Field(
        ...,
        description="Name assigned to the CloudWatch alarm",
    )
    AlarmDescription: Optional[str] = Field(
        default=None,
        description="Optional alarm description",
    )
    AWSAccountId: str = Field(
        default="",
        description="AWS account owning the alarm",
    )
    NewStateValue: str = Field(
        default="ALARM",
        description="New alarm state (ALARM, OK, INSUFFICIENT_DATA)",
    )
    NewStateReason: str = Field(
        default="",
        description="Human-readable reason for state change",
    )
    StateChangeTime: str = Field(
        default="",
        description="ISO timestamp of state transition",
    )
    Region: str = Field(
        default="",
        description="AWS region of the alarm",
    )
    OldStateValue: str = Field(
        default="OK",
        description="Previous alarm state",
    )
    Trigger: CloudWatchTrigger = Field(
        default_factory=CloudWatchTrigger,
        description="Trigger details including metric and dimensions",
    )

    def to_alarm_data_dict(self) -> dict[str, Any]:
        """Convert to plain dict for ServiceResolver.resolve()."""
        return self.model_dump(by_alias=True)
