from collections import defaultdict, deque
from typing import Any

from ..exceptions import NotFoundException

from ..repositories.service_catalog import ServiceCatalogRepository
from ..repositories.service_catalog import ServiceCatalogRepository
from ..schemas.services import (
    BlastRadiusResponse,
    DependencyNode,
    ServiceDependenciesResponse,
    ServiceDetail,
    ServiceSummary,
)



class ServiceCatalogService:
    def __init__(self, repository: ServiceCatalogRepository | None = None) -> None:
        self.repository = repository or ServiceCatalogRepository()

    async def list_services(self) -> list[ServiceSummary]:
        catalog = await self.repository.load_catalog()
        return [self._to_summary(service, catalog) for service in catalog["services"]]

    async def get_service(self, service_id: str) -> ServiceDetail:
        catalog = await self.repository.load_catalog()
        service = self._service_lookup(catalog).get(service_id)

        if service is None:
            raise NotFoundException(
                f"Unknown service: {service_id}",
                context={"service_id": service_id},
            )

        return self._to_detail(service, catalog)

    async def get_dependencies(self, service_id: str) -> ServiceDependenciesResponse:
        catalog = await self.repository.load_catalog()
        service = self._service_lookup(catalog).get(service_id)

        if service is None:
            raise NotFoundException(
                f"Unknown service: {service_id}",
                context={"service_id": service_id},
            )

        dependencies = [
            self._to_dependency_node(dependency_id, catalog)
            for dependency_id in service.get("dependencies", [])
        ]

        return ServiceDependenciesResponse(
            service_id=service_id,
            dependencies=dependencies,
        )

    async def get_blast_radius(self, target_id: str) -> BlastRadiusResponse:
        catalog = await self.repository.load_catalog()

        if not self._target_exists(target_id, catalog):
            raise NotFoundException(
                f"Unknown dependency target: {target_id}",
                context={"target_id": target_id},
            )

        service_lookup = self._service_lookup(catalog)
        reverse_dependencies = self._reverse_dependency_lookup(catalog)
        affected_ids = self._collect_affected_service_ids(target_id, reverse_dependencies)
        affected_services = [
            self._to_summary(service_lookup[service_id], catalog)
            for service_id in affected_ids
            if service_id in service_lookup
        ]

        return BlastRadiusResponse(
            target_id=target_id,
            affected_services=affected_services,
            direct_dependents=reverse_dependencies.get(target_id, []),
            impact_count=len(affected_services),
        )

    def _to_summary(
        self,
        service: dict[str, Any],
        catalog: dict[str, Any],
    ) -> ServiceSummary:
        return ServiceSummary(
            id=service["id"],
            owner_team=service["owner_team"],
            repo=service["repo"],
            language=service["language"],
            alert_threshold=service["alert_threshold"],
            oncall_slack=self._team_lookup(catalog)
            .get(service["owner_team"], {})
            .get("oncall_slack"),
        )

    def _to_detail(
        self,
        service: dict[str, Any],
        catalog: dict[str, Any],
    ) -> ServiceDetail:
        summary = self._to_summary(service, catalog)
        return ServiceDetail(
            **summary.model_dump(),
            dependencies=service.get("dependencies", []),
        )

    def _to_dependency_node(
        self,
        dependency_id: str,
        catalog: dict[str, Any],
    ) -> DependencyNode:
        service = self._service_lookup(catalog).get(dependency_id)

        if service is not None:
            summary = self._to_summary(service, catalog)
            return DependencyNode(
                id=dependency_id,
                dependency_type="service",
                **summary.model_dump(exclude={"id"}),
            )

        if dependency_id in set(catalog.get("external_apis", [])):
            return DependencyNode(id=dependency_id, dependency_type="external_api")

        if dependency_id in set(catalog.get("databases", [])):
            return DependencyNode(id=dependency_id, dependency_type="database")

        return DependencyNode(id=dependency_id, dependency_type="unknown")

    def _target_exists(self, target_id: str, catalog: dict[str, Any]) -> bool:
        return (
            target_id in self._service_lookup(catalog)
            or target_id in set(catalog.get("external_apis", []))
            or target_id in set(catalog.get("databases", []))
        )

    def _collect_affected_service_ids(
        self,
        target_id: str,
        reverse_dependencies: dict[str, list[str]],
    ) -> list[str]:
        affected: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque(reverse_dependencies.get(target_id, []))

        while queue:
            service_id = queue.popleft()
            if service_id in visited:
                continue

            visited.add(service_id)
            affected.append(service_id)
            queue.extend(reverse_dependencies.get(service_id, []))

        return affected

    def _reverse_dependency_lookup(self, catalog: dict[str, Any]) -> dict[str, list[str]]:
        reverse_dependencies: dict[str, list[str]] = defaultdict(list)

        for service in catalog["services"]:
            for dependency_id in service.get("dependencies", []):
                reverse_dependencies[dependency_id].append(service["id"])

        return dict(reverse_dependencies)

    def _service_lookup(self, catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {service["id"]: service for service in catalog["services"]}

    def _team_lookup(self, catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {team["id"]: team for team in catalog.get("teams", [])}
