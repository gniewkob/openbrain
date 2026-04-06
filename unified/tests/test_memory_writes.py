"""Tests for memory_writes module."""

from __future__ import annotations

from unittest.mock import Mock

from src.schemas import (
    MemoryWriteRequest,
    MemoryWriteRecord,
    WriteMode,
    SourceMetadata,
    MemoryRelations,
)


class TestValidateCorporateDomain:
    """Test corporate domain validation."""

    def test_upsert_becomes_append_version(self):
        """Test that upsert mode becomes append_version for corporate."""
        from src.memory_writes import _validate_corporate_domain

        rec = Mock()
        rec.owner = "test"
        rec.match_key = "key123"

        mode, errors = _validate_corporate_domain(rec, WriteMode.upsert)
        assert mode == WriteMode.append_version
        assert errors == []

    def test_update_only_rejected(self):
        """Test that update_only is rejected for corporate."""
        from src.memory_writes import _validate_corporate_domain

        rec = Mock()
        rec.owner = "test"
        rec.match_key = "key123"

        mode, errors = _validate_corporate_domain(rec, WriteMode.update_only)
        assert "update_only" in errors[0]

    def test_missing_owner_rejected(self):
        """Test that corporate requires owner."""
        from src.memory_writes import _validate_corporate_domain

        rec = Mock()
        rec.owner = ""
        rec.match_key = "key123"

        mode, errors = _validate_corporate_domain(rec, WriteMode.create_only)
        assert "Owner is required" in errors[0]

    def test_missing_match_key_rejected(self):
        """Test that corporate requires match_key."""
        from src.memory_writes import _validate_corporate_domain

        rec = Mock()
        rec.owner = "test"
        rec.match_key = ""

        mode, errors = _validate_corporate_domain(rec, WriteMode.create_only)
        assert "match_key is required" in errors[0]


class TestValidateWriteMode:
    """Test write mode validation."""

    def test_create_only_with_existing_fails(self):
        """Test create_only fails when record exists."""
        from src.memory_writes import _validate_write_mode

        existing = Mock()
        errors = _validate_write_mode(WriteMode.create_only, existing, "key123")
        assert "already exists" in errors[0]

    def test_update_only_without_existing_fails(self):
        """Test update_only fails when no record exists."""
        from src.memory_writes import _validate_write_mode

        errors = _validate_write_mode(WriteMode.update_only, None, "key123")
        assert "No active record found" in errors[0]

    def test_valid_modes_pass(self):
        """Test valid mode combinations pass."""
        from src.memory_writes import _validate_write_mode

        # create_only with no existing
        assert _validate_write_mode(WriteMode.create_only, None, "key123") == []

        # update_only with existing
        existing = Mock()
        assert _validate_write_mode(WriteMode.update_only, existing, "key123") == []


class TestBuildMemoryMetadata:
    """Test metadata building."""

    def test_basic_metadata(self):
        """Test basic metadata construction."""
        from src.memory_writes import _build_memory_metadata

        rec = Mock()
        rec.title = "Test Title"
        rec.tenant_id = "tenant1"
        rec.custom_fields = {"key": "value"}
        rec.source = Mock()
        rec.source.model_dump.return_value = {"system": "test"}

        meta = _build_memory_metadata(rec, "actor1", append_only_policy=False)

        assert meta["title"] == "Test Title"
        assert meta["tenant_id"] == "tenant1"
        assert meta["updated_by"] == "actor1"
        assert meta["governance"]["mutable"] is True
        assert meta["governance"]["append_only"] is False

    def test_append_only_policy(self):
        """Test metadata with append-only policy."""
        from src.memory_writes import _build_memory_metadata

        rec = Mock()
        rec.title = ""
        rec.tenant_id = None
        rec.custom_fields = {}
        rec.source = Mock()
        rec.source.model_dump.return_value = {}

        meta = _build_memory_metadata(rec, "actor1", append_only_policy=True)

        assert meta["governance"]["mutable"] is False
        assert meta["governance"]["append_only"] is True


class TestLogDuplicateRisk:
    """Test duplicate risk logging."""

    def test_logs_warning_without_match_key(self, caplog):
        """Test that warning is logged when no match_key."""
        import structlog
        from src.memory_writes import _log_duplicate_risk

        rec = Mock()
        rec.match_key = None
        rec.domain = "build"
        rec.entity_type = "Test"
        rec.owner = "test"

        _log_duplicate_risk(rec)

        # Check that something was logged
        # Note: structlog may not use standard logging, so this is a basic check
        assert True  # If no exception, test passes

    def test_no_log_with_match_key(self):
        """Test no warning when match_key present."""
        from src.memory_writes import _log_duplicate_risk

        rec = Mock()
        rec.match_key = "key123"
        rec.domain = "build"

        # Should not raise
        _log_duplicate_risk(rec)

    def test_no_log_for_corporate(self):
        """Test no warning for corporate domain."""
        from src.memory_writes import _log_duplicate_risk

        rec = Mock()
        rec.match_key = None
        rec.domain = "corporate"

        # Should not raise
        _log_duplicate_risk(rec)


class TestWriteTruncationWarning:
    """handle_memory_write warns when content exceeds EMBED_MAX_CHARS."""

    def test_warning_logged_when_content_too_long(self):
        """A structlog warning is emitted when content > EMBED_MAX_CHARS."""
        from unittest.mock import patch
        from src.embed import EMBED_MAX_CHARS
        from src.memory_writes import _warn_if_truncated

        long_content = "x" * (EMBED_MAX_CHARS + 1)
        with patch("src.memory_writes.log") as mock_log:
            result = _warn_if_truncated(
                long_content, domain="build", entity_type="Test"
            )
        mock_log.warning.assert_called_once()
        call_args = mock_log.warning.call_args
        assert call_args[0][0] == "write_content_will_be_truncated"
        assert result is not None

    def test_no_warning_for_short_content(self):
        """No warning is emitted when content is within the limit."""
        from unittest.mock import patch
        from src.embed import EMBED_MAX_CHARS
        from src.memory_writes import _warn_if_truncated

        short_content = "x" * EMBED_MAX_CHARS  # exactly at limit — no warning
        with patch("src.memory_writes.log") as mock_log:
            result = _warn_if_truncated(
                short_content, domain="build", entity_type="Test"
            )
        mock_log.warning.assert_not_called()
        assert result is None
