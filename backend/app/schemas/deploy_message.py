"""
Pydantic schema for the SQS deploy message contract.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeployMessage(BaseModel):
    """Schema matching the CI/CD pipeline SQS message contract.

    Reference: implementation_plan.md §1 — CI/CD Pipeline Contract.
    """

    service_id: str = Field(..., min_length=1, max_length=100)
    commit_sha: str = Field(..., min_length=7, max_length=64)
    repo: str = Field(..., min_length=1, max_length=255)
    branch: str = Field(..., min_length=1, max_length=200)
    pr_number: Optional[int] = None
    author: str = Field(..., min_length=1, max_length=255)
    deployed_at: datetime
    environment: str = Field(..., min_length=1, max_length=50)
    architecture_type: str = Field(
        ..., min_length=1, max_length=50,
        description="microservice, monolith, or module",
    )
    component_id: str = Field(..., min_length=1, max_length=200)
