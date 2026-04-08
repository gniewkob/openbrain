from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_repo_hygiene_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_repo_hygiene.py"
    spec = importlib.util.spec_from_file_location("check_repo_hygiene", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repo_hygiene_guardrail_passes_for_current_sources() -> None:
    module = _load_repo_hygiene_module()
    assert module.main() == 0


def test_find_forbidden_artifacts_detects_known_paths(tmp_path: Path) -> None:
    module = _load_repo_hygiene_module()
    (tmp_path / "reproduce_hang.py").write_text("print('debug')\n", encoding="utf-8")
    violations = module.find_forbidden_artifacts(
        tmp_path, ("reproduce_hang.py", "other_debug.py")
    )
    assert violations == ["reproduce_hang.py"]
