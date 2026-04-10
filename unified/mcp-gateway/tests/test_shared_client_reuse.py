import unittest
from unittest.mock import patch

from helpers import load_gateway_main


class GatewaySharedClientReuseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        gateway = load_gateway_main()
        client = getattr(gateway, "_http_client", None)
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass
        gateway._http_client = None
        gateway._http_client_config_key = None

    async def test_client_reuses_shared_async_client_instance(self) -> None:
        gateway = load_gateway_main()
        created_clients: list[object] = []

        class _CtorClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                created_clients.append(self)

            async def aclose(self) -> None:
                return None

        gateway._http_client = None
        gateway._http_client_config_key = None
        with patch.object(gateway.httpx, "AsyncClient", _CtorClient):
            async with gateway._client() as c1:
                self.assertIsNotNone(c1)
            async with gateway._client() as c2:
                self.assertIs(c1, c2)

        self.assertEqual(len(created_clients), 1)

    async def test_client_recreates_when_runtime_config_changes(self) -> None:
        gateway = load_gateway_main()
        created_clients: list[object] = []

        class _CtorClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                self.closed = False
                created_clients.append(self)

            async def aclose(self) -> None:
                self.closed = True

        gateway._http_client = None
        gateway._http_client_config_key = None
        with patch.object(gateway.httpx, "AsyncClient", _CtorClient):
            with patch.object(gateway, "BRAIN_URL", "http://127.0.0.1:7010"):
                async with gateway._client() as c1:
                    self.assertEqual(c1.kwargs["base_url"], "http://127.0.0.1:7010")

            with (
                patch.object(gateway, "BRAIN_URL", "http://127.0.0.1:7020"),
                patch.object(gateway._gateway_logger, "info") as log_info,
            ):
                async with gateway._client() as c2:
                    self.assertEqual(c2.kwargs["base_url"], "http://127.0.0.1:7020")
                log_info.assert_called_once()

        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertIsNot(created_clients[0], created_clients[1])

    async def test_client_recreate_survives_close_error(self) -> None:
        gateway = load_gateway_main()
        created_clients: list[object] = []

        class _CtorClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                created_clients.append(self)

            async def aclose(self) -> None:
                return None

        class _FailingCloseClient(_CtorClient):
            async def aclose(self) -> None:
                raise RuntimeError("close failed")

        gateway._http_client = None
        gateway._http_client_config_key = None
        with patch.object(gateway.httpx, "AsyncClient", _CtorClient):
            with patch.object(gateway, "BRAIN_URL", "http://127.0.0.1:7010"):
                async with gateway._client():
                    pass

        gateway._http_client = _FailingCloseClient(base_url="http://127.0.0.1:7010")
        gateway._http_client_config_key = (
            "http://127.0.0.1:7010",
            gateway.BACKEND_TIMEOUT,
            gateway.INTERNAL_API_KEY,
        )

        with (
            patch.object(gateway.httpx, "AsyncClient", _CtorClient),
            patch.object(gateway, "BRAIN_URL", "http://127.0.0.1:7020"),
            patch.object(gateway._gateway_logger, "warning") as log_warning,
        ):
            async with gateway._client() as c2:
                self.assertEqual(c2.kwargs["base_url"], "http://127.0.0.1:7020")
            log_warning.assert_called_once()

