from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_compose_guardrails_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_compose_guardrails.py"
    spec = importlib.util.spec_from_file_location("check_compose_guardrails", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compose_guardrails_pass_for_current_file() -> None:
    module = _load_compose_guardrails_module()
    assert module.main() == 0


def test_find_missing_required_snippets_detects_missing_values() -> None:
    module = _load_compose_guardrails_module()
    content = "POSTGRES_USER: ${POSTGRES_USER}\n"
    missing = module.find_missing_required_snippets(content)
    assert 'POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}' in missing
    assert 'POSTGRES_DB: ${POSTGRES_DB}' in missing


def test_find_forbidden_snippets_detects_hardcoded_defaults() -> None:
    module = _load_compose_guardrails_module()
    content = "DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/openbrain\n"
    forbidden = module.find_forbidden_snippets(content)
    assert "postgresql+asyncpg://postgres:postgres" in forbidden
