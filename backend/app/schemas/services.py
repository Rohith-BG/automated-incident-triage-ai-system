from typing import Literal

from pydantic import BaseModel, Field


DependencyType = Literal["service", "external_api", "database", "unknown"]


class ServiceSummary(BaseModel):
    id: str
    owner_team: str
    repo: str
    language: str
    alert_threshold: str
    oncall_slack: str | None = None


class ServiceDetail(ServiceSummary):
    dependencies: list[str] = Field(default_factory=list)


class DependencyNode(BaseModel):
    id: str
    dependency_type: DependencyType
    owner_team: str | None = None
    repo: str | None = None
    language: str | None = None
    alert_threshold: str | None = None
    oncall_slack: str | None = None


class ServiceDependenciesResponse(BaseModel):
    service_id: str
    dependencies: list[DependencyNode]


class BlastRadiusResponse(BaseModel):
    target_id: str
    affected_services: list[ServiceSummary]
    direct_dependents: list[str]
    impact_count: int
