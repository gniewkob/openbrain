from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_obsidian_contract_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_obsidian_contract.py"
    spec = importlib.util.spec_from_file_location("check_obsidian_contract", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_obsidian_contract_guardrail_passes_for_current_sources() -> None:
    module = _load_obsidian_contract_module()
    assert module.main() == 0


def test_obsidian_contract_ast_helpers() -> None:
    module = _load_obsidian_contract_module()

    src_with_call = """
async def brain_obsidian_sync():
    _require_obsidian_local_tools_enabled()
    return {"ok": True}
"""
    tree = module.ast.parse(src_with_call)
    fn = module._find_async_function(tree, "brain_obsidian_sync")
    assert fn is not None
    assert module._function_calls_name(fn, "_require_obsidian_local_tools_enabled") is True

    src_without_call = """
async def brain_obsidian_sync():
    return {"ok": True}
"""
    tree_no = module.ast.parse(src_without_call)
    fn_no = module._find_async_function(tree_no, "brain_obsidian_sync")
    assert fn_no is not None
    assert module._function_calls_name(fn_no, "_require_obsidian_local_tools_enabled") is False

    transport_src_ok = """
ENABLE_HTTP_OBSIDIAN_TOOLS = True
if ENABLE_HTTP_OBSIDIAN_TOOLS:
    async def brain_obsidian_vaults():
        return {}
    async def brain_obsidian_read_note():
        return {}
"""
    assert (
        module._http_obsidian_tools_defined_under_flag(
            transport_src_ok, ["obsidian_vaults", "obsidian_read_note"]
        )
        is True
    )

    transport_src_missing = """
ENABLE_HTTP_OBSIDIAN_TOOLS = True
if ENABLE_HTTP_OBSIDIAN_TOOLS:
    async def brain_obsidian_vaults():
        return {}
"""
    assert (
        module._http_obsidian_tools_defined_under_flag(
            transport_src_missing, ["obsidian_vaults", "obsidian_read_note"]
        )
        is False
    )


def test_obsidian_contract_requires_disabled_reason_snippets() -> None:
    module = _load_obsidian_contract_module()
    errors = module._check_disabled_reason_snippets(
        gateway_text="Set {OBSIDIAN_LOCAL_TOOLS_ENV}=1",
        http_text="Set ENABLE_HTTP_OBSIDIAN_TOOLS=1 before starting transport.",
        http_utils_text="",
    )
    assert any("gateway disabled reason missing snippet" in err for err in errors)
    assert any("HTTP disabled reason missing snippet" in err for err in errors)


def test_obsidian_contract_allows_http_disabled_reason_via_utils_delegate() -> None:
    module = _load_obsidian_contract_module()
    errors = module._check_disabled_reason_snippets(
        gateway_text=(
            "Local Obsidian tools are disabled by default.\n"
            "trusted local stdio gateway\n"
            "Set {OBSIDIAN_LOCAL_TOOLS_ENV}=1"
        ),
        http_text=(
            "def _http_obsidian_disabled_reason():\n"
            "    return http_obsidian_disabled_reason()\n"
        ),
        http_utils_text=(
            "HTTP Obsidian tools are disabled by default.\n"
            "Set ENABLE_HTTP_OBSIDIAN_TOOLS=1 before starting transport.\n"
        ),
    )
    assert errors == []


def test_obsidian_contract_checks_capabilities_payload_semantics() -> None:
    module = _load_obsidian_contract_module()

    src_ok = """
async def brain_capabilities():
    obsidian_status = "disabled"
    obsidian_tools = []
    obsidian_reason = "x"
    return {
        "obsidian": {
            "mode": "http",
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
        "obsidian_http": {
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
    }
"""
    assert (
        module._check_obsidian_capabilities_payload_semantics(
            src_ok,
            label="http",
            expected_mode="http",
            expected_secondary_key="obsidian_http",
        )
        == []
    )

    src_bad = """
async def brain_capabilities():
    obsidian_status = "disabled"
    obsidian_tools = []
    obsidian_reason = "x"
    return {
        "obsidian": {
            "mode": "local",
            "status": "disabled",
            "tools": [],
            "reason": None,
        },
        "obsidian_http": {
            "status": "disabled",
            "tools": [],
            "reason": None,
        },
    }
"""
    errors = module._check_obsidian_capabilities_payload_semantics(
        src_bad,
        label="http",
        expected_mode="http",
        expected_secondary_key="obsidian_http",
    )
    assert any("obsidian.mode must be constant 'http'" in err for err in errors)
    assert any("obsidian.status must reference obsidian_status" in err for err in errors)
    assert any("obsidian_http.status must reference obsidian_status" in err for err in errors)


def test_obsidian_contract_validates_disabled_reason_contract_shape(tmp_path: Path) -> None:
    module = _load_obsidian_contract_module()
    broken = tmp_path / "obsidian_disabled_reason_contract.json"
    broken.write_text("{}", encoding="utf-8")

    old_contract = module.DISABLED_REASON_CONTRACT
    module.DISABLED_REASON_CONTRACT = broken
    try:
        errors = module._check_disabled_reason_snippets(
            gateway_text="x",
            http_text="x",
            http_utils_text="x",
        )
    finally:
        module.DISABLED_REASON_CONTRACT = old_contract

    assert any("gateway_snippets" in err for err in errors)


def test_obsidian_contract_validates_guardrail_contract_shape(tmp_path: Path) -> None:
    module = _load_obsidian_contract_module()
    broken = tmp_path / "obsidian_guardrail_contract.json"
    broken.write_text('{"gateway":{},"http":{}}', encoding="utf-8")

    old_contract = module.GUARDRAIL_CONTRACT
    module.GUARDRAIL_CONTRACT = broken
    try:
        gateway_errors = module._check_gateway_gating()
        http_errors = module._check_http_transport_contract()
    finally:
        module.GUARDRAIL_CONTRACT = old_contract

    assert any("required_env_constant_snippet" in err for err in gateway_errors)
    assert any("required_guard_function" in err for err in gateway_errors)
    assert any("required_capability_snippets" in err for err in gateway_errors)
    assert any("required_gate_snippet" in err for err in http_errors)
    assert any("required_capability_snippets" in err for err in http_errors)


def test_obsidian_contract_guardrail_loader_requires_sections(tmp_path: Path) -> None:
    module = _load_obsidian_contract_module()
    broken = tmp_path / "obsidian_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")

    old_contract = module.GUARDRAIL_CONTRACT
    module.GUARDRAIL_CONTRACT = broken
    try:
        _, errors = module._load_obsidian_guardrail_contract()
    finally:
        module.GUARDRAIL_CONTRACT = old_contract

    assert any("gateway must be object" in err for err in errors)
    assert any("http must be object" in err for err in errors)
