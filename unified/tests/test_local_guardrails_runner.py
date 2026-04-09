from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_local_guardrails_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_local_guardrails.py"
    spec = importlib.util.spec_from_file_location("check_local_guardrails", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_guardrails_runner_success(monkeypatch) -> None:
    module = _load_local_guardrails_module()
    monkeypatch.setattr(module, "run_step", lambda _label, _script: 0)
    assert module.main() == 0


def test_local_guardrails_runner_stops_on_first_failure(monkeypatch) -> None:
    module = _load_local_guardrails_module()
    seen: list[str] = []

    def _run_step(label: str, _script: str) -> int:
        seen.append(label)
        if label == module.GUARDRAIL_STEPS[1][0]:
            return 2
        return 0

    monkeypatch.setattr(module, "run_step", _run_step)
    assert module.main() == 2
    assert seen == [module.GUARDRAIL_STEPS[0][0], module.GUARDRAIL_STEPS[1][0]]


def test_local_guardrails_includes_monitoring_contract_step() -> None:
    module = _load_local_guardrails_module()
    assert ("monitoring contract", "scripts/validate_monitoring_contract.py") in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_export_contract_step() -> None:
    module = _load_local_guardrails_module()
    assert ("export contract", "scripts/check_export_contract.py") in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_capabilities_manifest_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "capabilities manifest parity",
        "scripts/check_capabilities_manifest_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_capabilities_metadata_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "capabilities metadata parity",
        "scripts/check_capabilities_metadata_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_request_runtime_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "request/runtime parity",
        "scripts/check_request_runtime_parity.py",
    ) in module.GUARDRAIL_STEPS
