"""
Database connection and session management for OpenBrain Unified.
"""

import os
from urllib.parse import urlsplit
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Unified Database URL
# Local development defaults are intentionally plain strings.
_D_U = "postgres"
_D_P = "postgres"

DB_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://{_D_U}:{_D_P}@localhost:5432/openbrain_unified",
)


def _uses_dev_database_credentials(db_url: str) -> bool:
    try:
        sanitized = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        parsed = urlsplit(sanitized)
    except Exception:
        return False
    return parsed.username == _D_U and parsed.password == _D_P


def validate_database_configuration() -> None:
    public_mode = os.environ.get("PUBLIC_MODE", "").lower() == "true"
    public_base_url = bool(os.environ.get("PUBLIC_BASE_URL", "").strip())
    if (public_mode or public_base_url) and _uses_dev_database_credentials(DB_URL):
        raise RuntimeError(
            "PUBLIC_MODE=true or PUBLIC_BASE_URL set forbids dev default PostgreSQL "
            "credentials. Configure DATABASE_URL with a unique password."
        )


validate_database_configuration()

engine = create_async_engine(
    DB_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # recycle idle connections every 30 min
    connect_args={
        "server_settings": {
            "statement_timeout": "30000"  # 30 s per statement (PG accepts ms as string)
        }
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations."""
    async with AsyncSessionLocal() as session:
        yield session


# Alias for FastAPI Depends
get_session = get_db_session
