from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_shared_http_client_reuse_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_shared_http_client_reuse.py"
    spec = importlib.util.spec_from_file_location(
        "check_shared_http_client_reuse", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shared_http_client_reuse_guardrail_passes_for_current_sources() -> None:
    module = _load_shared_http_client_reuse_module()
    assert module.main() == 0


def test_shared_http_client_reuse_guardrail_detects_missing_client_factory() -> None:
    module = _load_shared_http_client_reuse_module()
    src = """
_http_client: object | None = None

class _SharedClient:
    async def __aenter__(self):
        global _http_client
        if _http_client is None:
            _http_client = httpx.AsyncClient(base_url="http://x")
        return _http_client

def _client():
    return object()
"""
    errors = module._check_source(src, "x")
    assert any("_client() must return _SharedClient()" in err for err in errors)


def test_shared_http_client_reuse_guardrail_detects_missing_none_guard() -> None:
    module = _load_shared_http_client_reuse_module()
    src = """
_http_client: object | None = None

class _SharedClient:
    async def __aenter__(self):
        return httpx.AsyncClient(base_url="http://x")

def _client():
    return _SharedClient()
"""
    errors = module._check_source(src, "x")
    assert any("must guard _http_client is None" in err for err in errors)
