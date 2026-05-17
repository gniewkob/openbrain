"""Tests for the config module."""

import pytest
from pydantic import ValidationError

from unified.src.config import AuthConfig, CORSConfig, DatabaseConfig, MCPConfig

class TestDatabaseConfig:
    def test_validate_url_postgresql(self):
        url = "postgresql://user:pass@localhost:5432/db"
        assert DatabaseConfig.validate_url(url) == url

    def test_validate_url_sqlite(self):
        url = "sqlite:///db.sqlite3"
        assert DatabaseConfig.validate_url(url) == url

    def test_validate_url_invalid(self):
        with pytest.raises(ValueError, match="DATABASE_URL must start with 'postgresql' or 'sqlite'"):
            DatabaseConfig.validate_url("mysql://user:pass@localhost:3306/db")

class TestCORSConfig:
    def test_get_origins_list_empty(self):
        config = CORSConfig(CORS_ALLOWED_ORIGINS="")
        assert config.get_origins_list() == ["http://localhost:*", "http://127.0.0.1:*"]

    def test_get_origins_list_with_values(self):
        config = CORSConfig(CORS_ALLOWED_ORIGINS="http://example.com, https://test.org ")
        assert config.get_origins_list() == ["http://example.com", "https://test.org"]

class TestMCPConfig:
    def test_validate_streamable_http_path_valid(self):
        assert MCPConfig.validate_streamable_http_path("/valid/path") == "/valid/path"
        assert MCPConfig.validate_streamable_http_path("/trailing/") == "/trailing"

    def test_validate_streamable_http_path_invalid_starts_with(self):
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must start with '/'"):
            MCPConfig.validate_streamable_http_path("invalid/path")

    def test_validate_streamable_http_path_root(self):
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not be '/' to avoid redirect loops"):
            MCPConfig.validate_streamable_http_path("/")

    def test_validate_streamable_http_path_invalid_chars(self):
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include query, fragment, or spaces"):
            MCPConfig.validate_streamable_http_path("/path?query=1")
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include query, fragment, or spaces"):
            MCPConfig.validate_streamable_http_path("/path#frag")
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include query, fragment, or spaces"):
            MCPConfig.validate_streamable_http_path("/path with space")

    def test_validate_streamable_http_path_double_slash(self):
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include backslashes or double slashes"):
            MCPConfig.validate_streamable_http_path("/path//double")
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include backslashes or double slashes"):
            MCPConfig.validate_streamable_http_path("/path\\back")

    def test_validate_streamable_http_path_dot_segments(self):
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include '.' or '..' segments"):
            MCPConfig.validate_streamable_http_path("/path/../test")
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must not include '.' or '..' segments"):
            MCPConfig.validate_streamable_http_path("/path/./test")

    def test_validate_streamable_http_path_too_long(self):
        with pytest.raises(ValueError, match="MCP_STREAMABLE_HTTP_PATH must be <= 128 characters"):
            MCPConfig.validate_streamable_http_path("/" + "a" * 128)

    def test_validate_health_probe_timeout(self):
        assert MCPConfig.validate_health_probe_timeout(10.0) == 10.0

        with pytest.raises(ValueError, match="MCP_HEALTH_PROBE_TIMEOUT_S must be finite"):
            MCPConfig.validate_health_probe_timeout(float('inf'))

        with pytest.raises(ValueError, match="MCP_HEALTH_PROBE_TIMEOUT_S must be > 0"):
            MCPConfig.validate_health_probe_timeout(0.0)

        with pytest.raises(ValueError, match="MCP_HEALTH_PROBE_TIMEOUT_S must be <= 30"):
            MCPConfig.validate_health_probe_timeout(31.0)

    def test_validate_backend_timeout(self):
        assert MCPConfig.validate_backend_timeout(60.0) == 60.0

        with pytest.raises(ValueError, match="BACKEND_TIMEOUT_S must be finite"):
            MCPConfig.validate_backend_timeout(float('inf'))

        with pytest.raises(ValueError, match="BACKEND_TIMEOUT_S must be > 0"):
            MCPConfig.validate_backend_timeout(0.0)

        with pytest.raises(ValueError, match="BACKEND_TIMEOUT_S must be <= 120"):
            MCPConfig.validate_backend_timeout(121.0)

    def test_validate_brain_url_valid(self):
        assert MCPConfig.validate_brain_url("https://example.com") == "https://example.com"
        assert MCPConfig.validate_brain_url("http://example.com:8080/") == "http://example.com:8080"

    def test_validate_brain_url_invalid(self):
        with pytest.raises(ValueError, match="BRAIN_URL must not include whitespace"):
            MCPConfig.validate_brain_url("http://exam ple.com")

        with pytest.raises(ValueError, match="BRAIN_URL must be a valid http\\(s\\) URL"):
            MCPConfig.validate_brain_url("ftp://example.com")

        with pytest.raises(ValueError, match="BRAIN_URL must not include credentials"):
            MCPConfig.validate_brain_url("http://user:pass@example.com")

        with pytest.raises(ValueError, match="BRAIN_URL must not include path"):
            MCPConfig.validate_brain_url("http://example.com/path")

        with pytest.raises(ValueError, match="BRAIN_URL must not include query params or fragment"):
            MCPConfig.validate_brain_url("http://example.com?query=1")

        with pytest.raises(ValueError, match="BRAIN_URL must not include query params or fragment"):
            MCPConfig.validate_brain_url("http://example.com#frag")

    def test_validate_source_system(self):
        assert MCPConfig.validate_source_system("valid-slug_1") == "valid-slug_1"
        assert MCPConfig.validate_source_system("A_Slug") == "a_slug"  # converts to lower

        with pytest.raises(ValueError, match="MCP_SOURCE_SYSTEM/SOURCE_SYSTEM must match"):
            MCPConfig.validate_source_system("-invalid")  # can't start with hyphen

        with pytest.raises(ValueError, match="MCP_SOURCE_SYSTEM/SOURCE_SYSTEM must match"):
            MCPConfig.validate_source_system("invalid space")

    def test_validate_timeout_relationship(self):
        # Default is health 5.0 <= backend 30.0, so this shouldn't raise
        config = MCPConfig()
        assert config.health_probe_timeout <= config.backend_timeout

        with pytest.raises(ValidationError, match="MCP_HEALTH_PROBE_TIMEOUT_S must be <= BACKEND_TIMEOUT_S"):
            MCPConfig(MCP_HEALTH_PROBE_TIMEOUT_S=30.0, BACKEND_TIMEOUT_S=10.0)

