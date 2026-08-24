"""
Auth REST API routes.

Provides endpoints for user registration, login, token refresh,
logout, and current user profile retrieval. Refresh tokens are
stored in HTTP-only cookies — never in localStorage.
"""

import logging

from fastapi import APIRouter, Cookie, Depends, Response, status

from ..controllers.auth import AuthController
from ..dependencies import get_auth_controller, get_current_user
from ..models.user import User
from ..schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie configuration constants
_REFRESH_COOKIE = "refresh_token"
_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an HTTP-only cookie."""
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=False,  # Set True in production (HTTPS)
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/auth",
    )


# ── Endpoints ────────────────────────────────────────────


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterRequest,
    controller: AuthController = Depends(get_auth_controller),
) -> UserResponse:
    """Create a new user account.

    The very first registered user becomes the platform admin and
    unlocks the onboarding / initial-setup flow (build + review KG).
    Every subsequent registration defaults to ``team_member``.
    """
    logger.info("Received registration request for email: %s", payload.email)
    response = await controller.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    logger.info("Successfully registered user: %s (id: %s)", response.email, response.id)
    return response


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain tokens",
)
async def login(
    payload: LoginRequest,
    response: Response,
    controller: AuthController = Depends(get_auth_controller),
) -> TokenResponse:
    """Authenticate and return an access token.

    The refresh token is set as an HTTP-only cookie.
    """
    logger.info("Received login request for email: %s", payload.email)
    user_resp, access_token, refresh_token = await controller.login(
        email=payload.email,
        password=payload.password,
    )
    _set_refresh_cookie(response, refresh_token)
    logger.info("Successfully authenticated user: %s (id: %s)", user_resp.email, user_resp.id)
    return TokenResponse(access_token=access_token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate access and refresh tokens",
)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(
        None, alias=_REFRESH_COOKIE
    ),
    controller: AuthController = Depends(get_auth_controller),
) -> TokenResponse:
    """Issue new tokens using the refresh token from the cookie.

    The old refresh token is invalidated by rotation.
    """
    logger.info("Received token refresh request")
    if not refresh_token:
        logger.warning("Token refresh failed: Missing refresh token cookie")
        from ..exceptions import UnauthorizedException
        raise UnauthorizedException("Missing refresh token.")

    new_access, new_refresh = await controller.refresh(
        refresh_token
    )
    _set_refresh_cookie(response, new_refresh)
    logger.info("Successfully rotated tokens")
    return TokenResponse(access_token=new_access)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and clear refresh cookie",
)
async def logout(response: Response) -> MessageResponse:
    """Clear the refresh token cookie."""
    logger.info("Received logout request")
    _clear_refresh_cookie(response)
    logger.info("Successfully logged out user and cleared cookies")
    return MessageResponse(message="Logged out successfully.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the profile of the authenticated user.

    Requires a valid Bearer access token.
    """
    logger.debug("Received profile request for user: %s", current_user.email)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
