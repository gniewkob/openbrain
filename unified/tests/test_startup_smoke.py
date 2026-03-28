import importlib
import unittest


def _import_app_module(name: str):
    for candidate in (f"unified.{name}", name):
        try:
            return importlib.import_module(candidate)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(name)


class StartupSmokeTests(unittest.TestCase):
    def test_main_module_imports_and_builds_fastapi_app(self) -> None:
        main = _import_app_module("src.main")

        self.assertEqual(main.app.title, "OpenBrain Unified Memory Service")

    def test_combined_module_imports(self) -> None:
        combined = _import_app_module("src.combined")

        self.assertTrue(callable(combined.app))


class CombinedRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_is_forwarded_to_rest_app(self) -> None:
        combined = _import_app_module("src.combined")
        calls: list[str] = []

        async def fake_rest_app(scope, receive, send):
            calls.append(scope["path"])
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        original_rest_app = combined.rest_app
        combined.rest_app = fake_rest_app
        messages: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        try:
            await combined.app(
                {"type": "http", "path": "/health", "method": "GET", "headers": []},
                receive,
                send,
            )
        finally:
            combined.rest_app = original_rest_app

        self.assertEqual(calls, ["/health"])
        self.assertEqual(messages[0]["status"], 204)

    async def test_probe_endpoints_are_forwarded_to_rest_app(self) -> None:
        combined = _import_app_module("src.combined")
        calls: list[str] = []

        async def fake_rest_app(scope, receive, send):
            calls.append(scope["path"])
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        original_rest_app = combined.rest_app
        combined.rest_app = fake_rest_app

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        try:
            for path in ("/healthz", "/readyz"):
                messages: list[dict] = []

                async def send(message):
                    messages.append(message)

                await combined.app(
                    {"type": "http", "path": path, "method": "GET", "headers": []},
                    receive,
                    send,
                )
                self.assertEqual(messages[0]["status"], 204)
        finally:
            combined.rest_app = original_rest_app

        self.assertEqual(calls, ["/healthz", "/readyz"])


if __name__ == "__main__":
    unittest.main()
