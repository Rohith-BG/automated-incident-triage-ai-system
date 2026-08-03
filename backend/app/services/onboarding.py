"""
Service Topology Onboarding & Discovery Service.

Implements SOLID design principles:
- Strategy Pattern (ITopologyScanner): Open/Closed Principle for extensible discovery sources.
- Single Responsibility (OnboardingService): Orchestrates discovery, service registry upsert,
  and Knowledge Graph change proposal creation for mandatory human review (Rule 26).
- Dependency Inversion: Accepts repository interfaces via dependency injection.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from backend.app.core.config import settings
from backend.app.enums import ProposalStatus
from backend.app.repositories.kg_change_proposal import KGChangeProposalRepository
from backend.app.repositories.service_registry import ServiceRegistryRepository
from backend.app.schemas.onboarding import (
    DiscoveredServiceInput,
    DiscoveredServiceSummary,
    DiscoverTopologyRequest,
    OnboardingResultResponse,
    OnboardingStatusResponse,
)

logger = logging.getLogger(__name__)


# ── Strategy Pattern (Open/Closed Principle) ─────────────────────────────


class ITopologyScanner(ABC):
    """Abstract Strategy interface for service topology scanners."""

    @abstractmethod
    async def scan(self, payload: DiscoverTopologyRequest) -> list[DiscoveredServiceInput]:
        """Scan and return discovered service configurations."""
        pass


class ServicesJsonScanner(ITopologyScanner):
    """Scanner strategy that extracts topology from data/services.json file."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self._data_path = data_path or (settings.DATA_DIR / "services.json")

    async def scan(self, payload: DiscoverTopologyRequest) -> list[DiscoveredServiceInput]:
        if not self._data_path.exists():
            logger.warning("services.json file not found at %s", self._data_path)
            return []

        with open(self._data_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        discovered: list[DiscoveredServiceInput] = []
        for svc in raw.get("services", []):
            discovered.append(
                DiscoveredServiceInput(
                    service_id=svc["id"],
                    repo=svc.get("repo", "googlecloudplatform/microservices-demo"),
                    architecture_type=payload.architecture_type,
                    language=svc.get("language"),
                    owner_team_id=svc.get("owner_team", payload.owner_team_id),
                    dependencies=svc.get("dependencies", []),
                    alert_threshold=svc.get("alert_threshold", "medium"),
                )
            )
        return discovered


class InlineScanner(ITopologyScanner):
    """Scanner strategy that reads topology directly from request payload."""

    async def scan(self, payload: DiscoverTopologyRequest) -> list[DiscoveredServiceInput]:
        return payload.services


class ScannerFactory:
    """Factory for instantiating scanner strategies (Factory Pattern)."""

    @staticmethod
    def get_scanner(source_type: str) -> ITopologyScanner:
        if source_type == "inline":
            return InlineScanner()
        elif source_type == "services_json":
            return ServicesJsonScanner()
        else:
            raise ValueError(f"Unsupported discovery source_type: '{source_type}'")


# ── Onboarding Service ────────────────────────────────────────────────────


class OnboardingService:
    """Orchestrates topology discovery, registry persistence, and KG proposal creation."""

    def __init__(
        self,
        service_registry_repo: ServiceRegistryRepository,
        kg_proposal_repo: KGChangeProposalRepository,
    ) -> None:
        """Initialise with injected repositories (Dependency Inversion)."""
        self._registry_repo = service_registry_repo
        self._proposal_repo = kg_proposal_repo

    async def discover_and_onboard(
        self, payload: DiscoverTopologyRequest
    ) -> OnboardingResultResponse:
        """Execute topology discovery, register services, and emit a pending KG proposal."""
        scanner = ScannerFactory.get_scanner(payload.source_type)
        discovered_inputs = await scanner.scan(payload)

        discovered_summaries: list[DiscoveredServiceSummary] = []
        registered_count = 0
        proposed_changes: list[dict[str, Any]] = []

        for svc_in in discovered_inputs:
            existing = await self._registry_repo.get_by_service_id(svc_in.service_id)
            is_new = existing is None

            owner = svc_in.owner_team_id or payload.owner_team_id
            if is_new:
                await self._registry_repo.create(
                    service_id=svc_in.service_id,
                    repo=svc_in.repo,
                    architecture_type=svc_in.architecture_type,
                    owner_team=owner,
                    language=svc_in.language,
                    alert_threshold=svc_in.alert_threshold or "medium",
                )
                registered_count += 1
            else:
                await self._registry_repo.update(
                    service_id=svc_in.service_id,
                    repo=svc_in.repo,
                    architecture_type=svc_in.architecture_type,
                    owner_team=owner,
                    language=svc_in.language,
                    alert_threshold=svc_in.alert_threshold,
                )

            discovered_summaries.append(
                DiscoveredServiceSummary(
                    service_id=svc_in.service_id,
                    architecture_type=svc_in.architecture_type,
                    owner_team_id=owner,
                    dependencies=svc_in.dependencies,
                    is_new=is_new,
                )
            )

            # Build proposed Knowledge Graph mutations for human review
            proposed_changes.append(
                {
                    "action": "add_node" if is_new else "update_node",
                    "target_type": "service",
                    "id": svc_in.service_id,
                    "properties": {
                        "architecture_type": svc_in.architecture_type,
                        "owner_team": owner,
                        "language": svc_in.language,
                        "dependencies": svc_in.dependencies,
                    },
                }
            )

        # Emit Knowledge Graph change proposal (status=pending, Rule 26)
        proposal_id = None
        if proposed_changes:
            first_svc = discovered_inputs[0] if discovered_inputs else None
            svc_id = first_svc.service_id if first_svc else "onboarding-batch"
            repo_name = first_svc.repo if first_svc else "topology-discovery"

            proposal = await self._proposal_repo.create(
                service_id=svc_id,
                commit_sha="onboarding-discovery",
                repo=repo_name,
                proposed_changes=proposed_changes,
                architecture_type=payload.architecture_type,
                component_id="topology-onboarding",
                diff_summary=f"Onboarded {len(discovered_inputs)} services via topology discovery ({payload.source_type}).",
            )
            proposal_id = proposal.id

        message = (
            f"Successfully discovered {len(discovered_inputs)} services ({registered_count} newly registered). "
            f"Generated Knowledge Graph proposal {proposal_id} for mandatory human review."
        )

        return OnboardingResultResponse(
            discovered_count=len(discovered_inputs),
            registered_count=registered_count,
            proposal_id=proposal_id,
            discovered_services=discovered_summaries,
            message=message,
        )

    async def get_onboarding_status(self) -> OnboardingStatusResponse:
        """Return high-level summary of onboarding status across the platform."""
        all_services = await self._registry_repo.list_all(active_only=False)
        active_services = [s for s in all_services if s.is_active]
        pending_proposals = await self._proposal_repo.list_proposals(
            status=ProposalStatus.PENDING
        )

        return OnboardingStatusResponse(
            total_registered_services=len(all_services),
            pending_proposals_count=len(pending_proposals),
            active_services_count=len(active_services),
        )
