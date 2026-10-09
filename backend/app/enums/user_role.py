"""
User role enumeration.

Defines the RBAC roles used across the platform.
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Valid RBAC roles for platform users."""

    ADMIN = "admin"
    DEVELOPER = "developer"
