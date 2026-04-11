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


def test_local_guardrails_includes_telemetry_contract_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "telemetry contract parity",
        "scripts/check_telemetry_contract_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_dashboard_memory_semantics_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "dashboard memory semantics",
        "scripts/check_dashboard_memory_semantics.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_hidden_test_data_alert_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "hidden test-data alert parity",
        "scripts/check_hidden_test_data_alert_parity.py",
    ) in module.GUARDRAIL_STEPS


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


def test_local_guardrails_includes_capabilities_health_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "capabilities health parity",
        "scripts/check_capabilities_health_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_request_runtime_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "request/runtime parity",
        "scripts/check_request_runtime_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_shared_http_client_reuse_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "shared http client reuse",
        "scripts/check_shared_http_client_reuse.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_tool_signature_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "tool signature parity",
        "scripts/check_tool_signature_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_admin_bounds_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "admin bounds parity",
        "scripts/check_admin_bounds_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_admin_endpoint_contract_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "admin endpoint contract parity",
        "scripts/check_admin_endpoint_contract_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_tool_inventory_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "tool inventory parity",
        "scripts/check_tool_inventory_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_capabilities_tools_truthfulness_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "capabilities tools truthfulness",
        "scripts/check_capabilities_tools_truthfulness.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_search_filter_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "search filter parity",
        "scripts/check_search_filter_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_list_filter_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "list filter parity",
        "scripts/check_list_filter_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_response_normalizers_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "response normalizers parity",
        "scripts/check_response_normalizers_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_http_error_adapter_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "http error adapter parity",
        "scripts/check_http_error_adapter_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_delete_semantics_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "delete semantics parity",
        "scripts/check_delete_semantics_parity.py",
    ) in module.GUARDRAIL_STEPS


def test_local_guardrails_includes_update_audit_semantics_parity_step() -> None:
    module = _load_local_guardrails_module()
    assert (
        "update audit semantics parity",
        "scripts/check_update_audit_semantics_parity.py",
    ) in module.GUARDRAIL_STEPS
