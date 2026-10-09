"""Unit tests for AuthService."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.app.core.security import verify_password
from backend.app.enums import UserRole
from backend.app.exceptions import ConflictException, UnauthorizedException
from backend.app.models.user import User
from backend.app.repositories.user import UserRepository
from backend.app.services.auth import AuthService


@pytest.fixture
def mock_repo():
    """Provide a mocked UserRepository."""
    return MagicMock(spec=UserRepository)


@pytest.fixture
def auth_service(mock_repo):
    """Provide an AuthService using the mock repository."""
    return AuthService(repository=mock_repo)


@pytest.mark.asyncio
async def test_register_success(auth_service, mock_repo) -> None:
    """register() creates a user with the requested role."""
    mock_repo.get_by_email = AsyncMock(return_value=None)

    mock_user = User(
        id="user-123",
        email="new@example.com",
        hashed_password="hashed_pass",
        full_name="Alice Smith",
        role=UserRole.DEVELOPER,
    )
    mock_repo.create = AsyncMock(return_value=mock_user)

    result = await auth_service.register(
        email="new@example.com",
        password="password123",
        full_name="Alice Smith",
        role=UserRole.DEVELOPER,
    )

    assert result == mock_user
    mock_repo.get_by_email.assert_called_once_with("new@example.com")
    mock_repo.create.assert_called_once()
    kwargs = mock_repo.create.call_args.kwargs
    assert kwargs["email"] == "new@example.com"
    assert kwargs["full_name"] == "Alice Smith"
    assert kwargs["role"] == UserRole.DEVELOPER
    assert verify_password("password123", kwargs["hashed_password"]) is True


@pytest.mark.asyncio
async def test_register_with_admin_role(auth_service, mock_repo) -> None:
    """register() creates a user with admin role when requested."""
    mock_repo.get_by_email = AsyncMock(return_value=None)

    mock_user = User(
        id="user-admin",
        email="admin2@example.com",
        hashed_password="hashed_pass",
        full_name="Second Admin",
        role=UserRole.ADMIN,
    )
    mock_repo.create = AsyncMock(return_value=mock_user)

    result = await auth_service.register(
        email="admin2@example.com",
        password="password123",
        full_name="Second Admin",
        role=UserRole.ADMIN,
    )

    assert result == mock_user
    assert mock_repo.create.call_args.kwargs["role"] == UserRole.ADMIN


@pytest.mark.asyncio
async def test_register_defaults_to_developer(auth_service, mock_repo) -> None:
    """register() defaults to developer role when no role specified."""
    mock_repo.get_by_email = AsyncMock(return_value=None)

    mock_user = User(
        id="user-dev",
        email="dev@example.com",
        hashed_password="hashed_pass",
        full_name="Dev User",
        role=UserRole.DEVELOPER,
    )
    mock_repo.create = AsyncMock(return_value=mock_user)

    result = await auth_service.register(
        email="dev@example.com",
        password="password123",
        full_name="Dev User",
    )

    assert result == mock_user
    assert mock_repo.create.call_args.kwargs["role"] == UserRole.DEVELOPER


@pytest.mark.asyncio
async def test_register_duplicate_email(auth_service, mock_repo) -> None:
    """register() raises ConflictException if email is already registered."""
    existing_user = User(
        id="user-123",
        email="existing@example.com",
        hashed_password="hash",
        full_name="Alice Smith",
    )
    mock_repo.get_by_email = AsyncMock(return_value=existing_user)

    with pytest.raises(ConflictException) as exc_info:
        await auth_service.register(
            email="existing@example.com",
            password="password123",
            full_name="Alice Smith",
        )

    assert "already registered" in exc_info.value.message
    mock_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_login_success(auth_service, mock_repo) -> None:
    """login() returns user and tokens for valid credentials."""
    from backend.app.core.security import hash_password
    hashed = hash_password("mypassword")
    
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password=hashed,
        full_name="Bob Doe",
        role=UserRole.DEVELOPER,
        is_active=True,
    )
    mock_repo.get_by_email = AsyncMock(return_value=user)

    res_user, access_token, refresh_token = await auth_service.login(
        email="user@example.com",
        password="mypassword",
    )

    assert res_user == user
    assert access_token is not None
    assert refresh_token is not None


@pytest.mark.asyncio
async def test_login_invalid_password(auth_service, mock_repo) -> None:
    """login() raises UnauthorizedException for wrong password."""
    from backend.app.core.security import hash_password
    hashed = hash_password("correct-pass")
    
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password=hashed,
        full_name="Bob Doe",
        is_active=True,
    )
    mock_repo.get_by_email = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException) as exc_info:
        await auth_service.login(
            email="user@example.com",
            password="wrong-pass",
        )

    assert "invalid email or password" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_login_user_not_found(auth_service, mock_repo) -> None:
    """login() raises UnauthorizedException if email doesn't exist."""
    mock_repo.get_by_email = AsyncMock(return_value=None)

    with pytest.raises(UnauthorizedException) as exc_info:
        await auth_service.login(
            email="unknown@example.com",
            password="password",
        )

    assert "invalid email or password" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_login_deactivated_user(auth_service, mock_repo) -> None:
    """login() raises UnauthorizedException if user account is inactive."""
    from backend.app.core.security import hash_password
    hashed = hash_password("pass")
    
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password=hashed,
        full_name="Bob Doe",
        is_active=False,
    )
    mock_repo.get_by_email = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException) as exc_info:
        await auth_service.login(
            email="user@example.com",
            password="pass",
        )

    assert "deactivated" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_refresh_success(auth_service, mock_repo) -> None:
    """refresh() rotates access and refresh tokens for active user."""
    from backend.app.core.security import create_refresh_token
    
    refresh_token = create_refresh_token({"sub": "user-123", "role": "developer"})
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password="hash",
        full_name="Bob Doe",
        role=UserRole.DEVELOPER,
        is_active=True,
    )
    mock_repo.get_by_id = AsyncMock(return_value=user)

    new_access, new_refresh = await auth_service.refresh(refresh_token)

    assert new_access is not None
    assert new_refresh is not None
    assert new_access != refresh_token


