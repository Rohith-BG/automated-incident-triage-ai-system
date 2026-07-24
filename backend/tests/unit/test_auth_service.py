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
    """register() creates a user if the email is not registered."""
    mock_repo.get_by_email = AsyncMock(return_value=None)
    
    # Mock create to return a User model
    mock_user = User(
        id="user-123",
        email="new@example.com",
        hashed_password="hashed_pass",
        full_name="Alice Smith",
        role=UserRole.TEAM_MEMBER,
    )
    mock_repo.create = AsyncMock(return_value=mock_user)

    result = await auth_service.register(
        email="new@example.com",
        password="password123",
        full_name="Alice Smith",
    )

    assert result == mock_user
    mock_repo.get_by_email.assert_called_once_with("new@example.com")
    # Verify that mock_repo.create was called with hashed password
    mock_repo.create.assert_called_once()
    kwargs = mock_repo.create.call_args.kwargs
    assert kwargs["email"] == "new@example.com"
    assert kwargs["full_name"] == "Alice Smith"
    assert kwargs["role"] == UserRole.TEAM_MEMBER
    assert verify_password("password123", kwargs["hashed_password"]) is True


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
        role=UserRole.SRE,
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
    
    refresh_token = create_refresh_token({"sub": "user-123", "role": "sre"})
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password="hash",
        full_name="Bob Doe",
        role=UserRole.SRE,
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
    
    refresh_token = create_refresh_token({"sub": "user-123", "role": "sre"})
    user = User(
        id="user-123",
        email="user@example.com",
        hashed_password="hash",
        full_name="Bob Doe",
        role=UserRole.SRE,
        is_active=False,
    )
    mock_repo.get_by_id = AsyncMock(return_value=user)

    with pytest.raises(UnauthorizedException) as exc_info:
        await auth_service.refresh(refresh_token)

    assert "deactivated" in exc_info.value.message.lower()
