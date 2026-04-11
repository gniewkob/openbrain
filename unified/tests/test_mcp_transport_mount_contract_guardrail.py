from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_guardrail_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_mcp_transport_mount_contract.py"
    spec = importlib.util.spec_from_file_location(
        "check_mcp_transport_mount_contract", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mcp_transport_mount_contract_guardrail_passes_for_current_sources() -> None:
    module = _load_guardrail_module()
    assert module.main() == 0


def test_mount_contract_detects_missing_transport_import() -> None:
    module = _load_guardrail_module()
    src = """
from .main import app as rest_app

mcp_app = mcp_transport.mcp.streamable_http_app()
"""
    errors = module._check_mount_contract(src)
    assert any("must import mcp_transport" in err for err in errors)


def test_mount_contract_detects_non_transport_mcp_app_assignment() -> None:
    module = _load_guardrail_module()
    src = """
from . import mcp_transport

mcp_app = mcp.streamable_http_app()
"""
    errors = module._check_mount_contract(src)
    assert any("must assign mcp_app" in err for err in errors)


def test_mount_contract_detects_missing_streamable_path_read() -> None:
    module = _load_guardrail_module()
    src = """
from . import mcp_transport

mcp_app = mcp_transport.mcp.streamable_http_app()

def app():
    streamable_http_path = "/sse"
"""
    errors = module._check_mount_contract(src)
    assert any("root redirect must read" in err for err in errors)
