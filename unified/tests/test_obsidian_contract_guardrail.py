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
    )
    assert any("gateway disabled reason missing snippet" in err for err in errors)
    assert any("HTTP disabled reason missing snippet" in err for err in errors)
