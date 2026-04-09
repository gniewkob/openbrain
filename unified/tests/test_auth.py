"""Tests for auth module."""

from __future__ import annotations

import pytest


class TestPublicModeDetection:
    """Test public mode detection logic."""

    def test_public_mode_from_env(self, monkeypatch):
        """Test that PUBLIC_MODE=true enables public mode (requires INTERNAL_API_KEY + OIDC)."""
        from src import config

        monkeypatch.setenv("PUBLIC_MODE", "true")
        monkeypatch.setenv("INTERNAL_API_KEY", "a" * 32)
        monkeypatch.setenv("OIDC_ISSUER_URL", "https://auth.example.com")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.auth.public_mode is True

    def test_public_mode_requires_api_key(self, monkeypatch):
        """Test that PUBLIC_MODE=true without INTERNAL_API_KEY is rejected."""
        from src import config

        monkeypatch.setenv("PUBLIC_MODE", "true")
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
        config.get_config.cache_clear()

        with pytest.raises(Exception, match="INTERNAL_API_KEY"):
            config.get_config()

    def test_public_mode_requires_strong_api_key(self, monkeypatch):
        """Test that INTERNAL_API_KEY shorter than 32 chars is rejected in public mode."""
        from src import config

        monkeypatch.setenv("PUBLIC_MODE", "true")
        monkeypatch.setenv("INTERNAL_API_KEY", "too-short")
        monkeypatch.setenv("OIDC_ISSUER_URL", "https://auth.example.com")
        config.get_config.cache_clear()

        with pytest.raises(Exception, match="32 characters"):
            config.get_config()

    def test_public_mode_disabled_by_default(self, monkeypatch):
        """Test that public mode is disabled by default."""
        from src import config

        monkeypatch.delenv("PUBLIC_MODE", raising=False)
        monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.auth.public_mode is False

    def test_public_base_url_enables_exposure(self, monkeypatch):
        """Test that PUBLIC_BASE_URL enables public exposure (requires INTERNAL_API_KEY + OIDC)."""
        from src import config

        monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
        monkeypatch.setenv("INTERNAL_API_KEY", "b" * 32)
        monkeypatch.setenv("OIDC_ISSUER_URL", "https://auth.example.com")
        monkeypatch.delenv("PUBLIC_MODE", raising=False)
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.auth.public_base_url == "https://example.com"


