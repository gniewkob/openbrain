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
