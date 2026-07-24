"""
Pydantic schemas for service registry.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ServiceRegistryCreate(BaseModel):
    """Request schema for registering a service."""

    service_id: str = Field(..., min_length=1, max_length=100)
    repo: str = Field(..., min_length=1, max_length=255)
    architecture_type: str = Field(default="microservice", max_length=50)
    owner_team: str = Field(..., min_length=1, max_length=100)
    language: Optional[str] = Field(default=None, max_length=50)
    alert_threshold: str = Field(default="medium", max_length=20)


class ServiceRegistryUpdate(BaseModel):
    """Request schema for updating a service."""

    repo: Optional[str] = Field(default=None, max_length=255)
    architecture_type: Optional[str] = Field(default=None, max_length=50)
    owner_team: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, max_length=50)
    alert_threshold: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None


class ServiceRegistryResponse(BaseModel):
    """Response schema for a registered service."""

    id: str
    service_id: str
    repo: str
    architecture_type: str
    owner_team: str
    language: Optional[str]
    alert_threshold: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
