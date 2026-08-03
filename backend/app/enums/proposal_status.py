"""
KG Change Proposal status enumeration.

Centralises all valid proposal lifecycle states.
"""

from enum import StrEnum


class ProposalStatus(StrEnum):
    """Valid lifecycle states for a Knowledge Graph change proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FEEDBACK = "feedback"
