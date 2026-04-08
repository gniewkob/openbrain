from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src import mcp_transport


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_TESTS = ROOT / "mcp-gateway" / "tests"
if str(GATEWAY_TESTS) not in sys.path:
    sys.path.insert(0, str(GATEWAY_TESTS))

from helpers import load_gateway_main

try:
    gateway = load_gateway_main()
    _GATEWAY_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    gateway = None
    _GATEWAY_IMPORT_ERROR = exc


def _drop_none(value):
    if isinstance(value, dict):
        return {
            key: _drop_none(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value


LEGACY_MEMORY = {
    "id": "mem-1",
    "tenant_id": None,
    "domain": "build",
    "entity_type": "Note",
    "content": "payload",
    "owner": "",
    "status": "active",
    "version": 1,
    "sensitivity": "internal",
    "superseded_by": None,
    "tags": ["parity"],
    "relations": {"parent": [], "related": [], "depends_on": [], "supersedes": []},
    "obsidian_ref": None,
    "custom_fields": {},
    "content_hash": "abc123",
    "match_key": "mk-1",
    "previous_id": None,
    "root_id": "mem-1",
    "valid_from": None,
    "created_at": "2026-03-27T00:00:00Z",
    "updated_at": "2026-03-27T00:00:00Z",
    "created_by": "internal",
    "updated_by": "internal",
}

V1_RECORD = {
    **LEGACY_MEMORY,
    "title": "Note",
    "summary": None,
    "source": {"type": "agent", "system": "chatgpt", "reference": None},
    "governance": {"mutable": True, "append_only": False, "retention_class": "default"},
    "updated_by": "internal",
}


class _FakeResponse:
    def __init__(self, status_code: int, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.is_error = status_code >= 400
        self.text = "" if payload is None else str(payload)

    def json(self):
        return self._payload


class _GatewayClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, path: str, json=None):
        # Gateway now uses V1 endpoints
        if path == "/api/v1/memory/write":
            return _FakeResponse(200, {"status": "created", "record": LEGACY_MEMORY})
        if path == "/api/v1/memory/find":
            return _FakeResponse(200, [{"record": LEGACY_MEMORY, "score": 0.9}])
        if path == "/api/v1/memory/sync-check":
            return _FakeResponse(
                200,
                {"status": "exists", "message": "Memory exists.", "match_key": "mk-1"},
            )
        if path == "/api/v1/memory/bulk-upsert":
            return _FakeResponse(200, {"inserted": [], "updated": [], "skipped": []})
        if path == "/api/v1/memory/maintain":
            return _FakeResponse(
                200,
                {
                    "dry_run": True,
                    "total_active": 0,
                    "dedup_count": 0,
                    "owners_normalized": 0,
                    "links_fixed": 0,
                    "actions": [],
                },
            )
        raise AssertionError(f"Unexpected POST path: {path}")

    async def get(self, path: str, params=None):
        if path == "/api/memories":
            return _FakeResponse(200, [LEGACY_MEMORY])
        if path.startswith("/api/v1/memory/"):
            return _FakeResponse(200, V1_RECORD)
        raise AssertionError(f"Unexpected GET path: {path}")

    async def put(self, path: str, json=None):
        if path == "/api/memories/mem-1":
            return _FakeResponse(200, LEGACY_MEMORY)
        raise AssertionError(f"Unexpected PUT path: {path}")

    async def patch(self, path: str, json=None):
        if path.startswith("/api/v1/memory/"):
            return _FakeResponse(200, V1_RECORD)
        raise AssertionError(f"Unexpected PATCH path: {path}")

    async def delete(self, path: str):
        if path in ("/api/memories/mem-1", "/api/v1/memory/mem-1"):
            return _FakeResponse(204, None)
        raise AssertionError(f"Unexpected DELETE path: {path}")


class _TransportClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, **kwargs):
        if method == "POST" and path == "/api/v1/memory/write":
            return _FakeResponse(200, {"status": "created", "record": V1_RECORD})
        if method == "POST" and path == "/api/v1/memory/find":
            payload = kwargs.get("json", {})
            if payload.get("sort") == "updated_at_desc":
                return _FakeResponse(200, [LEGACY_MEMORY])
            return _FakeResponse(200, [{"record": V1_RECORD, "score": 0.9}])
        if method == "POST" and path == "/api/v1/memory/sync-check":
            return _FakeResponse(
                200,
                {"status": "exists", "message": "Memory exists.", "match_key": "mk-1"},
            )
        if method == "POST" and path == "/api/v1/memory/bulk-upsert":
            return _FakeResponse(200, {"inserted": [], "updated": [], "skipped": []})
        if method == "POST" and path == "/api/v1/memory/maintain":
            return _FakeResponse(
                200,
                {
                    "dry_run": True,
                    "total_active": 0,
                    "dedup_count": 0,
                    "owners_normalized": 0,
                    "links_fixed": 0,
                    "actions": [],
                },
            )
        if method == "GET" and path == "/api/v1/memory/mem-1":
            return _FakeResponse(200, V1_RECORD)
        if method == "PUT" and path == "/api/memories/mem-1":
            return _FakeResponse(200, V1_RECORD)
        if method == "PATCH" and path.startswith("/api/v1/memory/"):
            return _FakeResponse(200, V1_RECORD)
        if method == "GET" and path == "/api/memories":
            return _FakeResponse(200, [LEGACY_MEMORY])
        if method == "DELETE" and path in ("/api/memories/mem-1", "/api/v1/memory/mem-1"):
            return _FakeResponse(204, None)
        raise AssertionError(f"Unexpected transport request: {method} {path}")


@unittest.skipIf(
    gateway is None, f"gateway test deps unavailable: {_GATEWAY_IMPORT_ERROR}"
)
class TransportParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_capabilities_parity_for_shared_backend_and_tiers(self) -> None:
        backend = {
            "status": "ok",
            "url": "http://127.0.0.1:7010",
            "api": "reachable",
            "db": "ok",
            "vector_store": "ok",
            "probe": "readyz",
        }
        with (
            patch("_gateway_src.main._get_backend_status", return_value=backend),
            patch.object(mcp_transport, "_get_backend_status", return_value=backend),
            patch("_gateway_src.main._obsidian_local_tools_enabled", return_value=False),
            patch.object(mcp_transport, "ENABLE_HTTP_OBSIDIAN_TOOLS", False),
        ):
            gateway_caps = await gateway.brain_capabilities()
            transport_caps = await mcp_transport.brain_capabilities()

        self.assertEqual(gateway_caps["backend"], transport_caps["backend"])
        self.assertEqual(gateway_caps["tier_1_core"]["tools"], transport_caps["tier_1_core"]["tools"])
        self.assertEqual(gateway_caps["tier_3_admin"]["tools"], transport_caps["tier_3_admin"]["tools"])
        self.assertEqual(
            set(gateway_caps["tier_2_advanced"]["tools"]),
            set(transport_caps["tier_2_advanced"]["tools"]),
        )
        self.assertEqual(gateway_caps["obsidian"]["status"], transport_caps["obsidian"]["status"])
        self.assertEqual(gateway_caps["obsidian"]["tools"], transport_caps["obsidian"]["tools"])

    async def test_store_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = (
                await gateway.brain_store(
                    content="payload", domain="build", match_key="mk-1"
                )
            ).model_dump(exclude_none=True)
            transport_result = await mcp_transport.brain_store(
                content="payload", domain="build", match_key="mk-1"
            )
        self.assertEqual(_drop_none(transport_result), _drop_none(gateway_result))

    async def test_list_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = await gateway.brain_list(domain="build", limit=1)
            transport_result = await mcp_transport.brain_list(domain="build", limit=1)
        self.assertEqual(transport_result, gateway_result)

    async def test_get_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = (await gateway.brain_get("mem-1")).model_dump(
                exclude_none=True
            )
            transport_result = await mcp_transport.brain_get("mem-1")
        self.assertEqual(_drop_none(transport_result), _drop_none(gateway_result))

    async def test_search_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = await gateway.brain_search(
                query="payload", top_k=1, domain="build"
            )
            transport_result = await mcp_transport.brain_search(
                query="payload", top_k=1, domain="build"
            )
        self.assertEqual(transport_result, gateway_result)

    async def test_update_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = (
                await gateway.brain_update(
                    memory_id="mem-1", content="payload", title="Note"
                )
            ).model_dump(exclude_none=True)
            transport_result = await mcp_transport.brain_update(
                memory_id="mem-1", content="payload", title="Note"
            )
        self.assertEqual(_drop_none(transport_result), _drop_none(gateway_result))

    async def test_delete_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = await gateway.brain_delete("mem-1")
            transport_result = await mcp_transport.brain_delete("mem-1")
        self.assertEqual(transport_result, gateway_result)

    async def test_sync_check_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = await gateway.brain_sync_check(match_key="mk-1")
            transport_result = await mcp_transport.brain_sync_check(match_key="mk-1")
        self.assertEqual(transport_result, gateway_result)

    async def test_upsert_bulk_parity_between_stdio_and_http(self) -> None:
        payload = [{"match_key": "mk-1", "content": "payload"}]
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = await gateway.brain_upsert_bulk(payload)
            transport_result = await mcp_transport.brain_upsert_bulk(payload)
        self.assertEqual(transport_result, gateway_result)

    async def test_maintain_parity_between_stdio_and_http(self) -> None:
        with (
            patch("_gateway_src.main._client", return_value=_GatewayClient()),
            patch.object(mcp_transport, "_client", return_value=_TransportClient()),
        ):
            gateway_result = await gateway.brain_maintain(dry_run=True)
            transport_result = await mcp_transport.brain_maintain(dry_run=True)
        self.assertEqual(transport_result, gateway_result)


if __name__ == "__main__":
    unittest.main()
