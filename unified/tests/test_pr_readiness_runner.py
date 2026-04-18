from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
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
        (
            cmd
            for label, cmd in module.PR_READINESS_STEPS
            if label == "contract integrity smoke"
        ),
        [],
    )
    assert "unified/tests/test_transport_parity.py" in step


def test_pr_readiness_contract_smoke_includes_core_contract_tests() -> None:
    module = _load_pr_readiness_module()
    step = next(
        (
            cmd
            for label, cmd in module.PR_READINESS_STEPS
            if label == "contract integrity smoke"
        ),
        [],
    )
    required = {
        "unified/tests/test_contract_integrity.py",
        "unified/tests/test_capabilities_response_contract.py",
        "unified/tests/test_health_route_alias_contract.py",
        "unified/tests/test_find_endpoint_validation.py",
    }
    assert required.issubset(set(step))


def test_pr_readiness_contract_smoke_includes_admin_openapi_contract() -> None:
    module = _load_pr_readiness_module()
    step = next(
        (
            cmd
            for label, cmd in module.PR_READINESS_STEPS
            if label == "contract integrity smoke"
        ),
        [],
    )
    assert "unified/tests/test_admin_openapi_contract.py" in step


def test_pr_readiness_guardrail_runner_includes_self_runner_test() -> None:
    module = _load_pr_readiness_module()
    step = next(
        (
            cmd
            for label, cmd in module.PR_READINESS_STEPS
            if label == "guardrail runner tests"
        ),
        [],
    )
    assert "unified/tests/test_pr_readiness_runner.py" in step


def test_pr_readiness_guardrail_runner_includes_mcp_transport_import_scope_test() -> (
    None
):
    module = _load_pr_readiness_module()
    step = next(
        (
            cmd
            for label, cmd in module.PR_READINESS_STEPS
            if label == "guardrail runner tests"
        ),
        [],
    )
    assert "unified/tests/test_mcp_transport_import_scope_guardrail.py" in step


def test_pr_readiness_guardrail_runner_includes_mcp_transport_mount_contract_test() -> (
    None
):
    module = _load_pr_readiness_module()
    step = next(
        (
            cmd
            for label, cmd in module.PR_READINESS_STEPS
            if label == "guardrail runner tests"
        ),
        [],
    )
    assert "unified/tests/test_mcp_transport_mount_contract_guardrail.py" in step


def test_pr_readiness_step_timeouts_defined_for_all_steps() -> None:
    module = _load_pr_readiness_module()
    labels = {label for label, _ in module.PR_READINESS_STEPS}
    assert labels.issubset(set(module.STEP_TIMEOUT_SECONDS.keys()))


def test_pr_readiness_run_step_returns_124_on_timeout(monkeypatch) -> None:
    module = _load_pr_readiness_module()

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["pytest"], timeout=1)

    monkeypatch.setattr(module.subprocess, "run", _timeout)
    assert module.run_step("contract integrity smoke", ["pytest"]) == 124


def test_pr_readiness_contract_loader_validates_shape(tmp_path: Path) -> None:
    module = _load_pr_readiness_module()
    broken = tmp_path / "pr_readiness_runner_contract.json"
    broken.write_text("{}", encoding="utf-8")

    original_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid PR readiness contract"
        except ValueError as exc:
            assert "guardrail_runner_test_files" in str(exc)
    finally:
        module.CONTRACT = original_contract
