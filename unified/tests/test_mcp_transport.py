from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

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


class _ProbeClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        result = self._responses[path]
        if isinstance(result, Exception):
            raise result
        return result


class _ErrorClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, **kwargs):
        raise httpx.ConnectError("connect timeout", request=httpx.Request(method, path))


class McpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_env_bool_uses_default_when_env_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(mcp_transport._env_bool("ENABLE_HTTP_OBSIDIAN_TOOLS"))
            self.assertTrue(
                mcp_transport._env_bool("ENABLE_HTTP_OBSIDIAN_TOOLS", default=True)
            )

    async def test_env_bool_accepts_true_like_values(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on"):
            with patch.dict(
                os.environ, {"ENABLE_HTTP_OBSIDIAN_TOOLS": value}, clear=True
            ):
                self.assertTrue(mcp_transport._env_bool("ENABLE_HTTP_OBSIDIAN_TOOLS"))

    async def test_client_reuses_shared_async_client_instance(self) -> None:
        created_clients: list[object] = []

        class _CtorClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                created_clients.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method: str, path: str, **kwargs):
                return _FakeResponse(200, payload={"status": "ok"})

        mcp_transport._http_client = None
        mcp_transport._http_client_config_key = None
        with patch.object(mcp_transport.httpx, "AsyncClient", _CtorClient):
            async with mcp_transport._client() as c1:
                self.assertIsNotNone(c1)
            async with mcp_transport._client() as c2:
                self.assertIs(c1, c2)

        self.assertEqual(len(created_clients), 1)
        mcp_transport._http_client = None
        mcp_transport._http_client_config_key = None

    async def test_client_recreates_when_runtime_config_changes(self) -> None:
        created_clients: list[object] = []

        class _CtorClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                self.closed = False
                created_clients.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method: str, path: str, **kwargs):
                return _FakeResponse(200, payload={"status": "ok"})

            async def aclose(self) -> None:
                self.closed = True

        mcp_transport._http_client = None
        mcp_transport._http_client_config_key = None
        with patch.object(mcp_transport.httpx, "AsyncClient", _CtorClient):
            with patch.object(mcp_transport, "BRAIN_URL", "http://127.0.0.1:7010"):
                async with mcp_transport._client() as c1:
                    self.assertEqual(c1.kwargs["base_url"], "http://127.0.0.1:7010")

            with (
                patch.object(mcp_transport, "BRAIN_URL", "http://127.0.0.1:7020"),
                patch.object(mcp_transport.log, "info") as log_info,
            ):
                async with mcp_transport._client() as c2:
                    self.assertEqual(c2.kwargs["base_url"], "http://127.0.0.1:7020")
                log_info.assert_any_call(
                    "mcp_client_refreshed_due_to_config_drift",
                    old_base_url="http://127.0.0.1:7010",
                    new_base_url="http://127.0.0.1:7020",
                )

        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertIsNot(created_clients[0], created_clients[1])
        mcp_transport._http_client = None
        mcp_transport._http_client_config_key = None

    async def test_client_recreate_survives_close_error(self) -> None:
        created_clients: list[object] = []

        class _CtorClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                created_clients.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method: str, path: str, **kwargs):
                return _FakeResponse(200, payload={"status": "ok"})

            async def aclose(self) -> None:
                return None

        class _FailingCloseClient(_CtorClient):
            async def aclose(self) -> None:
                raise RuntimeError("close failed")

        mcp_transport._http_client = None
        mcp_transport._http_client_config_key = None
        with patch.object(mcp_transport.httpx, "AsyncClient", _CtorClient):
            with patch.object(mcp_transport, "BRAIN_URL", "http://127.0.0.1:7010"):
                async with mcp_transport._client():
                    pass

        # Inject failing previous client + old config key.
        mcp_transport._http_client = _FailingCloseClient(
            base_url="http://127.0.0.1:7010"
        )
        mcp_transport._http_client_config_key = (
            "http://127.0.0.1:7010",
            mcp_transport.BACKEND_TIMEOUT,
            mcp_transport.INTERNAL_API_KEY,
        )
        with (
            patch.object(mcp_transport.httpx, "AsyncClient", _CtorClient),
            patch.object(mcp_transport, "BRAIN_URL", "http://127.0.0.1:7020"),
            patch.object(mcp_transport.log, "warning") as log_warning,
        ):
            async with mcp_transport._client() as c2:
                self.assertEqual(c2.kwargs["base_url"], "http://127.0.0.1:7020")
            log_warning.assert_called_once()

        mcp_transport._http_client = None
        mcp_transport._http_client_config_key = None

    async def test_brain_capabilities_hide_http_obsidian_tools_when_disabled(
        self,
    ) -> None:
        with (
            patch.object(mcp_transport, "ENABLE_HTTP_OBSIDIAN_TOOLS", False),
            patch.object(
                mcp_transport,
                "_get_backend_status",
                AsyncMock(
                    return_value={
                        "status": "ok",
                        "api": "reachable",
                        "db": "ok",
                        "vector_store": "ok",
                        "probe": "readyz",
                    }
                ),
            ),
        ):
            result = await mcp_transport.brain_capabilities()

        self.assertEqual(result["backend"]["status"], "ok")
        self.assertEqual(result["health"]["overall"], "healthy")
        self.assertEqual(result["health"]["components"]["api"], "healthy")
        self.assertEqual(result["health"]["components"]["obsidian"], "disabled")
        self.assertEqual(result["obsidian"]["mode"], "http")
        self.assertEqual(result["obsidian"]["status"], "disabled")
        self.assertEqual(result["obsidian"]["tools"], [])
        self.assertEqual(
            result["obsidian"]["reason"], result["obsidian_http"]["reason"]
        )
        self.assertEqual(result["obsidian_http"]["status"], "disabled")
        self.assertEqual(result["obsidian_http"]["tools"], [])
        self.assertIn("disabled", result["obsidian_http"]["reason"])
        self.assertNotIn("obsidian_vaults", result["tier_2_advanced"]["tools"])

    async def test_brain_capabilities_include_http_obsidian_tools_when_enabled(
        self,
    ) -> None:
        with (
            patch.object(mcp_transport, "ENABLE_HTTP_OBSIDIAN_TOOLS", True),
            patch.object(
                mcp_transport,
                "_get_backend_status",
                AsyncMock(
                    return_value={
                        "status": "ok",
                        "api": "reachable",
                        "db": "ok",
                        "vector_store": "ok",
                        "probe": "readyz",
                    }
                ),
            ),
        ):
            result = await mcp_transport.brain_capabilities()

        self.assertEqual(result["backend"]["status"], "ok")
        self.assertEqual(result["health"]["overall"], "healthy")
        self.assertEqual(result["health"]["components"]["api"], "healthy")
        self.assertEqual(result["health"]["components"]["obsidian"], "enabled")
        self.assertEqual(result["obsidian"]["mode"], "http")
        self.assertEqual(result["obsidian"]["status"], "enabled")
        self.assertEqual(result["obsidian"]["tools"], result["obsidian_http"]["tools"])
        self.assertIsNone(result["obsidian"]["reason"])
        self.assertEqual(result["obsidian_http"]["status"], "enabled")
        self.assertEqual(
            result["obsidian_http"]["tools"],
            ["obsidian_vaults", "obsidian_read_note", "obsidian_sync"],
        )
        self.assertIsNone(result["obsidian_http"]["reason"])
        for tool in result["obsidian_http"]["tools"]:
            self.assertIn(tool, result["tier_2_advanced"]["tools"])

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

    async def test_safe_req_normalizes_request_errors(self) -> None:
        with patch.object(mcp_transport, "_client", return_value=_ErrorClient()):
            with self.assertRaisesRegex(ValueError, "Backend request failed"):
                await mcp_transport._safe_req("GET", "/api/memories/missing")

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

    async def test_init_config_parses_public_base_hostname_for_transport_security(
        self,
    ) -> None:
        old_brain_url = mcp_transport.BRAIN_URL
        old_backend_timeout = mcp_transport.BACKEND_TIMEOUT
        old_health_probe_timeout = mcp_transport.HEALTH_PROBE_TIMEOUT
        old_source_system = mcp_transport.MCP_SOURCE_SYSTEM
        old_streamable_path = mcp_transport.STREAMABLE_HTTP_PATH
        old_ngrok_host = mcp_transport._ngrok_host

        fake_cfg = SimpleNamespace(
            mcp=SimpleNamespace(
                brain_url="http://127.0.0.1:7010",
                backend_timeout=12.5,
                health_probe_timeout=2.0,
                source_system="gateway",
                streamable_http_path="/events",
            ),
            auth=SimpleNamespace(
                internal_api_key="k" * 40,
                public_base_url="https://abc123.ngrok-free.app/consent",
            ),
        )

        with patch("src.config.get_config", return_value=fake_cfg):
            mcp_transport._init_config()

        self.assertEqual(mcp_transport.BRAIN_URL, "http://127.0.0.1:7010")
        self.assertEqual(mcp_transport.BACKEND_TIMEOUT, 12.5)
        self.assertEqual(mcp_transport.HEALTH_PROBE_TIMEOUT, 2.0)
        self.assertEqual(mcp_transport.MCP_SOURCE_SYSTEM, "gateway")
        self.assertEqual(mcp_transport.STREAMABLE_HTTP_PATH, "/events")
        self.assertEqual(mcp_transport._ngrok_host, "abc123.ngrok-free.app")

        transport_security = mcp_transport._build_transport_security(
            mcp_transport._ngrok_host
        )
        self.assertIn("abc123.ngrok-free.app", transport_security.allowed_hosts)
        self.assertIn("abc123.ngrok-free.app:*", transport_security.allowed_hosts)
        self.assertIn(
            "https://abc123.ngrok-free.app", transport_security.allowed_origins
        )

        mcp_transport.BRAIN_URL = old_brain_url
        mcp_transport.BACKEND_TIMEOUT = old_backend_timeout
        mcp_transport.HEALTH_PROBE_TIMEOUT = old_health_probe_timeout
        mcp_transport.MCP_SOURCE_SYSTEM = old_source_system
        mcp_transport.STREAMABLE_HTTP_PATH = old_streamable_path
        mcp_transport._ngrok_host = old_ngrok_host

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

    async def test_brain_search_top_k_zero_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_k must be 1"):
            await mcp_transport.brain_search(query="x", top_k=0)

    async def test_brain_search_top_k_over_limit_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_k must be 1"):
            await mcp_transport.brain_search(
                query="x", top_k=mcp_transport.MAX_SEARCH_TOP_K + 1
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
                "PATCH",
                "/api/v1/memory/mem-1",
                {
                    "json": {
                        "content": "after",
                        "updated_by": "agent",
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

    async def test_brain_update_uses_canonical_updated_by_placeholder(self) -> None:
        response = _FakeResponse(200, payload={"id": "mem-1"})
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            await mcp_transport.brain_update(
                "mem-1",
                content="after",
                updated_by="gateway-user",
            )
        self.assertEqual(
            fake_client.last_request[2]["json"]["updated_by"],
            "agent",
        )

    async def test_brain_update_empty_updated_by_falls_back_to_agent(self) -> None:
        response = _FakeResponse(200, payload={"id": "mem-1"})
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            await mcp_transport.brain_update(
                "mem-1",
                content="after",
                updated_by="   ",
            )
        self.assertEqual(
            fake_client.last_request[2]["json"]["updated_by"],
            "agent",
        )

    async def test_brain_delete_returns_gateway_shape(self) -> None:
        response = _FakeResponse(204, payload=None)
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            result = await mcp_transport.brain_delete("mem-1")
        self.assertEqual(result, {"deleted": True, "id": "mem-1"})
        self.assertEqual(fake_client.last_request[0], "DELETE")
        self.assertEqual(fake_client.last_request[1], "/api/v1/memory/mem-1")

    async def test_brain_export_uses_v1_export_endpoint(self) -> None:
        response = _FakeResponse(200, payload=[{"id": "mem-1"}])
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            result = await mcp_transport.brain_export(["mem-1"])
        self.assertEqual(result, [{"id": "mem-1"}])
        self.assertEqual(
            fake_client.last_request,
            ("POST", "/api/v1/memory/export", {"json": {"ids": ["mem-1"]}}),
        )

    async def test_brain_list_uses_legacy_list_shape(self) -> None:
        response = _FakeResponse(
            200,
            payload=[
                {
                    "record": {
                        "id": "mem-1",
                        "domain": "build",
                        "entity_type": "Note",
                        "content": "x",
                        "owner": "",
                        "status": "active",
                        "version": 1,
                        "sensitivity": "internal",
                        "tags": [],
                        "relations": {},
                        "custom_fields": {},
                        "created_by": "internal",
                        "updated_by": "internal",
                        "created_at": "2026-03-27T00:00:00Z",
                        "updated_at": "2026-03-27T00:00:00Z",
                    },
                    "score": 1.0,
                }
            ],
        )
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            result = await mcp_transport.brain_list(domain="build", limit=5)
        self.assertEqual(result[0]["id"], "mem-1")
        self.assertEqual(result[0]["domain"], "build")
        self.assertEqual(
            fake_client.last_request,
            (
                "POST",
                "/api/v1/memory/find",
                {
                    "json": {
                        "query": None,
                        "filters": {"domain": "build"},
                        "limit": 5,
                        "sort": "updated_at_desc",
                    }
                },
            ),
        )

    async def test_brain_list_limit_zero_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be 1"):
            await mcp_transport.brain_list(limit=0)

    async def test_brain_list_limit_over_max_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be 1"):
            await mcp_transport.brain_list(limit=mcp_transport.MAX_LIST_LIMIT + 1)

    async def test_brain_obsidian_sync_limit_bounds_when_tool_enabled(self) -> None:
        if not hasattr(mcp_transport, "brain_obsidian_sync"):
            self.skipTest("HTTP Obsidian tools disabled in this runtime profile")
        with self.assertRaisesRegex(ValueError, "limit must be 1"):
            await mcp_transport.brain_obsidian_sync(limit=0)

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
                "/api/v1/memory/sync-check",
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
                "/api/v1/memory/bulk-upsert",
                {"json": [{"match_key": "mk-1", "content": "x"}]},
            ),
        )

    async def test_brain_maintain_uses_v1_endpoint(self) -> None:
        response = _FakeResponse(200, payload={"dry_run": True, "actions": []})
        fake_client = _FakeClient(response)
        with patch.object(mcp_transport, "_client", return_value=fake_client):
            result = await mcp_transport.brain_maintain(dry_run=True)
        self.assertEqual(result, {"dry_run": True, "actions": []})
        self.assertEqual(
            fake_client.last_request,
            ("POST", "/api/v1/memory/maintain", {"json": {"dry_run": True}}),
        )

    async def test_guard_re_raises_as_tool_error(self) -> None:
        @mcp_transport.mcp_tool_guard
        async def broken():
            raise RuntimeError("boom")

        with self.assertRaisesRegex(ValueError, "Tool execution failed: boom"):
            await broken()

    async def test_get_backend_status_prefers_readyz(self) -> None:
        readyz = _FakeResponse(
            200,
            payload={"status": "ok", "db": "ok", "vector_store": "ok"},
        )
        with patch.object(
            mcp_transport,
            "_client",
            return_value=_ProbeClient({"/readyz": readyz}),
        ):
            result = await mcp_transport._get_backend_status()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["probe"], "readyz")
        self.assertEqual(result["api"], "reachable")
        self.assertEqual(result["db"], "ok")
        self.assertEqual(result["vector_store"], "ok")

    async def test_get_backend_status_falls_back_to_healthz(self) -> None:
        with patch.object(
            mcp_transport,
            "_client",
            side_effect=[
                _ProbeClient({"/readyz": RuntimeError("timeout")}),
                _ProbeClient(
                    {"/healthz": _FakeResponse(200, payload={"status": "ok"})}
                ),
            ],
        ):
            result = await mcp_transport._get_backend_status()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["probe"], "healthz_fallback")
        self.assertEqual(result["api"], "reachable")
        self.assertIn("/readyz probe failed", result["reason"])

    async def test_get_backend_status_reports_unavailable_when_both_probes_fail(
        self,
    ) -> None:
        with patch.object(
            mcp_transport,
            "_client",
            side_effect=[
                _ProbeClient({"/readyz": RuntimeError("readyz down")}),
                _ProbeClient({"/healthz": RuntimeError("healthz down")}),
                _ProbeClient({"/api/v1/health": RuntimeError("api health down")}),
            ],
        ):
            result = await mcp_transport._get_backend_status()

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["api"], "unreachable")
        self.assertEqual(result["probe"], "api_health_fallback")
        self.assertIn("readyz down", result["reason"])
        self.assertIn("healthz down", result["reason"])
        self.assertIn("api health down", result["reason"])

    async def test_get_backend_status_uses_api_health_when_readyz_and_healthz_fail(
        self,
    ) -> None:
        with patch.object(
            mcp_transport,
            "_client",
            side_effect=[
                _ProbeClient({"/readyz": RuntimeError("readyz timeout")}),
                _ProbeClient({"/healthz": RuntimeError("healthz timeout")}),
                _ProbeClient(
                    {"/api/v1/health": _FakeResponse(200, payload={"status": "ok"})}
                ),
            ],
        ):
            result = await mcp_transport._get_backend_status()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["api"], "reachable")
        self.assertEqual(result["probe"], "api_health_fallback")
        self.assertIn("/readyz probe failed", result["reason"])
        self.assertIn("/healthz probe failed", result["reason"])


if __name__ == "__main__":
    unittest.main()
