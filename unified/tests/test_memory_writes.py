"""Tests for memory_writes module."""

from __future__ import annotations

from unittest.mock import Mock

from src.schemas import (
    MemoryWriteRequest,
    MemoryWriteRecord,
    WriteMode,
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
        from src.memory_writes import _log_duplicate_risk

        rec = Mock()
        rec.match_key = None
        rec.domain = "build"
        rec.entity_type = "Test"
        rec.owner = "test"

        from unittest.mock import patch

        with patch("src.memory_writes.log") as mock_log:
            _log_duplicate_risk(rec)

        mock_log.warning.assert_called_once()
        call_args = mock_log.warning.call_args
        assert call_args[0][0] == "duplicate_risk_write"

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

    def test_warning_appears_in_response_warnings(self):
        """MemoryWriteResponse.warnings contains truncation message when content > limit."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.embed import EMBED_MAX_CHARS
        from src.schemas import (
            WriteMode,
            MemoryWriteResponse,
        )

        long_content = "x" * (EMBED_MAX_CHARS + 500)
        request = MemoryWriteRequest(
            record=MemoryWriteRecord(
                content=long_content,
                domain="build",
                entity_type="Test",
            ),
            write_mode=WriteMode.upsert,
        )

        mock_session = MagicMock()
        # No existing record
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        # Mock _create_new_memory to return a clean response — we only care that
        # handle_memory_write appends the truncation warning to it
        fake_response = MemoryWriteResponse(status="created")

        with patch(
            "src.memory_writes._create_new_memory",
            new=AsyncMock(return_value=fake_response),
        ):
            from src.memory_writes import handle_memory_write

            response = asyncio.run(handle_memory_write(mock_session, request))

        assert any(
            "will be indexed for vector search" in w for w in response.warnings
        ), f"Expected truncation warning in response.warnings, got: {response.warnings}"


class TestClassifyBulkResults:
    """Test classification of bulk write results."""

    def test_classify_all_statuses(self):
        """Test classifying created, updated, versioned, and skipped statuses."""
        from src.memory_writes import _classify_bulk_results
        from src.schemas import BatchResultItem

        results = [
            BatchResultItem(input_index=0, status="created", record_id="mem1"),
            BatchResultItem(input_index=1, status="updated", record_id="mem2"),
            BatchResultItem(input_index=2, status="versioned", record_id="mem3"),
            BatchResultItem(input_index=3, status="skipped", record_id="mem4"),
            BatchResultItem(input_index=4, status="failed", record_id="mem5"),
        ]

        mem1, mem2, mem3 = Mock(), Mock(), Mock()
        id_to_mem = {
            "mem1": mem1,
            "mem2": mem2,
            "mem3": mem3,
        }

        inserted, updated, skipped = _classify_bulk_results(results, id_to_mem)

        assert inserted == [mem1]
        assert updated == [mem2, mem3]
        assert skipped == ["mem4"]

    def test_classify_missing_memory_in_dict(self):
        """Test that created/updated are ignored if not in id_to_mem."""
        from src.memory_writes import _classify_bulk_results
        from src.schemas import BatchResultItem

        results = [
            BatchResultItem(input_index=0, status="created", record_id="mem1"),
            BatchResultItem(input_index=1, status="updated", record_id="mem2"),
            BatchResultItem(input_index=2, status="skipped", record_id="mem3"),
        ]

        # id_to_mem is empty, so mem1 and mem2 won't be found
        id_to_mem = {}

        inserted, updated, skipped = _classify_bulk_results(results, id_to_mem)

        assert inserted == []
        assert updated == []
        assert skipped == ["mem3"]

    def test_classify_skipped_without_record_id(self):
        """Test skipped status when record_id is None."""
        from src.memory_writes import _classify_bulk_results
        from src.schemas import BatchResultItem

        results = [
            BatchResultItem(input_index=0, status="skipped", record_id=None),
        ]

        inserted, updated, skipped = _classify_bulk_results(results, {})

        assert inserted == []
        assert updated == []
        assert skipped == [""]