class TestAuthConfig:
    def test_parse_bool(self):
        assert AuthConfig.parse_bool("true") is True
        assert AuthConfig.parse_bool("TRUE") is True
        assert AuthConfig.parse_bool("false") is False
        assert AuthConfig.parse_bool("FALSE") is False
        assert AuthConfig.parse_bool(True) is True
        assert AuthConfig.parse_bool(False) is False

    def test_validate_public_mode_secrets_not_public(self):
        config = AuthConfig(PUBLIC_MODE="false")
        assert config.public_mode is False

    def test_validate_public_mode_secrets_valid(self):
        config = AuthConfig(
            PUBLIC_MODE="true",
            INTERNAL_API_KEY="a" * 32,
            OIDC_ISSUER_URL="https://example.com"
        )
        assert config.public_mode is True

    def test_validate_public_mode_secrets_missing_key(self):
        with pytest.raises(ValidationError) as exc_info:
            AuthConfig(PUBLIC_MODE="true")
        assert "INTERNAL_API_KEY is required when PUBLIC_MODE=true or PUBLIC_BASE_URL is set" in str(exc_info.value)

    def test_validate_public_mode_secrets_short_key(self):
        with pytest.raises(ValidationError) as exc_info:
            AuthConfig(PUBLIC_MODE="true", INTERNAL_API_KEY="short")
        assert "INTERNAL_API_KEY must be at least 32 characters in public mode" in str(exc_info.value)
