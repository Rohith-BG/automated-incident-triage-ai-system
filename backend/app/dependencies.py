"""
FastAPI dependency injection providers.

Wires up the Route → Controller → Service → Repository chain
so that each layer receives its dependencies cleanly via
FastAPI's ``Depends()`` mechanism.
"""

import logging
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .controllers.auth import AuthController
from .controllers.incident import IncidentController
from .controllers.incident_knowledge import IncidentKnowledgeController
from .core.database import get_db
from .core.security import decode_token
from .enums import UserRole
from .exceptions import ForbiddenException, UnauthorizedException
from .models.user import User
from .repositories.incident import IncidentRepository
from .repositories.incident_knowledge import IncidentKnowledgeRepository
from .repositories.incident_resolution import IncidentResolutionRepository
from .repositories.kg_change_proposal import KGChangeProposalRepository
from .repositories.service_registry import ServiceRegistryRepository
from .repositories.user import UserRepository
from .services.auth import AuthService
from .services.incident import IncidentService
from .services.incident_knowledge import IncidentKnowledgeService
from .services.service_registry import KGProposalService, ServiceRegistryService

logger = logging.getLogger(__name__)

# ── Incident domain ─────────────────────────────────────


def get_incident_repository(
    db: AsyncSession = Depends(get_db),
) -> IncidentRepository:
    """Provide an IncidentRepository bound to the current session."""
    return IncidentRepository(session=db)


def get_incident_resolution_repository(
    db: AsyncSession = Depends(get_db),
) -> IncidentResolutionRepository:
    """Provide an IncidentResolutionRepository bound to the current session."""
    return IncidentResolutionRepository(session=db)


def get_incident_service(
    repo: IncidentRepository = Depends(get_incident_repository),
    resolution_repo: IncidentResolutionRepository = Depends(get_incident_resolution_repository),
) -> IncidentService:
    """Provide an IncidentService with its repository."""
    return IncidentService(repository=repo, resolution_repository=resolution_repo)


def get_incident_controller(
    service: IncidentService = Depends(get_incident_service),
) -> IncidentController:
    """Provide an IncidentController with its service."""
    return IncidentController(service=service)


# ── Incident Knowledge domain ───────────────────────────


def get_incident_knowledge_repository(
    db: AsyncSession = Depends(get_db),
) -> IncidentKnowledgeRepository:
    """Provide an IncidentKnowledgeRepository bound to the current session."""
    return IncidentKnowledgeRepository(session=db)


def get_incident_knowledge_service(
    repo: IncidentKnowledgeRepository = Depends(get_incident_knowledge_repository),
) -> IncidentKnowledgeService:
    """Provide an IncidentKnowledgeService with its repository."""
    return IncidentKnowledgeService(repository=repo)


def get_incident_knowledge_controller(
    service: IncidentKnowledgeService = Depends(get_incident_knowledge_service),
) -> IncidentKnowledgeController:
    """Provide an IncidentKnowledgeController with its service."""
    return IncidentKnowledgeController(service=service)


# ── Auth domain ─────────────────────────────────────────


def get_user_repository(
    db: AsyncSession = Depends(get_db),
) -> UserRepository:
    """Provide a UserRepository bound to the current session."""
    return UserRepository(session=db)


def get_auth_service(
    repo: UserRepository = Depends(get_user_repository),
) -> AuthService:
    """Provide an AuthService with its repository."""
    return AuthService(repository=repo)


def get_auth_controller(
    service: AuthService = Depends(get_auth_service),
) -> AuthController:
    """Provide an AuthController with its service."""
    return AuthController(service=service)


def get_service_registry_repository(
    db: AsyncSession = Depends(get_db),
) -> ServiceRegistryRepository:
    """Provide a ServiceRegistryRepository."""
    return ServiceRegistryRepository(session=db)


def get_service_registry_service(
    repo: ServiceRegistryRepository = Depends(get_service_registry_repository),
) -> ServiceRegistryService:
    """Provide a ServiceRegistryService."""
    return ServiceRegistryService(repo=repo)


def get_kg_proposal_repository(
    db: AsyncSession = Depends(get_db),
) -> KGChangeProposalRepository:
    """Provide a KGChangeProposalRepository."""
    return KGChangeProposalRepository(session=db)


def get_kg_proposal_service(
    repo: KGChangeProposalRepository = Depends(get_kg_proposal_repository),
) -> KGProposalService:
    """Provide a KGProposalService."""
    return KGProposalService(proposal_repo=repo)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the Bearer JWT and return the active user.

    Raises:
        UnauthorizedException: If the token is missing,
            invalid, expired, or the user is inactive.
    """
    if token is None:
        logger.warning("Authentication failed: No bearer token provided")
        raise UnauthorizedException("Not authenticated.")

    payload = decode_token(token)

    if payload.get("type") != "access":
        logger.warning("Authentication failed: JWT token type is not 'access'")
        raise UnauthorizedException(
            "Invalid token type. Use an access token."
        )

    user_id: str = payload["sub"]
    repo = UserRepository(session=db)
    user = await repo.get_by_id(user_id)

    if user is None:
        logger.warning("Authentication failed: User ID %s not found in DB", user_id)
        raise UnauthorizedException("User not found.")
    if not user.is_active:
        logger.warning("Authentication failed: User account %s is deactivated", user.email)
        raise UnauthorizedException("Account is deactivated.")

    return user


def require_role(*roles: UserRole | str):
    """Return a dependency that enforces RBAC role checks.

    Usage::

        @router.get("/admin-only")
        async def admin_view(
            user: User = Depends(require_role(UserRole.ADMIN)),
        ):
            ...

    Args:
        roles: One or more allowed UserRole enum values or role strings.

    Returns:
        A FastAPI dependency function.
    """
    role_values = [r.value if hasattr(r, "value") else str(r) for r in roles]

    async def _check_role(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in role_values:
            logger.warning(
                "RBAC authorization failed for user %s: Required roles %s, actual role: %s",
                current_user.email,
                role_values,
                current_user.role,
            )
            raise ForbiddenException(
                "Insufficient permissions for this action."
            )
        return current_user

    return _check_role


    return _check_role
