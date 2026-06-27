import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import backend.app.core.database as db_mod
from backend.app.core.database import init_db


@pytest.mark.asyncio
async def test_init_db_prod_missing_postgres() -> None:
    """Verify that in production mode, missing/invalid pg_url raises ValueError."""
    with patch.object(db_mod.settings, "ENVIRONMENT", "prod"), \
         patch.object(db_mod, "is_testing", False), \
         patch.object(db_mod, "pg_url", None), \
         patch.object(db_mod, "pg_engine", None):

        with pytest.raises(ValueError, match="PostgreSQL DATABASE_URL must be configured correctly"):
            await init_db()


@pytest.mark.asyncio
async def test_init_db_prod_connection_failure() -> None:
    """Verify that in production mode, connection failure raises the exception."""
    mock_engine = MagicMock()
    # Mock async context manager for connect
    mock_engine.connect.return_value.__aenter__.side_effect = Exception("Connection refused")

    with patch.object(db_mod.settings, "ENVIRONMENT", "prod"), \
         patch.object(db_mod, "is_testing", False), \
         patch.object(db_mod, "pg_url", "postgresql+asyncpg://user:pass@host/db"), \
         patch.object(db_mod, "pg_engine", mock_engine):

        with pytest.raises(Exception, match="Connection refused"):
            await init_db()


@pytest.mark.asyncio
async def test_init_db_dev_fallback_on_failure() -> None:
    """Verify that in development mode, connection failure falls back to SQLite."""
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__.side_effect = Exception("PG connection failed")

    mock_sqlite = MagicMock()
    # mock sqlite_engine.begin() async context manager
    mock_begin_ctx = AsyncMock()
    mock_sqlite.begin.return_value = mock_begin_ctx

    with patch.object(db_mod.settings, "ENVIRONMENT", "dev"), \
         patch.object(db_mod, "is_testing", False), \
         patch.object(db_mod, "pg_url", "postgresql+asyncpg://user:pass@host/db"), \
         patch.object(db_mod, "pg_engine", mock_engine), \
         patch.object(db_mod, "sqlite_engine", mock_sqlite), \
         patch.object(db_mod.AsyncSessionLocal, "configure") as mock_configure:

        await init_db()
        assert db_mod.use_sqlite_fallback is True
        mock_configure.assert_called_with(bind=mock_sqlite)
        mock_sqlite.begin.assert_called_once()
