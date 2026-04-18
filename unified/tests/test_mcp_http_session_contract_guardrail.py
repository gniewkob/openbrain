from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_guardrail_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_mcp_http_session_contract.py"
    spec = importlib.util.spec_from_file_location(
        "check_mcp_http_session_contract", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mcp_http_session_contract_guardrail_passes_for_current_sources() -> None:
    module = _load_guardrail_module()
    assert module.main() == 0


def test_extract_mcp_run_kwargs() -> None:
    module = _load_guardrail_module()
    src = """
def main():
    mcp.run(
        transport="streamable-http",
        path="/",
        host="0.0.0.0",
        stateless_http=True,
    )
"""
    tree = module.ast.parse(src)
    kwargs = module._extract_mcp_run_kwargs(tree)
    assert kwargs["transport"] == "streamable-http"
    assert kwargs["path"] == "/"
    assert kwargs["stateless_http"] == "True"


def test_custom_route_detection() -> None:
    module = _load_guardrail_module()
    src = """
@mcp.custom_route("/consent", methods=["GET"])
def consent():
    return None
"""
    tree = module.ast.parse(src)
    assert module._has_custom_route(tree, "/consent") is True
    assert module._has_custom_route(tree, "/missing") is False


def test_main_entrypoint_detection() -> None:
    module = _load_guardrail_module()
    src_ok = """
def main():
    return None

if __name__ == "__main__":
    main()
"""
    src_missing = """
def main():
    return None
"""
    assert module._has_main_entrypoint_call(module.ast.parse(src_ok)) is True
    assert module._has_main_entrypoint_call(module.ast.parse(src_missing)) is False


def test_mcp_http_session_contract_loader_validates_required_keys(
    tmp_path: Path,
) -> None:
    module = _load_guardrail_module()
    broken = tmp_path / "mcp_http_session_contract.json"
    broken.write_text("{}", encoding="utf-8")

    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for missing contract keys"
        except ValueError as exc:
            assert "missing keys" in str(exc)
    finally:
        module.CONTRACT = old_contract
