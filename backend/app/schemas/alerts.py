"""
Alert validation schemas.

Defines Pydantic request/response structures for alert webhook ingestion.
"""

from pydantic import BaseModel, Field


class AlertWebhookPayload(BaseModel):
    """Payload representing an alert raised by monitoring systems."""

    service_id: str = Field(
        ...,
        description="The identifier of the service raising the alert.",
        examples=["cart-service"],
    )
    alert_message: str = Field(
        ...,
        description="The detailed error message associated with the alert.",
        examples=["Redis connection lost: ECONNREFUSED 127.0.0.1:6379"],
    )


class AlertWebhookResponse(BaseModel):
    """Standard response from alert ingestion webhook."""

    success: bool = Field(
        True, description="Indicates if alert was processed successfully."
    )
    incident_id: str = Field(
        ..., description="The ID of the incident this alert is attached to."
    )
    status: str = Field(
        ..., description="The status of the incident (e.g. 'investigating')."
    )
    is_duplicate: bool = Field(
        ...,
        description="True if this alert was deduplicated and attached to an active incident.",
    )
