from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_cleanup_actor_semantics_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_cleanup_actor_semantics.py"
    spec = importlib.util.spec_from_file_location(
        "check_cleanup_actor_semantics", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cleanup_actor_semantics_guardrail_passes_for_current_source() -> None:
    module = _load_cleanup_actor_semantics_module()
    assert module.main() == 0


def test_cleanup_actor_semantics_detects_missing_fallback() -> None:
    module = _load_cleanup_actor_semantics_module()
    src = """
async def cleanup_build_test_data(req, session, _user):
    require_admin(_user)
    actor = get_subject(_user)
    return await cleanup_build_test_data_use_case(
        session,
        dry_run=req.dry_run,
        limit=req.limit,
        actor=actor,
    )
"""
    errors = module._check_cleanup_actor_semantics(src)
    assert any(
        "must set actor via get_subject(_user) or 'agent'" in err for err in errors
    )
