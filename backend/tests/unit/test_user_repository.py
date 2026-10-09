"""Unit tests for UserRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.database import Base
from backend.app.enums import UserRole
from backend.app.models.user import User
from backend.app.repositories.user import UserRepository

ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:", echo=False
)
TestSession = async_sessionmaker(
    bind=ENGINE, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create and tear down tables for every test."""
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    """Provide a fresh async session per test."""
    async with TestSession() as sess:
        yield sess


@pytest_asyncio.fixture
async def repo(session: AsyncSession):
    """Provide a UserRepository bound to the test session."""
    return UserRepository(session=session)


@pytest.mark.asyncio
async def test_create_user(
    repo: UserRepository, session: AsyncSession
) -> None:
    """create() inserts a new user and hashes their password."""
    user = await repo.create(
        email="test@example.com",
        hashed_password="some-hashed-password",
        full_name="John Doe",
        role=UserRole.DEVELOPER,
    )
    await session.commit()

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.hashed_password == "some-hashed-password"
    assert user.full_name == "John Doe"
    assert user.role == UserRole.DEVELOPER
    assert user.is_active is True


@pytest.mark.asyncio
async def test_get_by_id(
    repo: UserRepository, session: AsyncSession
) -> None:
    """get_by_id() retrieves user correctly."""
    user = await repo.create(
        email="test@example.com",
        hashed_password="hash",
        full_name="John Doe",
        role=UserRole.DEVELOPER,
    )
    await session.commit()

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.email == "test@example.com"


@pytest.mark.asyncio
async def test_get_by_id_not_found(
    repo: UserRepository,
) -> None:
    """get_by_id() returns None if not found."""
    fetched = await repo.get_by_id("nonexistent-id")
    assert fetched is None


@pytest.mark.asyncio
async def test_get_by_email(
    repo: UserRepository, session: AsyncSession
) -> None:
    """get_by_email() retrieves user correctly."""
    user = await repo.create(
        email="test@example.com",
        hashed_password="hash",
        full_name="John Doe",
        role=UserRole.DEVELOPER,
    )
    await session.commit()

    fetched = await repo.get_by_email("test@example.com")
    assert fetched is not None
    assert fetched.id == user.id


@pytest.mark.asyncio
async def test_get_by_email_not_found(
    repo: UserRepository,
) -> None:
    """get_by_email() returns None if not found."""
    fetched = await repo.get_by_email("unknown@example.com")
    assert fetched is None
