from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import uuid


def _load_secret_scan_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_no_committed_secrets.py"
    spec = importlib.util.spec_from_file_location("check_no_committed_secrets", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_placeholder_values_are_ignored() -> None:
    module = _load_secret_scan_module()
    assert module._is_placeholder("${INTERNAL_API_KEY}") is True
    assert module._is_placeholder("$TOKEN") is True
    assert module._is_placeholder("changeme") is True
    assert module._is_placeholder("your-secret-here") is True


def _create_repo_scoped_tmp_dir(module) -> Path:
    tmp_dir = module.ROOT / "unified" / "tests" / ".tmp_secret_scan_guardrail" / str(uuid.uuid4())
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def test_main_detects_real_secret_like_value(monkeypatch) -> None:
    module = _load_secret_scan_module()
    tmp_dir = _create_repo_scoped_tmp_dir(module)
    try:
        suspect = tmp_dir / "settings.env"
        suspect.write_text("INTERNAL_API_KEY=super-real-secret-value\n", encoding="utf-8")
        monkeypatch.setattr(module, "tracked_files", lambda: [suspect])
        assert module.main() == 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_main_allows_placeholder_secret_values(monkeypatch) -> None:
    module = _load_secret_scan_module()
    tmp_dir = _create_repo_scoped_tmp_dir(module)
    try:
        env_file = tmp_dir / ".env.example"
        env_file.write_text(
            "INTERNAL_API_KEY=${INTERNAL_API_KEY}\nPOSTGRES_PASSWORD=changeme\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(module, "tracked_files", lambda: [env_file])
        assert module.main() == 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
