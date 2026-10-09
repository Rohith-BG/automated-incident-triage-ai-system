"""
Database session management.

Configures async SQLAlchemy engine and session makers, supporting
PostgreSQL in production and a lightweight SQLite fallback in development.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator


from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

logger = logging.getLogger(__name__)

is_testing = "pytest" in sys.modules

# Initial database URLs — normalise PaaS-provided postgres:// schemes
# (Render, Heroku, Railway emit postgres:// but SQLAlchemy needs
# postgresql+asyncpg://).
pg_url = settings.DATABASE_URL
if pg_url.startswith("postgres://"):
    pg_url = pg_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif pg_url.startswith("postgresql://"):
    pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://", 1)
sqlite_url = "sqlite+aiosqlite:///:memory:" if is_testing else "sqlite+aiosqlite:///./triage.db"

# SQLite serialises writers: a second connection writing while another holds
# the write lock fails outright after the busy timeout. A background
# investigation persists its result concurrently with request handling and the
# workers, so WAL (readers never block the writer) plus a generous busy
# timeout is what keeps those writes from raising "database is locked".
_SQLITE_BUSY_TIMEOUT_MS = 30_000


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(
    dbapi_connection: Any, _connection_record: Any
) -> None:
    """Apply concurrency pragmas to every new SQLite connection."""
    # Guard: only execute PRAGMAs on SQLite connections.
    module = type(dbapi_connection).__module__ or ""
    if "sqlite" not in module and "aiosqlite" not in module:
        return
    cursor = dbapi_connection.cursor()
    try:
        if not is_testing:
            # In-memory SQLite has no journal file to write ahead.
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


# Create engines
pg_engine = None
if pg_url and "postgresql" in pg_url:
    try:
        pg_engine = create_async_engine(
            pg_url,
            pool_size=10,
            max_overflow=20
        )
    except Exception as e:
        logger.warning(f"Could not create PostgreSQL engine during import: {e}")

sqlite_engine = create_async_engine(sqlite_url, echo=False)

# Default to pg_engine unless testing, not configured, or fallback active
use_sqlite_fallback = is_testing or pg_engine is None
engine = sqlite_engine if use_sqlite_fallback else pg_engine

class Base(DeclarativeBase):
    pass


# Default session factory (imported by routers/tests)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── SQLite write serialisation ────────────────────────────
# aiosqlite wraps each connection in its own thread, which means
# SQLite's internal busy_timeout is not reliably honoured across
# concurrent asyncio tasks.  This lock serialises write-heavy
# transactions so only one proceeds at a time.  On PostgreSQL the
# context manager is a no-op passthrough.
# ponytail: global asyncio.Lock caps write throughput to 1 concurrent
# writer — fine for dev SQLite; upgrade path is PostgreSQL.
_sqlite_write_lock = asyncio.Lock()


@asynccontextmanager
async def sqlite_serialize_writes():
    """Acquire the SQLite write lock if the active engine is SQLite.

    Usage::

        async with sqlite_serialize_writes():
            async with AsyncSessionLocal() as session:
                ...
                await session.commit()

    On PostgreSQL this yields immediately without locking.
    """
    if use_sqlite_fallback:
        async with _sqlite_write_lock:
            yield
    else:
        yield



async def init_db() -> None:
    """Initialize database.

    Tests PostgreSQL connection and falls back to SQLite if PG connection fails.
    In production mode, disables SQLite fallback and crashes startup if PG fails.
    """
    global engine, use_sqlite_fallback

    if is_testing:
        logger.info("Test mode: using SQLite in-memory database")
        engine = sqlite_engine
        AsyncSessionLocal.configure(bind=sqlite_engine)
        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return

    # Strict check for production environment
    if settings.is_prod_mode:
        if not pg_url or "postgresql" not in pg_url or pg_engine is None:
            raise ValueError(
                "PostgreSQL DATABASE_URL must be configured correctly in production environment."
            )
        try:
            logger.info("Testing PostgreSQL connection (Production mode)...")
            async with pg_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Successfully connected to PostgreSQL database.")
            engine = pg_engine
            AsyncSessionLocal.configure(bind=pg_engine)
            # Re-confirm fallback is inactive
            use_sqlite_fallback = False
            # In production, do NOT run Base.metadata.create_all automatically.
            # Production schemas must be managed via migrations (e.g. Alembic).
            return
        except Exception as e:
            logger.critical(f"PostgreSQL connection failed in production mode: {e}. Crashing startup.")
            raise e

    # Dev fallback path
    if not use_sqlite_fallback and pg_engine is not None:
        try:
            logger.info("Testing PostgreSQL connection (Development mode)...")
            async with pg_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Successfully connected to PostgreSQL database.")
            engine = pg_engine
            AsyncSessionLocal.configure(bind=pg_engine)
            # Auto-create tables in development PostgreSQL
            if settings.is_dev_mode:
                async with pg_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection failed ({e}). "
                "Falling back to local SQLite database (triage.db)."
            )
            use_sqlite_fallback = True

    # SQLite fallback creation
    logger.info("Using local SQLite database fallback (triage.db).")
    engine = sqlite_engine
    AsyncSessionLocal.configure(bind=sqlite_engine)
    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection yield for DB session.

    Resolves the correct active engine (supporting SQLite runtime fallbacks).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
