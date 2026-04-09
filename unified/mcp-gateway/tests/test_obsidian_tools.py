import unittest
from unittest.mock import AsyncMock, Mock, patch

from helpers import load_gateway_main


class _MockResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _MockRequestClient:
    def __init__(self, response: _MockResponse) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, **kwargs):
        return self._response


class GatewayObsidianToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        gateway = load_gateway_main()
        client = getattr(gateway, "_http_client", None)
        if client is not None:
            await client.aclose()
            gateway._http_client = None

    async def _assert_opt_in_required(self, func, *args, **kwargs) -> None:
        gateway = load_gateway_main()
        method = getattr(gateway, func)

        with patch.dict("os.environ", {}, clear=False):
            with self.assertRaises(ValueError) as ctx:
                await method(*args, **kwargs)

        self.assertIn("ENABLE_LOCAL_OBSIDIAN_TOOLS=1", str(ctx.exception))

    async def test_brain_obsidian_vaults_requires_explicit_opt_in(self) -> None:
        await self._assert_opt_in_required("brain_obsidian_vaults")

    async def test_disabled_reason_is_consistent_between_capabilities_and_runtime_guard(
        self,
    ) -> None:
        gateway = load_gateway_main()
        with patch.dict("os.environ", {}, clear=False):
            caps = await gateway.brain_capabilities()
            with self.assertRaises(ValueError) as ctx:
                await gateway.brain_obsidian_vaults()

        self.assertEqual(caps["obsidian"]["reason"], str(ctx.exception))

    async def test_all_local_obsidian_tools_require_explicit_opt_in(self) -> None:
        await self._assert_opt_in_required(
            "brain_obsidian_write_note",
            vault="Documents",
            path="Inbox/Test.md",
            content="Body",
        )
        await self._assert_opt_in_required(
            "brain_obsidian_export",
            vault="Documents",
        )
        await self._assert_opt_in_required(
            "brain_obsidian_collection",
            query="architecture",
            collection_name="Architecture",
        )
        await self._assert_opt_in_required(
            "brain_obsidian_bidirectional_sync",
        )
        await self._assert_opt_in_required(
            "brain_obsidian_sync_status",
        )
        await self._assert_opt_in_required(
            "brain_obsidian_update_note",
            vault="Documents",
            path="Inbox/Test.md",
        )

    async def test_brain_obsidian_vaults_uses_local_adapter(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False), patch("_gateway_src.main.ObsidianCliAdapter") as adapter_cls:
            adapter = AsyncMock()
            adapter.list_vaults.return_value = ["Documents"]
            adapter_cls.return_value = adapter

            result = await gateway.brain_obsidian_vaults()

        adapter.list_vaults.assert_awaited_once_with()
        self.assertEqual(result, ["Documents"])

    async def test_brain_obsidian_read_note_uses_local_adapter(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False), patch("_gateway_src.main.ObsidianCliAdapter") as adapter_cls:
            adapter = AsyncMock()
            adapter.read_note.return_value = Mock(
                vault="Documents",
                path="Inbox/Test.md",
                title="Test",
                content="Body",
                frontmatter={"domain": "build"},
                tags=["openbrain"],
                file_hash="abc",
            )
            adapter_cls.return_value = adapter

            result = await gateway.brain_obsidian_read_note(path="Inbox/Test.md", vault="Documents")

        adapter.read_note.assert_awaited_once_with("Documents", "Inbox/Test.md")
        self.assertEqual(result["path"], "Inbox/Test.md")

    async def test_brain_obsidian_sync_reads_local_notes_and_writes_v1(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"summary": {"received": 1}, "results": [{"status": "created"}]}

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False), patch("_gateway_src.main.ObsidianCliAdapter") as adapter_cls, patch("_gateway_src.main._client") as mock_client:
            adapter = AsyncMock()
            adapter.list_files.return_value = ["Inbox/Test.md"]
            adapter.read_note.return_value = Mock(
                vault="Documents",
                path="Inbox/Test.md",
                title="Test",
                content="Body",
                frontmatter={},
                tags=["openbrain"],
                file_hash="abc",
            )
            adapter_cls.return_value = adapter

            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_sync(vault="Documents", folder="Inbox", limit=1)

        adapter.list_files.assert_awaited_once_with("Documents", folder="Inbox", limit=1)
        adapter.read_note.assert_awaited_once_with("Documents", "Inbox/Test.md")
        client.post.assert_awaited_once()
        self.assertEqual(result["scanned"], 1)

    async def test_brain_obsidian_write_note_calls_backend_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"path": "Inbox/Test.md", "created": True}

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._client") as mock_client,
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_write_note(
                vault="Documents",
                path="Inbox/Test.md",
                content="Body",
                title="Test",
                tags=["openbrain"],
            )

        client.post.assert_awaited_once_with(
            "/api/v1/obsidian/write-note",
            json={
                "vault": "Documents",
                "path": "Inbox/Test.md",
                "content": "# Test\n\nBody",
                "frontmatter": {"tags": ["openbrain"], "title": "Test"},
                "overwrite": False,
            },
        )
        self.assertEqual(result["created"], True)

    async def test_brain_obsidian_export_calls_backend_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"exported_count": 1}

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._client") as mock_client,
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_export(
                vault="Documents",
                folder="Exports",
                query="architecture",
                domain="build",
                max_items=10,
            )

        client.post.assert_awaited_once_with(
            "/api/v1/obsidian/export",
            json={
                "vault": "Documents",
                "folder": "Exports",
                "memory_ids": None,
                "query": "architecture",
                "domain": "build",
                "max_items": 10,
            },
        )
        self.assertEqual(result["exported_count"], 1)

    async def test_brain_obsidian_collection_calls_backend_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"collection_name": "Architecture"}

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._client") as mock_client,
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_collection(
                query="architecture",
                collection_name="Architecture",
                max_items=10,
            )

        client.post.assert_awaited_once_with(
            "/api/v1/obsidian/collection",
            json={
                "query": "architecture",
                "collection_name": "Architecture",
                "vault": "Documents",
                "folder": "Collections",
                "domain": None,
                "max_items": 10,
                "group_by": None,
            },
        )
        self.assertEqual(result["collection_name"], "Architecture")

    async def test_brain_obsidian_bidirectional_sync_calls_backend_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"changes_detected": 3}

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._client") as mock_client,
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_bidirectional_sync(
                vault="Memory",
                strategy="manual_review",
                dry_run=True,
            )

        client.post.assert_awaited_once_with(
            "/api/v1/obsidian/bidirectional-sync",
            json={
                "vault": "Memory",
                "strategy": "manual_review",
                "dry_run": True,
            },
        )
        self.assertEqual(result["changes_detected"], 3)

    async def test_brain_obsidian_sync_status_calls_backend_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"tracked_files": 4}

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._client") as mock_client,
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_sync_status()

        client.get.assert_awaited_once_with("/api/v1/obsidian/sync-status")
        self.assertEqual(result["tracked_files"], 4)

    async def test_brain_obsidian_update_note_calls_backend_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"updated": True}

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._client") as mock_client,
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_update_note(
                vault="Documents",
                path="Inbox/Test.md",
                content="More",
                append=True,
                tags=["openbrain"],
            )

        client.post.assert_awaited_once_with(
            "/api/v1/obsidian/update-note",
            json={
                "vault": "Documents",
                "path": "Inbox/Test.md",
                "content": "More",
                "append": True,
                "tags": ["openbrain"],
            },
        )
        self.assertEqual(result["updated"], True)

    async def test_brain_capabilities_hides_obsidian_tools_when_disabled(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {}, clear=False):
            result = await gateway.brain_capabilities()

        self.assertEqual(result["obsidian"]["mode"], "local")
        self.assertEqual(result["obsidian"]["status"], "disabled")
        self.assertEqual(result["obsidian"]["tools"], [])
        self.assertEqual(result["health"]["components"]["obsidian"], "disabled")
        self.assertEqual(result["obsidian"]["reason"], result["obsidian_local"]["reason"])
        self.assertIn("ENABLE_LOCAL_OBSIDIAN_TOOLS=1", result["obsidian"]["reason"])
        self.assertIn("trusted local stdio gateway", result["obsidian"]["reason"])
        self.assertNotIn("obsidian_vaults", result["tier_2_advanced"]["tools"])
        self.assertEqual(result["obsidian_local"]["tools"], [])

    async def test_brain_capabilities_includes_obsidian_tools_when_enabled(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False):
            result = await gateway.brain_capabilities()

        self.assertEqual(result["obsidian"]["mode"], "local")
        self.assertEqual(result["obsidian"]["status"], "enabled")
        self.assertEqual(result["obsidian"]["tools"], result["obsidian_local"]["tools"])
        self.assertEqual(result["health"]["components"]["obsidian"], "enabled")
        self.assertIsNone(result["obsidian"]["reason"])
        self.assertEqual(
            result["obsidian_local"]["tools"],
            [
                "obsidian_vaults",
                "obsidian_read_note",
                "obsidian_sync",
                "obsidian_write_note",
                "obsidian_export",
                "obsidian_collection",
                "obsidian_bidirectional_sync",
                "obsidian_sync_status",
                "obsidian_update_note",
            ],
        )
        for tool in result["obsidian_local"]["tools"]:
            self.assertIn(tool, result["tier_2_advanced"]["tools"])

    async def test_brain_capabilities_keep_obsidian_disabled_when_tools_not_registered(
        self,
    ) -> None:
        gateway = load_gateway_main()

        with (
            patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False),
            patch("_gateway_src.main._local_obsidian_tools_registered", return_value=False),
            patch(
                "_gateway_src.main._get_backend_status",
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
            result = await gateway.brain_capabilities()

        self.assertEqual(result["obsidian"]["status"], "disabled")
        self.assertEqual(result["obsidian"]["tools"], [])
        self.assertEqual(result["obsidian_local"]["status"], "disabled")
        self.assertEqual(result["obsidian_local"]["tools"], [])

    async def test_brain_capabilities_marks_reachable_backend_as_degraded_when_readyz_is_503(self) -> None:
        gateway = load_gateway_main()

        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.get.return_value = _MockResponse(
            503,
            {"status": "degraded", "db": "degraded", "vector_store": "ok"},
        )

        with patch("_gateway_src.main.httpx.AsyncClient", return_value=client):
            result = await gateway.brain_capabilities()

        self.assertEqual(result["backend"]["status"], "degraded")
        self.assertEqual(result["backend"]["api"], "reachable")
        self.assertEqual(result["backend"]["db"], "degraded")
        self.assertEqual(result["backend"]["probe"], "readyz")
        self.assertEqual(result["health"]["overall"], "degraded")
        self.assertEqual(result["health"]["components"]["db"], "degraded")

    async def test_brain_capabilities_falls_back_to_healthz_before_reporting_outage(self) -> None:
        gateway = load_gateway_main()

        readyz_client = AsyncMock()
        readyz_client.__aenter__.return_value = readyz_client
        readyz_client.__aexit__.return_value = False
        readyz_client.get.side_effect = RuntimeError("connection refused")

        healthz_client = AsyncMock()
        healthz_client.__aenter__.return_value = healthz_client
        healthz_client.__aexit__.return_value = False
        healthz_client.get.return_value = _MockResponse(200, {"status": "ok"})

        with patch(
            "_gateway_src.main.httpx.AsyncClient",
            side_effect=[readyz_client, healthz_client],
        ):
            result = await gateway.brain_capabilities()

        self.assertEqual(result["backend"]["status"], "degraded")
        self.assertEqual(result["backend"]["api"], "reachable")
        self.assertEqual(result["backend"]["probe"], "healthz_fallback")
        self.assertIn("/readyz probe failed", result["backend"]["reason"])
        self.assertEqual(result["health"]["overall"], "degraded")

    async def test_brain_capabilities_uses_api_health_fallback_when_probes_fail(self) -> None:
        gateway = load_gateway_main()

        readyz_client = AsyncMock()
        readyz_client.__aenter__.return_value = readyz_client
        readyz_client.__aexit__.return_value = False
        readyz_client.get.side_effect = RuntimeError("readyz down")

        healthz_client = AsyncMock()
        healthz_client.__aenter__.return_value = healthz_client
        healthz_client.__aexit__.return_value = False
        healthz_client.get.side_effect = RuntimeError("healthz down")

        api_client = _MockRequestClient(_MockResponse(200, {"status": "ok"}))

        with (
            patch(
                "_gateway_src.main.httpx.AsyncClient",
                side_effect=[readyz_client, healthz_client],
            ),
            patch("_gateway_src.main._client", return_value=api_client),
        ):
            result = await gateway.brain_capabilities()

        self.assertEqual(result["backend"]["status"], "degraded")
        self.assertEqual(result["backend"]["api"], "reachable")
        self.assertEqual(result["backend"]["probe"], "api_health_fallback")
        self.assertIn("/readyz probe failed", result["backend"]["reason"])
        self.assertIn("/healthz probe failed", result["backend"]["reason"])
        self.assertEqual(result["health"]["overall"], "degraded")


if __name__ == "__main__":
    unittest.main()