@pytest.mark.asyncio
async def test_refresh_inactive_user(auth_service, mock_repo) -> None:
    """refresh() raises UnauthorizedException if user is deactivated."""
    from backend.app.core.security import create_refresh_token
    
    refresh_token = create_refresh_token({"sub": "user-123", "role": "developer"})
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password="hash",
        full_name="Bob Doe",
        role=UserRole.DEVELOPER,
        is_active=False,
    )
    mock_repo.get_by_id = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException) as exc_info:
        await auth_service.refresh(refresh_token)

    assert "deactivated" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_list_users(auth_service, mock_repo) -> None:
    """list_users() returns all users from the repository."""
    user_a = User(
        id="u-1", email="a@x.com", hashed_password="h",
        full_name="A", role=UserRole.ADMIN, is_active=True,
    )
    user_b = User(
        id="u-2", email="b@x.com", hashed_password="h",
        full_name="B", role=UserRole.DEVELOPER, is_active=True,
    )
    mock_repo.list_all = AsyncMock(return_value=[user_a, user_b])

    result = await auth_service.list_users()

    assert len(result) == 2
    assert result[0].id == "u-1"
    mock_repo.list_all.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_success(auth_service, mock_repo) -> None:
    """update_user() patches name and role."""
    user = User(
        id="u-1", email="a@x.com", hashed_password="h",
        full_name="Old Name", role=UserRole.DEVELOPER, is_active=True,
    )
    updated = User(
        id="u-1", email="a@x.com", hashed_password="h",
        full_name="New Name", role=UserRole.ADMIN, is_active=True,
    )
    mock_repo.get_by_id = AsyncMock(return_value=user)
    mock_repo.update = AsyncMock(return_value=updated)

    result = await auth_service.update_user(
        user_id="u-1",
        admin_id="u-admin",
        full_name="New Name",
        role=UserRole.ADMIN,
    )

    assert result.full_name == "New Name"
    assert result.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_update_user_not_found(auth_service, mock_repo) -> None:
    """update_user() raises NotFoundException for missing user."""
    from backend.app.exceptions import NotFoundException

    mock_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException):
        await auth_service.update_user(
            user_id="missing",
            admin_id="admin-1",
            full_name="X",
        )


@pytest.mark.asyncio
async def test_update_user_self_deactivate_blocked(
    auth_service, mock_repo,
) -> None:
    """update_user() blocks an admin from deactivating themselves."""
    from backend.app.exceptions import BadRequestException

    user = User(
        id="admin-1", email="a@x.com", hashed_password="h",
        full_name="Admin", role=UserRole.ADMIN, is_active=True,
    )
    mock_repo.get_by_id = AsyncMock(return_value=user)

    with pytest.raises(BadRequestException, match="own account"):
        await auth_service.update_user(
            user_id="admin-1",
            admin_id="admin-1",
            is_active=False,
        )
