"""
User role enumeration.

Defines the RBAC roles used across the platform.
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Valid RBAC roles for platform users."""

    ADMIN = "admin"
    SRE = "sre"
    TEAM_MEMBER = "team_member"
