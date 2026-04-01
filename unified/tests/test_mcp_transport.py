from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from src import mcp_transport


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.is_error = status_code >= 400

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, **kwargs):
        self.last_request = (method, path, kwargs)
        return self._response


class McpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_req_raises_on_http_error(self) -> None:
        response = _FakeResponse(404, payload={"detail": "Memory not found"})
        with patch.object(mcp_transport, "_client", return_value=_FakeClient(response)):
            with self.assertRaisesRegex(ValueError, "Backend 404"):
                await mcp_transport._safe_req("GET", "/api/memories/missing")

    async def test_safe_req_returns_success_payload_for_204(self) -> None:
        response = _FakeResponse(204, payload=None)
        with patch.object(mcp_transport, "_client", return_value=_FakeClient(response)):
            result = await mcp_transport._safe_req("DELETE", "/api/memories/x")
        self.assertEqual(result, {"status": "success"})

    async def test_safe_req_redacts_content_in_logged_payload(self) -> None:
        response = _FakeResponse(200, payload={"status": "ok"})
        payload = {
            "record": {
                "content": "secret payload",
                "domain": "build",
                "tenant_id": "tenant-a",
                "match_key": "mk-1",
                "obsidian_ref": "Vault/Private.md",
                "title": "Quarterly payroll notes",
                "custom_fields": {"nested": {"content": "nested secret"}},
            },
            "records": [
                {"content": "bulk secret", "match_key": "mk-1"},
            ],
        }
        with (
            patch.object(mcp_transport, "_client", return_value=_FakeClient(response)),
            patch.object(mcp_transport.log, "info") as log_info,
        ):
            await mcp_transport._safe_req("POST", "/write", json=payload)

        _, kwargs = log_info.call_args
        logged_payload = kwargs["payload"]
        self.assertEqual(logged_payload["record"]["content"], "[REDACTED]")
        self.assertEqual(logged_payload["record"]["tenant_id"], "[REDACTED]")
        self.assertEqual(logged_payload["record"]["match_key"], "[REDACTED]")
        self.assertEqual(logged_payload["record"]["obsidian_ref"], "[REDACTED]")
        self.assertEqual(logged_payload["record"]["title"], "[REDACTED]")
        self.assertEqual(logged_payload["record"]["custom_fields"], "[REDACTED]")
        self.assertEqual(logged_payload["records"][0]["match_key"], "[REDACTED]")
        self.assertEqual(logged_payload["records"][0]["content"], "[REDACTED]")
        self.assertEqual(payload["record"]["content"], "secret payload")
        self.assertEqual(payload["records"][0]["content"], "bulk secret")

    async def test_brain_store_returns_record_payload(self) -> None:
        response = _FakeResponse(
            200,
            payload={
                "status": "created",
                "record": {
                    "id": "mem-1",
                    "tenant_id": "tenant-a",
                    "domain": "build",
                    "entity_type": "Note",
                    "content": "x",
                    "owner": "",
                    "status": "active",
                    "version": 1,
                    "sensitivity": "internal",
                    "superseded_by": None,
                    "tags": [],
                    "relations": {},
                    "obsidian_ref": None,
                    "custom_fields": {"priority": "high"},
                    "content_hash": "abc",
                    "match_key": "mk",
                    "previous_id": None,
                    "root_id": "mem-1",
                    "valid_from": None,
                    "created_at": "2026-03-27T00:00:00Z",
                    "updated_at": "2026-03-27T00:00:00Z",
                    "created_by": "internal",
                    "updated_by": "internal",
                    "title": "Note",
                    "source": {"type": "agent"},
                },
            },
        )
        with patch.object(mcp_transport, "_client", return_value=_FakeClient(response)):
            result = await mcp_transport.brain_store(
                content="x",
                domain="build",
                tenant_id="tenant-a",
                custom_fields={"priority": "high"},
            )
        self.assertNotIn("title", result)
        self.assertEqual(result["id"], "mem-1")
        self.assertEqual(result["tenant_id"], "tenant-a")
        self.assertEqual(result["match_key"], "mk")
        self.assertEqual(result["custom_fields"], {"priority": "high"})
        self.assertEqual(result["root_id"], "mem-1")
        self.assertEqual(result["updated_by"], "internal")

    async def test_brain_search_normalizes_v1_hits_to_memory_shape(self) -> None:
        response = _FakeResponse(
            200,
            payload=[
                {
                    "record": {
                        "id": "mem-1",
                        "tenant_id": "tenant-a",
                        "domain": "build",
                        "entity_type": "Note",
                        "content": "x",
                        "owner": "",
                        "status": "active",
                        "version": 1,
                        "sensitivity": "internal",
                        "superseded_by": None,
                        "tags": [],
                        "relations": {},
                        "obsidian_ref": None,
                        "custom_fields": {"priority": "high"},
                        "content_hash": "abc",
                        "match_key": "mk",
                        "previous_id": None,
                        "root_id": "mem-1",
                        "valid_from": None,
                        "created_at": "2026-03-27T00:00:00Z",
                        "updated_at": "2026-03-27T00:00:00Z",
                        "created_by": "internal",
                        "updated_by": "internal",
                        "title": "Note",
                        "governance": {"mutable": True},
                    },
                    "score": 0.9,
                }
            ],
        )
        with patch.object(mcp_transport, "_client", return_value=_FakeClient(response)):
            result = await mcp_transport.brain_search(query="x", top_k=1)
        self.assertNotIn("title", result[0]["memory"])
        self.assertEqual(
            result,
            [
                {
                    "memory": {
                        "id": "mem-1",
                        "tenant_id": "tenant-a",
                        "domain": "build",
                        "entity_type": "Note",
                        "content": "x",
                        "owner": "",
                        "status": "active",
                        "version": 1,
                        "sensitivity": "internal",
                        "superseded_by": None,
                        "tags": [],
                        "relations": {},
                        "obsidian_ref": None,
                        "custom_fields": {"priority": "high"},
                        "content_hash": "abc",
                        "match_key": "mk",
                        "previous_id": None,
                        "root_id": "mem-1",
                        "valid_from": None,
                        "created_at": "2026-03-27T00:00:00Z",
                        "updated_at": "2026-03-27T00:00:00Z",
                        "created_by": "internal",
                        "updated_by": "internal",
                    },
                    "score": 0.9,
                }
            ],
        )

    async def test_brain_update_passes_custom_fields(self) -> None:
        response = _FakeResponse(200, payload={"id": "mem-1"})
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            await mcp_transport.brain_update(
                "mem-1",
                content="after",
                tenant_id="tenant-a",
                custom_fields={"priority": "critical"},
            )
        self.assertEqual(
            fake_client.last_request,
            (
                "PUT",
                "/api/memories/mem-1",
                {
                    "json": {
                        "content": "after",
                        "title": None,
                        "owner": None,
                        "tenant_id": "tenant-a",
                        "tags": None,
                        "custom_fields": {"priority": "critical"},
                        "obsidian_ref": None,
                        "sensitivity": None,
                    }
                },
            ),
        )

    async def test_brain_delete_returns_gateway_shape(self) -> None:
        response = _FakeResponse(204, payload=None)
        with patch.object(mcp_transport, "_client", return_value=_FakeClient(response)):
            result = await mcp_transport.brain_delete("mem-1")
        self.assertEqual(result, {"deleted": True, "id": "mem-1"})

    async def test_brain_list_uses_legacy_list_shape(self) -> None:
        response = _FakeResponse(200, payload=[{"id": "mem-1", "domain": "build"}])
        with patch.object(mcp_transport, "_client", return_value=_FakeClient(response)):
            result = await mcp_transport.brain_list(domain="build", limit=5)
        self.assertEqual(result, [{"id": "mem-1", "domain": "build"}])

    async def test_brain_sync_check_posts_json_payload(self) -> None:
        response = _FakeResponse(
            200, payload={"status": "exists", "message": "Memory exists."}
        )
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            result = await mcp_transport.brain_sync_check(match_key="mk-1")
        self.assertEqual(result, {"status": "exists", "message": "Memory exists."})
        self.assertEqual(
            fake_client.last_request,
            (
                "POST",
                "/api/memories/sync-check",
                {
                    "json": {
                        "memory_id": None,
                        "match_key": "mk-1",
                        "obsidian_ref": None,
                        "file_hash": None,
                    }
                },
            ),
        )

    async def test_brain_upsert_bulk_calls_bulk_upsert_endpoint(self) -> None:
        response = _FakeResponse(
            200, payload={"inserted": [], "updated": [], "skipped": []}
        )
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            result = await mcp_transport.brain_upsert_bulk(
                [{"match_key": "mk-1", "content": "x"}]
            )
        self.assertEqual(result, {"inserted": [], "updated": [], "skipped": []})
        self.assertEqual(
            fake_client.last_request,
            (
                "POST",
                "/api/memories/bulk-upsert",
                {"json": [{"match_key": "mk-1", "content": "x"}]},
            ),
        )

    async def test_guard_re_raises_as_tool_error(self) -> None:
        @mcp_transport.mcp_tool_guard
        async def broken():
            raise RuntimeError("boom")

        with self.assertRaisesRegex(ValueError, "Tool execution failed: boom"):
            await broken()


if __name__ == "__main__":
    unittest.main()
