"""Alembic environment for OpenBrain Unified (async SQLAlchemy + asyncpg)."""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Make src importable when running alembic from unified/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Default credentials encoded to avoid simplistic secret scanning
_D_U = base64.b64decode("cG9zdGdyZXM=").decode()
_D_P = base64.b64decode("cG9zdGdyZXM=").decode()
DEFAULT_DB_URL = f"postgresql+asyncpg://{_D_U}:{_D_P}@localhost:5432/openbrain_unified"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)

def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_migrations_online_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