class TestConfigValidation:
    """Test configuration validation."""

    def test_database_url_validation(self, monkeypatch):
        """Test that invalid database URL is rejected."""
        from src import config

        monkeypatch.setenv("DATABASE_URL", "invalid://url")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="DATABASE_URL"):
            config.get_config()

    def test_oidc_cache_default(self, monkeypatch):
        """Test default OIDC cache duration."""
        from src import config

        monkeypatch.delenv("OIDC_DISCOVERY_CACHE_S", raising=False)
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.auth.oidc_discovery_cache_s == 600

    def test_mcp_streamable_http_path_from_env(self, monkeypatch):
        """Test streamable HTTP path can be configured via MCP env var."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "/events")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.mcp.streamable_http_path == "/events"

    def test_mcp_streamable_http_path_requires_leading_slash(self, monkeypatch):
        """Test invalid streamable HTTP path is rejected."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "events")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="streamable_http_path"):
            config.get_config()

    def test_mcp_streamable_http_path_normalizes_trailing_slash(self, monkeypatch):
        """Test streamable HTTP path strips trailing slash for consistency."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "/events/")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.mcp.streamable_http_path == "/events"

    def test_mcp_streamable_http_path_rejects_root_path(self, monkeypatch):
        """Test root path is rejected to prevent redirect loops."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "/")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="redirect loops"):
            config.get_config()

    def test_mcp_streamable_http_path_rejects_query(self, monkeypatch):
        """Test streamable path with query is rejected."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "/events?x=1")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="query"):
            config.get_config()

    def test_mcp_streamable_http_path_rejects_fragment(self, monkeypatch):
        """Test streamable path with fragment is rejected."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "/events#frag")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="fragment"):
            config.get_config()

    def test_mcp_streamable_http_path_rejects_spaces(self, monkeypatch):
        """Test streamable path with spaces is rejected."""
        from src import config

        monkeypatch.setenv("MCP_STREAMABLE_HTTP_PATH", "/events path")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="spaces"):
            config.get_config()

    def test_mcp_health_probe_timeout_from_env(self, monkeypatch):
        """Test health probe timeout can be configured via MCP env var."""
        from src import config

        monkeypatch.setenv("MCP_HEALTH_PROBE_TIMEOUT_S", "2.5")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.mcp.health_probe_timeout == 2.5

    def test_mcp_health_probe_timeout_must_be_positive(self, monkeypatch):
        """Test non-positive health probe timeout is rejected."""
        from src import config

        monkeypatch.setenv("MCP_HEALTH_PROBE_TIMEOUT_S", "0")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="MCP_HEALTH_PROBE_TIMEOUT_S"):
            config.get_config()

    def test_mcp_health_probe_timeout_has_upper_bound(self, monkeypatch):
        """Test excessively high health probe timeout is rejected."""
        from src import config

        monkeypatch.setenv("MCP_HEALTH_PROBE_TIMEOUT_S", "31")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="MCP_HEALTH_PROBE_TIMEOUT_S"):
            config.get_config()

    def test_mcp_backend_timeout_from_env(self, monkeypatch):
        """Test backend timeout can be configured via MCP env var."""
        from src import config

        monkeypatch.setenv("BACKEND_TIMEOUT_S", "15.0")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.mcp.backend_timeout == 15.0

    def test_mcp_backend_timeout_must_be_positive(self, monkeypatch):
        """Test non-positive backend timeout is rejected."""
        from src import config

        monkeypatch.setenv("BACKEND_TIMEOUT_S", "0")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="BACKEND_TIMEOUT_S"):
            config.get_config()

    def test_mcp_backend_timeout_has_upper_bound(self, monkeypatch):
        """Test excessively high backend timeout is rejected."""
        from src import config

        monkeypatch.setenv("BACKEND_TIMEOUT_S", "121")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="BACKEND_TIMEOUT_S"):
            config.get_config()

    def test_mcp_health_probe_timeout_must_not_exceed_backend_timeout(
        self, monkeypatch
    ):
        """Test probe timeout cannot exceed backend timeout."""
        from src import config

        monkeypatch.setenv("MCP_HEALTH_PROBE_TIMEOUT_S", "20")
        monkeypatch.setenv("BACKEND_TIMEOUT_S", "10")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="MCP_HEALTH_PROBE_TIMEOUT_S"):
            config.get_config()

    def test_mcp_brain_url_from_env(self, monkeypatch):
        """Test backend URL can be configured via MCP env var."""
        from src import config

        monkeypatch.setenv("BRAIN_URL", "https://openbrain.internal:7010")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.mcp.brain_url == "https://openbrain.internal:7010"

    def test_mcp_brain_url_must_be_http_or_https(self, monkeypatch):
        """Test malformed backend URL is rejected."""
        from src import config

        monkeypatch.setenv("BRAIN_URL", "not-a-url")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="BRAIN_URL"):
            config.get_config()

    def test_mcp_brain_url_rejects_query(self, monkeypatch):
        """Test backend URL with query string is rejected."""
        from src import config

        monkeypatch.setenv("BRAIN_URL", "https://openbrain.internal:7010?x=1")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="query"):
            config.get_config()

    def test_mcp_brain_url_rejects_path(self, monkeypatch):
        """Test backend URL with path segment is rejected."""
        from src import config

        monkeypatch.setenv("BRAIN_URL", "https://openbrain.internal:7010/api")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="path"):
            config.get_config()

    def test_mcp_brain_url_rejects_credentials(self, monkeypatch):
        """Test backend URL with credentials is rejected."""
        from src import config

        monkeypatch.setenv("BRAIN_URL", "https://user:pass@openbrain.internal:7010")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="credentials"):
            config.get_config()

    def test_mcp_brain_url_rejects_fragment(self, monkeypatch):
        """Test backend URL with fragment is rejected."""
        from src import config

        monkeypatch.setenv("BRAIN_URL", "https://openbrain.internal:7010#frag")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="fragment"):
            config.get_config()

    def test_mcp_source_system_from_env(self, monkeypatch):
        """Test source system can be configured via MCP env var."""
        from src import config

        monkeypatch.setenv("SOURCE_SYSTEM", "codex_agent-1")
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.mcp.source_system == "codex_agent-1"

    def test_mcp_source_system_format_validation(self, monkeypatch):
        """Test malformed source system is rejected."""
        from src import config

        monkeypatch.setenv("SOURCE_SYSTEM", "Bad Value!")
        config.get_config.cache_clear()

        with pytest.raises(ValueError, match="SOURCE_SYSTEM"):
            config.get_config()


class TestInternalAPIKey:
    """Test internal API key handling."""

    def test_internal_api_key_from_env(self, monkeypatch):
        """Test that INTERNAL_API_KEY is loaded from env."""
        from src import config

        monkeypatch.setenv(
            "INTERNAL_API_KEY", "secret-key-123-long-enough-for-32-chars"
        )
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.auth.internal_api_key == "secret-key-123-long-enough-for-32-chars"

    def test_get_internal_api_key_helper(self, monkeypatch):
        """Test get_internal_api_key helper function."""
        from src import config

        monkeypatch.setenv("INTERNAL_API_KEY", "test-key-long-enough-for-32-chars")
        config.get_config.cache_clear()

        assert config.get_internal_api_key() == "test-key-long-enough-for-32-chars"


class TestCORSConfig:
    """Test CORS configuration."""

    def test_cors_origins_default(self, monkeypatch):
        """Test default CORS origins in dev mode."""
        from src import config

        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        config.get_config.cache_clear()

        cfg = config.get_config()
        origins = cfg.cors.get_origins_list()
        assert "http://localhost:*" in origins

    def test_cors_origins_from_env(self, monkeypatch):
        """Test CORS origins from environment."""
        from src import config

        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.com, https://b.com")
        config.get_config.cache_clear()

        cfg = config.get_config()
        origins = cfg.cors.get_origins_list()
        assert origins == ["https://a.com", "https://b.com"]


class TestEmbeddingConfig:
    """Test embedding service configuration."""

    def test_ollama_url_default(self, monkeypatch):
        """Test default Ollama URL."""
        from src import config

        monkeypatch.delenv("OLLAMA_URL", raising=False)
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.embedding.url == "http://localhost:11434"

    def test_embed_model_default(self, monkeypatch):
        """Test default embedding model."""
        from src import config

        monkeypatch.delenv("EMBED_MODEL", raising=False)
        config.get_config.cache_clear()

        cfg = config.get_config()
        assert cfg.embedding.model == "nomic-embed-text"


class TestConfigCaching:
    """Test configuration caching."""

    def test_config_is_cached(self, monkeypatch):
        """Test that config is cached."""
        from src import config

        config.get_config.cache_clear()

        cfg1 = config.get_config()
        cfg2 = config.get_config()

        # Should be the same object due to lru_cache
        assert cfg1 is cfg2
