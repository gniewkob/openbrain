from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_compose_guardrails_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_compose_guardrails.py"
    spec = importlib.util.spec_from_file_location(
        "check_compose_guardrails", script_path
    )
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
    contract = module.load_contract()
    content = "POSTGRES_USER: ${POSTGRES_USER}\n"
    missing = module.find_missing_required_snippets(
        content, contract["required_snippets"]
    )
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}" in missing
    assert "POSTGRES_DB: ${POSTGRES_DB}" in missing


def test_find_forbidden_snippets_detects_hardcoded_defaults() -> None:
    module = _load_compose_guardrails_module()
    contract = module.load_contract()
    content = "DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/openbrain\n"
    forbidden = module.find_forbidden_snippets(content, contract["forbidden_snippets"])
    assert "postgresql+asyncpg://postgres:postgres" in forbidden


def test_find_missing_public_transport_snippets_detects_ngrok_regressions() -> None:
    module = _load_compose_guardrails_module()
    contract = module.load_contract()
    content = """
PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
INTERNAL_API_KEY=${INTERNAL_API_KEY}
command:
  - "http"
  - "mcp-http:7011"
"""
    missing = module.find_missing_public_transport_snippets(
        content, contract["required_public_transport_snippets"]
    )
    assert "http://mcp-http:7011" in missing
    assert "--url=${NGROK_DOMAIN}" in missing


def test_compose_guardrails_contract_loader_validates_required_keys(
    tmp_path: Path,
) -> None:
    module = _load_compose_guardrails_module()
    broken = tmp_path / "compose_guardrails_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract_path = module.CONTRACT_PATH
    module.CONTRACT_PATH = broken
    try:
        try:
            module.load_contract()
            assert False, "expected ValueError for invalid compose guardrails contract"
        except ValueError as exc:
            assert "required_snippets" in str(exc)
    finally:
        module.CONTRACT_PATH = old_contract_path
