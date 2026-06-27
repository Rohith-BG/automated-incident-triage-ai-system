'''Base use case classes for service catalog services.'''

from __future__ import annotations

from abc import ABC

class ServiceCatalogUseCase(ABC):
    """Base class for service‑catalog use‑case services.

    Concrete services (e.g. :class:`ServiceCatalogService`) should inherit
    from this class to signal they belong to the *service‑catalog* use‑case
    layer. No mandatory methods are defined yet; this placeholder enables
    a clear separation between transport (controllers), business logic
    (services) and data access (repositories) while keeping the codebase
    aligned with the Clean‑Architecture guidelines in AGENTS.md.
    """
    pass
