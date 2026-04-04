"""
Database connection and session management for OpenBrain Unified.
"""

from urllib.parse import urlsplit
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import get_config

# Unified Database URL
# Local development defaults are intentionally plain strings.
_D_U = "postgres"
_D_P = "postgres"


def _uses_dev_database_credentials(db_url: str) -> bool:
    try:
        sanitized = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        parsed = urlsplit(sanitized)
    except Exception:
        return False
    return parsed.username == _D_U and parsed.password == _D_P


def validate_database_configuration() -> None:
    config = get_config()
    public_mode = config.auth.public_mode
    public_base_url = bool(config.auth.public_base_url)
    if (public_mode or public_base_url) and _uses_dev_database_credentials(config.database.url):
        raise RuntimeError(
            "PUBLIC_MODE=true or PUBLIC_BASE_URL set forbids dev default PostgreSQL "
            "credentials. Configure DATABASE_URL with a unique password."
        )


validate_database_configuration()

engine = create_async_engine(
    get_config().database.url,
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
