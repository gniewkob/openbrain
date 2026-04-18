from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_audit_semantics_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_audit_semantics.py"
    spec = importlib.util.spec_from_file_location("check_audit_semantics", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_audit_semantics_guardrail_passes_for_current_sources() -> None:
    module = _load_audit_semantics_module()
    assert module.main() == 0


def test_audit_semantics_ast_helpers_detect_expected_shapes() -> None:
    module = _load_audit_semantics_module()

    schema_src = """
class MemoryWriteRecord(BaseModel):
    content: str
    domain: str
"""
    assert module._field_names_in_class(schema_src, "MemoryWriteRecord") == {
        "content",
        "domain",
    }

    patch_src_ok = """
async def v1_update(memory_id, data):
    actor = "auth-sub"
    safe_data = data.model_copy(update={"updated_by": actor})
    updated = await update_memory(session, memory_id, safe_data, actor=actor)
"""
    assert module._has_patch_actor_override(patch_src_ok) is True

    patch_src_bad = """
async def v1_update(memory_id, data):
    actor = "auth-sub"
    updated = await update_memory(session, memory_id, data, actor=actor)
"""
    assert module._has_patch_actor_override(patch_src_bad) is False


def test_mcp_updated_by_placeholder_guardrail_patterns(tmp_path) -> None:
    module = _load_audit_semantics_module()
    contract = module._load_contract()
    mcp_patterns = [
        str(pattern) for pattern in contract["mcp_placeholder_required_patterns"]
    ]

    ok_src = """
async def brain_update(memory_id: str, content: str, updated_by: str = "agent"):
    _ = normalize_updated_by(updated_by)
    payload = {"content": content, "updated_by": canonical_updated_by()}
"""
    bad_src = """
async def brain_update(memory_id: str, content: str, updated_by: str = "agent"):
    payload = {"content": content, "updated_by": updated_by}
"""
    transport = tmp_path / "transport.py"
    gateway = tmp_path / "gateway.py"
    transport.write_text(ok_src, encoding="utf-8")
    gateway.write_text(bad_src, encoding="utf-8")

    module.MCP_TRANSPORT = transport
    module.MCP_GATEWAY = gateway
    errors = module._check_mcp_updated_by_placeholder_binding(mcp_patterns)
    assert any(
        "mcp-gateway/src/main.py missing MCP audit placeholder pattern" in err
        for err in errors
    )


def test_audit_semantics_contract_loader_validates_shape(tmp_path: Path) -> None:
    module = _load_audit_semantics_module()
    broken = tmp_path / "audit_semantics_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid audit semantics contract"
        except ValueError as exc:
            assert "memory_write_required_patterns" in str(exc)
    finally:
        module.CONTRACT = old_contract
