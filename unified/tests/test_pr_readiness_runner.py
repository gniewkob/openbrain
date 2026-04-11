from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_pr_readiness_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_pr_readiness.py"
    spec = importlib.util.spec_from_file_location("check_pr_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pr_readiness_runner_success(monkeypatch) -> None:
    module = _load_pr_readiness_module()
    monkeypatch.setattr(module, "run_step", lambda _label, _cmd: 0)
    assert module.main() == 0


def test_pr_readiness_runner_stops_on_first_failure(monkeypatch) -> None:
    module = _load_pr_readiness_module()
    seen: list[str] = []

    def _run_step(label: str, _cmd: list[str]) -> int:
        seen.append(label)
        if label == module.PR_READINESS_STEPS[1][0]:
            return 3
        return 0

    monkeypatch.setattr(module, "run_step", _run_step)
    assert module.main() == 3
    assert seen == [module.PR_READINESS_STEPS[0][0], module.PR_READINESS_STEPS[1][0]]


def test_pr_readiness_contract_smoke_includes_transport_parity() -> None:
    module = _load_pr_readiness_module()
    step = next(
        (cmd for label, cmd in module.PR_READINESS_STEPS if label == "contract integrity smoke"),
        [],
    )
    assert "unified/tests/test_transport_parity.py" in step


def test_pr_readiness_guardrail_runner_includes_self_runner_test() -> None:
    module = _load_pr_readiness_module()
    step = next(
        (cmd for label, cmd in module.PR_READINESS_STEPS if label == "guardrail runner tests"),
        [],
    )
    assert "unified/tests/test_pr_readiness_runner.py" in step
