"""
Controllers for formatting HTTP API responses.
"""

from typing import Any
from ..models.service_registry import ServiceRegistry
from ..models.kg_change_proposal import KGChangeProposal
from ..schemas.service_registry import ServiceRegistryResponse
from ..schemas.kg_change_proposal import KGProposalResponse


class ServiceRegistryController:
    """Controller for formatting service registry responses."""

    @staticmethod
    def format_service(entry: ServiceRegistry) -> dict[str, Any]:
        """Format single service entry."""
        return ServiceRegistryResponse.model_validate(entry).model_dump()

    @staticmethod
    def format_services_list(entries: list[ServiceRegistry]) -> list[dict[str, Any]]:
        """Format list of service entries."""
        return [ServiceRegistryResponse.model_validate(e).model_dump() for e in entries]


class KGProposalController:
    """Controller for formatting KG change proposal responses."""

    @staticmethod
    def format_proposal(proposal: KGChangeProposal) -> dict[str, Any]:
        """Format single proposal."""
        return KGProposalResponse.model_validate(proposal).model_dump()

    @staticmethod
    def format_proposals_list(proposals: list[KGChangeProposal]) -> list[dict[str, Any]]:
        """Format list of proposals."""
        return [KGProposalResponse.model_validate(p).model_dump() for p in proposals]
