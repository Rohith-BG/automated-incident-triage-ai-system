"""
FastAPI route handlers for KG Change Proposals review and feedback workflow.
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, Query, status

from ..dependencies import (
    get_current_user,
    get_kg_proposal_service,
    require_role,
)
from ..enums import UserRole
from ..models.user import User
from ..schemas.kg_change_proposal import (
    KGProposalFeedbackRequest,
    KGProposalResponse,
)
from ..services.service_registry import KGProposalService

router = APIRouter(prefix="/kg-proposals", tags=["KG Proposals"])


@router.get("", response_model=list[KGProposalResponse])
async def list_proposals(
    service_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    service: KGProposalService = Depends(get_kg_proposal_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List KG change proposals."""
    return await service.list_proposals(service_id=service_id, status=status_filter, limit=limit)


@router.get("/{proposal_id}", response_model=KGProposalResponse)
async def get_proposal(
    proposal_id: str,
    service: KGProposalService = Depends(get_kg_proposal_service),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get single proposal details."""
    return await service.get_proposal(proposal_id)


@router.post(
    "/{proposal_id}/approve",
    response_model=KGProposalResponse,
)
async def approve_proposal(
    proposal_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: KGProposalService = Depends(get_kg_proposal_service),
) -> Any:
    """Approve a KG proposal and apply changes to Knowledge Graph (Admin only)."""
    return await service.approve_proposal(proposal_id=proposal_id, reviewer=current_user.email)


@router.post(
    "/{proposal_id}/reject",
    response_model=KGProposalResponse,
)
async def reject_proposal(
    proposal_id: str,
    reason: Optional[str] = Query(None),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: KGProposalService = Depends(get_kg_proposal_service),
) -> Any:
    """Reject a proposal without applying changes (Admin only)."""
    return await service.reject_proposal(proposal_id=proposal_id, reviewer=current_user.email, reason=reason)


@router.post(
    "/{proposal_id}/feedback",
    response_model=KGProposalResponse,
)
async def submit_feedback(
    proposal_id: str,
    payload: KGProposalFeedbackRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    service: KGProposalService = Depends(get_kg_proposal_service),
) -> Any:
    """Submit correction feedback, triggering agent re-analysis loop (Admin only)."""
    return await service.submit_feedback(
        proposal_id=proposal_id,
        reviewer=current_user.email,
        feedback=payload.feedback,
    )
