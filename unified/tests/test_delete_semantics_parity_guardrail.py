from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_delete_semantics_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_delete_semantics_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_delete_semantics_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_delete_semantics_guardrail_passes_for_current_sources() -> None:
    module = _load_delete_semantics_module()
    assert module.main() == 0


def test_gateway_semantics_detector_finds_missing_allow_statuses() -> None:
    module = _load_delete_semantics_module()
    src = """
async def brain_delete(memory_id: str):
    async with _client() as c:
        r = await _request_or_raise(c, "DELETE", "/api/v1/memory/x")
"""
    errors = module._check_gateway_delete_semantics(src)
    assert any("allow 403 and 404 passthrough" in err for err in errors)


def test_transport_semantics_detector_finds_missing_forbidden_mapping() -> None:
    module = _load_delete_semantics_module()
    src = """
async def brain_delete(memory_id: str):
    if response.status_code == 404:
        raise ValueError(f"Memory not found: {memory_id}")
"""
    errors = module._check_transport_delete_semantics(src)
    assert any("map 403 explicitly" in err for err in errors)


def test_gateway_semantics_detector_requires_backend_error_mapping() -> None:
    module = _load_delete_semantics_module()
    src = """
async def brain_delete(memory_id: str):
    async with _client() as c:
        r = await _request_or_raise(c, "DELETE", "/api/v1/memory/x", allow_statuses={403, 404})
    if r.status_code == 404:
        raise ValueError(f"Memory not found: {memory_id}")
    if r.status_code == 403:
        raise ValueError("Cannot delete corporate memories. Use deprecation instead.")
"""
    errors = module._check_gateway_delete_semantics(src)
    assert any("backend_error_message mapping" in err for err in errors)
