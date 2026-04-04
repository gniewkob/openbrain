"""Central configuration module for OpenBrain.

Uses pydantic-settings for type-safe, validated configuration from
environment variables. All configuration is centralized here - no
scattered os.environ.get() calls in other modules.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/openbrain_unified",
        alias="DATABASE_URL",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v.startswith(("postgresql", "sqlite")):
            raise ValueError("DATABASE_URL must start with 'postgresql' or 'sqlite'")
        return v


class AuthConfig(BaseSettings):
    """Authentication and authorization configuration."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    public_mode: bool = Field(default=False, alias="PUBLIC_MODE")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")
    internal_api_key: str = Field(default="", alias="INTERNAL_API_KEY")
    oidc_issuer_url: str = Field(default="", alias="OIDC_ISSUER_URL")
    oidc_audience: str = Field(default="https://openbrain-mcp", alias="OIDC_AUDIENCE")
    oidc_discovery_cache_s: int = Field(default=600, alias="OIDC_DISCOVERY_CACHE_S")
    policy_registry_json: str = Field(
        default="", alias="OPENBRAIN_POLICY_REGISTRY_JSON"
    )
    policy_registry_path: str = Field(
        default="", alias="OPENBRAIN_POLICY_REGISTRY_PATH"
    )

    @field_validator("public_mode", mode="before")
    @classmethod
    def parse_bool(cls, v):
        """Parse boolean from string environment variable."""
        if isinstance(v, str):
            return v.lower() == "true"
        return v

    @model_validator(mode="after")
    def validate_public_mode_secrets(self) -> "AuthConfig":
        """Validate required secrets in public mode."""
        is_public = self.public_mode or bool(self.public_base_url)
        if is_public:
            if not self.internal_api_key:
                raise ValueError(
                    "INTERNAL_API_KEY is required when PUBLIC_MODE=true "
                    "or PUBLIC_BASE_URL is set"
                )
            if len(self.internal_api_key) < 32:
                raise ValueError(
                    "INTERNAL_API_KEY must be at least 32 characters in public mode"
                )
            if not self.oidc_issuer_url:
                raise ValueError(
                    "OIDC_ISSUER_URL is required when PUBLIC_MODE=true "
                    "or PUBLIC_BASE_URL is set"
                )
        return self


class EmbeddingConfig(BaseSettings):
    """Ollama embedding service configuration."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    url: str = Field(default="http://localhost:11434", alias="OLLAMA_URL")
    model: str = Field(default="nomic-embed-text", alias="EMBED_MODEL")
    cache_size: int = Field(default=1000, alias="EMBED_CACHE_SIZE")


class ObsidianConfig(BaseSettings):
    """Obsidian integration configuration."""

    model_config = SettingsConfigDict(env_prefix="OBSIDIAN_", case_sensitive=False)

    cli_command: str = Field(default="obsidian", alias="CLI_COMMAND")
    vault_paths: str = Field(default="", alias="VAULT_PATHS")  # JSON string
    data_dir: str = Field(default=".openbrain", alias="DATA_DIR")


class CORSConfig(BaseSettings):
    """CORS configuration."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    allowed_origins: str = Field(default="", alias="CORS_ALLOWED_ORIGINS")

    def get_origins_list(self) -> list[str]:
        """Parse comma-separated origins into list."""
        if not self.allowed_origins:
            return ["http://localhost:*", "http://127.0.0.1:*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


class RedisConfig(BaseSettings):
    """Redis configuration for rate limiting."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    url: str = Field(default="memory://", alias="REDIS_URL")


class MCPConfig(BaseSettings):
    """MCP transport configuration."""

    model_config = SettingsConfigDict(env_prefix="MCP_", case_sensitive=False)

    brain_url: str = Field(default="http://127.0.0.1:80", alias="BRAIN_URL")
    backend_timeout: float = Field(default=30.0, alias="BACKEND_TIMEOUT_S")
    source_system: str = Field(default="other", alias="SOURCE_SYSTEM")


class AppConfig(BaseSettings):
    """Main application configuration.

    All settings are loaded from environment variables with sensible defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined here
    )

    # Database
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    # Auth
    auth: AuthConfig = Field(default_factory=AuthConfig)

    # Embedding
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    # Obsidian
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)

    # CORS
    cors: CORSConfig = Field(default_factory=CORSConfig)

    # Redis
    redis: RedisConfig = Field(default_factory=RedisConfig)

    # MCP
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    # Rate limiting
    rate_limit_per_minute: int = Field(default=100, alias="AUTH_RATE_LIMIT_RPM")


@lru_cache()
def get_config() -> AppConfig:
    """Get cached application configuration.

    The configuration is loaded once and cached for the lifetime of the process.
    """
    return AppConfig()


# Backwards compatibility - re-export commonly used settings
def get_database_url() -> str:
    """Get database URL."""
    return get_config().database.url


def is_public_mode() -> bool:
    """Check if running in public mode."""
    return get_config().auth.public_mode


def get_internal_api_key() -> str:
    """Get internal API key for MCP gateway."""
    return get_config().auth.internal_api_key


def get_public_base_url() -> str:
    """Get public base URL."""
    return get_config().auth.public_base_url


def get_oidc_issuer_url() -> str:
    """Get OIDC issuer URL."""
    return get_config().auth.oidc_issuer_url
