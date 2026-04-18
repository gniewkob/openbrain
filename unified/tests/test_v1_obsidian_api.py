"""Tests for api/v1/obsidian.py — uncovered branches via TestClient + mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.common.obsidian_adapter import ObsidianCliError, ObsidianNote
from src.schemas import ObsidianExportItem, ObsidianExportResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_app():
    from src.main import app

    return app


def _client():
    app = _get_app()
    from src.auth import require_auth

    app.dependency_overrides[require_auth] = lambda: {"sub": "local-dev"}
    return TestClient(app, raise_server_exceptions=False), app


def _restore(app):
    app.dependency_overrides.clear()


def _note(
    vault="my-vault", path="Notes/test.md", title="Test", content="# Test\nHello"
):
    return ObsidianNote(
        vault=vault,
        path=path,
        title=title,
        content=content,
        frontmatter={"tags": ["test"]},
        tags=["test"],
        file_hash="abc123",
    )


_ADAPTER_PATH = "src.api.v1.obsidian.ObsidianCliAdapter"


# ---------------------------------------------------------------------------
# /vaults — list + error
# ---------------------------------------------------------------------------


def test_v1_obsidian_vaults_success():
    client, app = _client()
    try:
        mock_adapter = MagicMock()
        mock_adapter.list_vaults = AsyncMock(return_value=["vault1", "vault2"])
        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.get("/api/v1/obsidian/vaults")
        assert r.status_code == 200
        assert "vault1" in r.json()
    finally:
        _restore(app)


def test_v1_obsidian_vaults_error():
    client, app = _client()
    try:
        mock_adapter = MagicMock()
        mock_adapter.list_vaults = AsyncMock(side_effect=ObsidianCliError("not found"))
        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.get("/api/v1/obsidian/vaults")
        assert r.status_code == 503
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /read-note — success + error
# ---------------------------------------------------------------------------


def test_v1_obsidian_read_note_success():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.read_note = AsyncMock(return_value=note)
        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/read-note",
                json={"vault": "my-vault", "path": "Notes/test.md"},
            )
        assert r.status_code == 200
        assert r.json()["title"] == "Test"
    finally:
        _restore(app)


def test_v1_obsidian_read_note_error():
    client, app = _client()
    try:
        mock_adapter = MagicMock()
        mock_adapter.read_note = AsyncMock(
            side_effect=ObsidianCliError("vault missing")
        )
        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/read-note",
                json={"vault": "my-vault", "path": "Notes/test.md"},
            )
        assert r.status_code == 503
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /sync — with explicit paths + with adapter list_files + error
# ---------------------------------------------------------------------------


_SYNC_PATCHES = [
    "src.api.v1.obsidian.note_to_memory_write_record",
    "src.api.v1.obsidian.MemoryWriteManyRequest",
]


def test_v1_obsidian_sync_with_explicit_paths():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.read_note = AsyncMock(return_value=note)

        mock_result = MagicMock()
        mock_result.summary = {"created": 1, "updated": 0, "skipped": 0, "failed": 0}
        mock_result.results = []

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.handle_memory_write_many",
                AsyncMock(return_value=mock_result),
            ),
            patch(
                "src.api.v1.obsidian.note_to_memory_write_record",
                return_value=MagicMock(),
            ),
            patch("src.api.v1.obsidian.MemoryWriteManyRequest"),
        ):
            r = client.post(
                "/api/v1/obsidian/sync",
                json={
                    "vault": "my-vault",
                    "paths": ["Notes/test.md"],
                    "domain": "build",
                    "entity_type": "Note",
                    "owner": "alice",
                },
            )
        assert r.status_code == 200
    finally:
        _restore(app)


def test_v1_obsidian_sync_uses_adapter_list_files():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.list_files = AsyncMock(return_value=["Notes/auto.md"])
        mock_adapter.read_note = AsyncMock(return_value=note)

        mock_result = MagicMock()
        mock_result.summary = {"created": 0, "updated": 1, "skipped": 0, "failed": 0}
        mock_result.results = []

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.handle_memory_write_many",
                AsyncMock(return_value=mock_result),
            ),
            patch(
                "src.api.v1.obsidian.note_to_memory_write_record",
                return_value=MagicMock(),
            ),
            patch("src.api.v1.obsidian.MemoryWriteManyRequest"),
        ):
            r = client.post(
                "/api/v1/obsidian/sync",
                json={
                    "vault": "my-vault",
                    "domain": "build",
                    "entity_type": "Note",
                    "owner": "alice",
                },
            )
        assert r.status_code == 200
    finally:
        _restore(app)


def test_v1_obsidian_sync_error():
    client, app = _client()
    try:
        mock_adapter = MagicMock()
        mock_adapter.list_files = AsyncMock(
            side_effect=ObsidianCliError("adapter failure")
        )
        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/sync",
                json={
                    "vault": "my-vault",
                    "domain": "build",
                    "entity_type": "Note",
                    "owner": "alice",
                },
            )
        assert r.status_code == 503
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /write-note — success (new) + error
# ---------------------------------------------------------------------------


def test_v1_obsidian_write_note_success():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=False)
        mock_adapter.write_note = AsyncMock(return_value=note)

        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/write-note",
                json={"vault": "my-vault", "path": "Notes/new.md", "content": "# New"},
            )
        assert r.status_code == 200
        assert r.json()["created"] is True  # exists=False → created=True
    finally:
        _restore(app)


def test_v1_obsidian_write_note_overwrite():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=True)
        mock_adapter.write_note = AsyncMock(return_value=note)

        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/write-note",
                json={
                    "vault": "my-vault",
                    "path": "Notes/existing.md",
                    "content": "updated",
                },
            )
        assert r.status_code == 200
        assert r.json()["created"] is False
    finally:
        _restore(app)


def test_v1_obsidian_write_note_error():
    client, app = _client()
    try:
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=False)
        mock_adapter.write_note = AsyncMock(
            side_effect=ObsidianCliError("write failed")
        )

        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/write-note",
                json={"vault": "my-vault", "path": "Notes/new.md", "content": "# New"},
            )
        assert r.status_code == 503
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /export — memory_ids path + query path + no ids/query raises 422
# ---------------------------------------------------------------------------


def _mock_memory_out(mid="m1", title="Memory Title"):
    mem = MagicMock()
    mem.id = mid
    mem.title = title
    mem.domain = "build"
    mem.content = "some content"
    return mem


def test_v1_obsidian_export_with_memory_ids():
    client, app = _client()
    try:
        mem = _mock_memory_out()
        note = _note(path="memories/Memory_Title.md", title="Memory Title")
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=False)
        mock_adapter.write_note = AsyncMock(return_value=note)

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch("src.api.v1.obsidian.get_memory", AsyncMock(return_value=mem)),
        ):
            r = client.post(
                "/api/v1/obsidian/export",
                json={"vault": "my-vault", "memory_ids": ["m1"]},
            )
        assert r.status_code == 200
        assert r.json()["exported_count"] == 1
    finally:
        _restore(app)


def test_v1_obsidian_export_with_query():
    client, app = _client()
    try:
        mem = _mock_memory_out()
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=False)
        mock_adapter.write_note = AsyncMock(return_value=note)

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.search_memories",
                AsyncMock(return_value=[(mem, 0.9)]),
            ),
        ):
            r = client.post(
                "/api/v1/obsidian/export",
                json={"vault": "my-vault", "query": "test query"},
            )
        assert r.status_code == 200
    finally:
        _restore(app)


def test_v1_obsidian_export_with_query_and_domain_filter():
    client, app = _client()
    try:
        mem_build = _mock_memory_out("m1")
        mem_build.domain = "build"
        mem_corp = _mock_memory_out("m2")
        mem_corp.domain = "corporate"
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=False)
        mock_adapter.write_note = AsyncMock(return_value=note)

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.search_memories",
                AsyncMock(return_value=[(mem_build, 0.9), (mem_corp, 0.8)]),
            ),
        ):
            r = client.post(
                "/api/v1/obsidian/export",
                json={"vault": "my-vault", "query": "test", "domain": "build"},
            )
        assert r.status_code == 200
        assert r.json()["exported_count"] == 1  # corp filtered out
    finally:
        _restore(app)


def test_v1_obsidian_export_no_ids_no_query_returns_422():
    client, app = _client()
    try:
        r = client.post(
            "/api/v1/obsidian/export",
            json={"vault": "my-vault"},
        )
        assert r.status_code == 422
    finally:
        _restore(app)


def test_v1_obsidian_export_write_error_captured():
    client, app = _client()
    try:
        mem = _mock_memory_out()
        mock_adapter = MagicMock()
        mock_adapter.note_exists = AsyncMock(return_value=False)
        mock_adapter.write_note = AsyncMock(side_effect=Exception("write failed"))

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch("src.api.v1.obsidian.get_memory", AsyncMock(return_value=mem)),
        ):
            r = client.post(
                "/api/v1/obsidian/export",
                json={"vault": "my-vault", "memory_ids": ["m1"]},
            )
        assert r.status_code == 200
        assert len(r.json()["errors"]) == 1  # error captured, not raised
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /sync-status
# ---------------------------------------------------------------------------


def test_v1_obsidian_sync_status():
    client, app = _client()
    try:
        mock_tracker = MagicMock()
        mock_tracker.get_stats.return_value = {
            "total_tracked": 5,
            "never_synced": 2,
            "synced_recently": 3,
            "storage_path": "/tmp/sync",
        }
        with patch(
            "src.api.v1.obsidian._get_sync_tracker",
            AsyncMock(return_value=mock_tracker),
        ):
            r = client.get("/api/v1/obsidian/sync-status")
        assert r.status_code == 200
        assert r.json()["total_tracked"] == 5
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /update-note — success + error
# ---------------------------------------------------------------------------


def test_v1_obsidian_update_note_success():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.update_note = AsyncMock(return_value=note)

        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/update-note",
                params={
                    "vault": "my-vault",
                    "path": "Notes/test.md",
                    "content": "updated",
                },
            )
        assert r.status_code == 200
        assert r.json()["created"] is False
    finally:
        _restore(app)


def test_v1_obsidian_update_note_with_tags():
    client, app = _client()
    try:
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.update_note = AsyncMock(return_value=note)

        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            # list params need separate key=value pairs to encode as repeated query params
            r = client.post(
                "/api/v1/obsidian/update-note",
                params=[
                    ("vault", "my-vault"),
                    ("path", "Notes/test.md"),
                    ("tags", "tag1"),
                    ("tags", "tag2"),
                ],
            )
        assert r.status_code == 200
        mock_adapter.update_note.assert_called_once()
    finally:
        _restore(app)


def test_v1_obsidian_update_note_error():
    client, app = _client()
    try:
        mock_adapter = MagicMock()
        mock_adapter.update_note = AsyncMock(side_effect=ObsidianCliError("not found"))

        with patch(_ADAPTER_PATH, return_value=mock_adapter):
            r = client.post(
                "/api/v1/obsidian/update-note",
                params={"vault": "my-vault", "path": "Notes/missing.md"},
            )
        assert r.status_code == 503
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /bidirectional-sync — success + timeout
# ---------------------------------------------------------------------------


def _mock_bidir_result():
    from datetime import datetime

    result = MagicMock()
    result.started_at = datetime(2026, 1, 1, 0, 0, 0)
    result.completed_at = datetime(2026, 1, 1, 0, 0, 1)
    result.changes_detected = 0
    result.changes_applied = 0
    result.conflicts = 0
    result.errors = []
    result.details = []
    return result


def test_v1_obsidian_bidirectional_sync_success():
    client, app = _client()
    try:
        mock_engine = MagicMock()
        mock_engine.sync = AsyncMock(return_value=_mock_bidir_result())
        mock_adapter = MagicMock()

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian._get_sync_engine",
                AsyncMock(return_value=mock_engine),
            ),
        ):
            r = client.post(
                "/api/v1/obsidian/bidirectional-sync",
                json={"vault": "my-vault"},
            )
        assert r.status_code == 200
        assert r.json()["changes_detected"] == 0
    finally:
        _restore(app)


def test_v1_obsidian_bidirectional_sync_timeout():
    import asyncio

    client, app = _client()
    try:
        mock_engine = MagicMock()
        mock_engine.sync = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_adapter = MagicMock()

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian._get_sync_engine",
                AsyncMock(return_value=mock_engine),
            ),
        ):
            r = client.post(
                "/api/v1/obsidian/bidirectional-sync",
                json={"vault": "my-vault"},
            )
        assert r.status_code == 503
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# /collection — success + domain filter + ObsidianCliError on index write
# ---------------------------------------------------------------------------


def test_v1_obsidian_collection_success():

    client, app = _client()
    try:
        mem = _mock_memory_out()
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.write_note = AsyncMock(return_value=note)

        export_response = ObsidianExportResponse(
            vault="my-vault",
            folder="Collections/test-col",
            exported_count=1,
            exported=[
                ObsidianExportItem(memory_id="m1", path="p.md", title="T", created=True)
            ],
            errors=[],
        )

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.search_memories",
                AsyncMock(return_value=[(mem, 0.9)]),
            ),
            patch(
                "src.api.v1.obsidian.v1_obsidian_export",
                AsyncMock(return_value=export_response),
            ),
            patch("src.api.v1.obsidian.build_collection_index", return_value="# Index"),
        ):
            r = client.post(
                "/api/v1/obsidian/collection",
                json={
                    "query": "test query",
                    "collection_name": "test-col",
                    "vault": "my-vault",
                },
            )
        assert r.status_code == 200
        assert r.json()["collection_name"] == "test-col"
    finally:
        _restore(app)


def test_v1_obsidian_collection_with_domain_filter():

    client, app = _client()
    try:
        mem_build = _mock_memory_out("m1")
        mem_build.domain = "build"
        mem_corp = _mock_memory_out("m2")
        mem_corp.domain = "corporate"
        note = _note()
        mock_adapter = MagicMock()
        mock_adapter.write_note = AsyncMock(return_value=note)

        export_response = ObsidianExportResponse(
            vault="my-vault",
            folder="Collections/test-col",
            exported_count=1,
            exported=[
                ObsidianExportItem(memory_id="m1", path="p.md", title="T", created=True)
            ],
            errors=[],
        )

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.search_memories",
                AsyncMock(return_value=[(mem_build, 0.9), (mem_corp, 0.8)]),
            ),
            patch(
                "src.api.v1.obsidian.v1_obsidian_export",
                AsyncMock(return_value=export_response),
            ),
            patch("src.api.v1.obsidian.build_collection_index", return_value="# Index"),
        ):
            r = client.post(
                "/api/v1/obsidian/collection",
                json={
                    "query": "test",
                    "collection_name": "test-col",
                    "vault": "my-vault",
                    "domain": "build",
                },
            )
        assert r.status_code == 200
    finally:
        _restore(app)


def test_v1_obsidian_collection_index_write_error():

    client, app = _client()
    try:
        mem = _mock_memory_out()
        mock_adapter = MagicMock()
        mock_adapter.write_note = AsyncMock(
            side_effect=ObsidianCliError("write failed")
        )

        export_response = ObsidianExportResponse(
            vault="my-vault",
            folder="Collections/test-col",
            exported_count=0,
            exported=[],
            errors=[],
        )

        with (
            patch(_ADAPTER_PATH, return_value=mock_adapter),
            patch(
                "src.api.v1.obsidian.search_memories",
                AsyncMock(return_value=[(mem, 0.9)]),
            ),
            patch(
                "src.api.v1.obsidian.v1_obsidian_export",
                AsyncMock(return_value=export_response),
            ),
            patch("src.api.v1.obsidian.build_collection_index", return_value="# Index"),
        ):
            r = client.post(
                "/api/v1/obsidian/collection",
                json={
                    "query": "test",
                    "collection_name": "test-col",
                    "vault": "my-vault",
                },
            )
        assert r.status_code == 503
    finally:
        _restore(app)
