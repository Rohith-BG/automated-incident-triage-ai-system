import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure the backend directory is in the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.core.config import settings
from backend.app.core.database import Base

from backend.app.models.incident import Alert, Incident, RootCauseReportModel
from backend.app.models.user import User
from backend.app.models.incident_knowledge import IncidentKnowledge
from backend.app.models.incident_resolution import IncidentResolution

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations within a synchronous sync connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def get_connectable_engine():
    """Retrieve the connectable engine, falling back to SQLite if PostgreSQL fails."""
    pg_url = settings.DATABASE_URL
    sqlite_url = "sqlite+aiosqlite:///./triage.db"

    if pg_url and "postgresql" in pg_url:
        try:
            # Attempt to connect to PostgreSQL
            test_engine = create_async_engine(pg_url, poolclass=pool.NullPool)
            async with test_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print("Alembic: Connected to PostgreSQL database successfully.")
            return test_engine
        except Exception as e:
            print(
                f"Alembic: PostgreSQL connection failed ({e}). "
                f"Falling back to local SQLite database: {sqlite_url}"
            )

    # Use SQLite fallback
    return create_async_engine(sqlite_url, poolclass=pool.NullPool)


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an AsyncEngine
    and associate a connection with the context.
    """
    connectable = await get_connectable_engine()

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
