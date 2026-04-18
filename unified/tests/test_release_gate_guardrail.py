from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_release_gate_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_release_gate.py"
    spec = importlib.util.spec_from_file_location("check_release_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_evaluate_release_gate_unprotected(monkeypatch):
    module = _load_release_gate_module()

    monkeypatch.setattr(
        module, "_get_repo_and_branch", lambda: ("gniewkob/openbrain", "master")
    )
    monkeypatch.setattr(module, "_get_branch_protection", lambda _repo, _branch: None)

    result = module.evaluate_release_gate()
    assert result.protected is False
    assert result.healthy is False
    assert tuple(module.REQUIRED_CHECKS) == result.missing_checks


def test_evaluate_release_gate_missing_single_check(monkeypatch):
    module = _load_release_gate_module()
    current_contexts = list(module.REQUIRED_CHECKS[:-1])

    monkeypatch.setattr(
        module, "_get_repo_and_branch", lambda: ("gniewkob/openbrain", "master")
    )
    monkeypatch.setattr(
        module,
        "_get_branch_protection",
        lambda _repo, _branch: {
            "required_status_checks": {"contexts": current_contexts}
        },
    )

    result = module.evaluate_release_gate()
    assert result.protected is True
    assert result.healthy is False
    assert result.missing_checks == (module.REQUIRED_CHECKS[-1],)


def test_evaluate_release_gate_healthy(monkeypatch):
    module = _load_release_gate_module()

    monkeypatch.setattr(
        module, "_get_repo_and_branch", lambda: ("gniewkob/openbrain", "master")
    )
    monkeypatch.setattr(
        module,
        "_get_branch_protection",
        lambda _repo, _branch: {
            "required_status_checks": {"contexts": list(module.REQUIRED_CHECKS)}
        },
    )

    result = module.evaluate_release_gate()
    assert result.protected is True
    assert result.missing_checks == ()
    assert result.healthy is True


def test_release_gate_contract_loader_validates_shape(tmp_path: Path):
    module = _load_release_gate_module()
    broken = tmp_path / "release_gate_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid release gate contract"
        except ValueError as exc:
            assert "required_checks" in str(exc)
    finally:
        module.CONTRACT = old_contract
