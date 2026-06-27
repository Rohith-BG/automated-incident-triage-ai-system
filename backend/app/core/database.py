"""
Database session management.

Configures async SQLAlchemy engine and session makers, supporting
PostgreSQL in production and a lightweight SQLite fallback in development.
"""

import logging
import sys
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base

from .config import settings

logger = logging.getLogger(__name__)

is_testing = "pytest" in sys.modules

# Initial database URLs
pg_url = settings.DATABASE_URL
sqlite_url = "sqlite+aiosqlite:///:memory:" if is_testing else "sqlite+aiosqlite:///./triage.db"

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

Base = declarative_base()

# Default session factory (imported by routers/tests)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


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
