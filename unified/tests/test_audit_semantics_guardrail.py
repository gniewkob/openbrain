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
