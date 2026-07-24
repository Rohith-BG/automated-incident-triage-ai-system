"""
Incident status enumeration.

Centralises all valid incident lifecycle states. Use this enum
everywhere instead of raw strings to guarantee consistency
across models, services, repositories, and API responses.
"""

from enum import StrEnum


class IncidentStatus(StrEnum):
    """Valid lifecycle states for an incident."""

    INVESTIGATING = "investigating"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    RESOLVED = "resolved"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def active_statuses(cls) -> list["IncidentStatus"]:
        """Return statuses that indicate an incident is still open.

        Used by the deduplication logic to decide whether a new
        alert should attach to an existing incident rather than
        creating a new one.
        """
        return [cls.INVESTIGATING, cls.ROOT_CAUSE_IDENTIFIED]
