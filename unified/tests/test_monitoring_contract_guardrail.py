from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_monitoring_contract_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "validate_monitoring_contract.py"
    spec = importlib.util.spec_from_file_location("validate_monitoring_contract", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_metric_tokens_ignores_promql_keywords() -> None:
    module = _load_monitoring_contract_module()
    expr = (
        'sum(rate(http_requests_total_500{job="openbrain-unified"}[5m])) '
        "/ clamp_min(rate(http_requests_total_200{job=\"openbrain-unified\"}[5m]), 0.000001)"
    )
    tokens = module.extract_metric_tokens(expr)
    assert "http_requests_total_500" in tokens
    assert "http_requests_total_200" in tokens
    assert "sum" not in tokens
    assert "rate" not in tokens
    assert "job" not in tokens


def test_validate_monitoring_contract_flags_unexpected_metric(tmp_path: Path) -> None:
    module = _load_monitoring_contract_module()
    dashboard_path = tmp_path / "dashboard.json"
    dashboard_path.write_text(
        json.dumps(
            {
                "panels": [
                    {"title": "Test", "targets": [{"expr": "mystery_metric_total{job=\"x\"}"}]}
                ]
            }
        ),
        encoding="utf-8",
    )
    contract = {"required_metrics": ["http_requests_total_200"], "dashboard_files": []}
    errors, referenced, live = module.validate_monitoring_contract(
        contract,
        [dashboard_path],
        [],
        forbid_vector_zero=False,
        check_live_metrics=False,
        metrics_url="http://127.0.0.1:9180/metrics",
    )
    assert any("Monitoring expressions reference metrics not in contract" in err for err in errors)
    assert "mystery_metric_total" in referenced
    assert live == set()


def test_validate_monitoring_contract_flags_unexpected_metric_from_alert_rule(
    tmp_path: Path,
) -> None:
    module = _load_monitoring_contract_module()
    alert_rules_path = tmp_path / "alerts.yml"
    alert_rules_path.write_text(
        "\n".join(
            [
                "groups:",
                "  - name: test",
                "    rules:",
                "      - alert: TestAlert",
                "        expr: mystery_alert_metric_total > 0",
            ]
        ),
        encoding="utf-8",
    )
    contract = {"required_metrics": ["http_requests_total_200"], "dashboard_files": []}
    errors, referenced, _ = module.validate_monitoring_contract(
        contract,
        [],
        [alert_rules_path],
        forbid_vector_zero=False,
        check_live_metrics=False,
        metrics_url="http://127.0.0.1:9180/metrics",
    )
    assert any("Monitoring expressions reference metrics not in contract" in err for err in errors)
    assert "mystery_alert_metric_total" in referenced


def test_load_alert_rule_exprs_supports_multiline_expr_block(tmp_path: Path) -> None:
    module = _load_monitoring_contract_module()
    alert_rules_path = tmp_path / "alerts.yml"
    alert_rules_path.write_text(
        "\n".join(
            [
                "groups:",
                "  - name: test",
                "    rules:",
                "      - alert: ComplexAlert",
                "        expr: |",
                "          increase(search_requests_total{job=\"openbrain-unified\"}[1h])",
                "          / clamp_min(increase(sync_checks_total{job=\"openbrain-unified\"}[1h]), 1)",
            ]
        ),
        encoding="utf-8",
    )

    exprs = module.load_alert_rule_exprs(alert_rules_path)
    assert len(exprs) == 1
    rule_name, expr = exprs[0]
    assert rule_name == "ComplexAlert"
    assert "search_requests_total" in expr
    assert "sync_checks_total" in expr


def test_main_succeeds_without_live_metrics_check(monkeypatch) -> None:
    module = _load_monitoring_contract_module()
    monkeypatch.setattr(module, "validate_monitoring_contract", lambda *_args, **_kwargs: ([], {"a"}, set()))
    monkeypatch.setattr(sys, "argv", ["validate_monitoring_contract.py"])
    assert module.main() == 0


def test_main_fails_when_live_metrics_check_errors(monkeypatch) -> None:
    module = _load_monitoring_contract_module()
    monkeypatch.setattr(
        module,
        "validate_monitoring_contract",
        lambda *_args, **_kwargs: (["Failed to fetch live metrics from x"], set(), set()),
    )
    monkeypatch.setattr(sys, "argv", ["validate_monitoring_contract.py", "--check-live"])
    assert module.main() == 1


def test_main_forbids_vector_zero_by_default(monkeypatch) -> None:
    module = _load_monitoring_contract_module()
    seen: dict[str, bool] = {}

    def _validate(*_args, **kwargs):
        seen["forbid_vector_zero"] = kwargs["forbid_vector_zero"]
        return [], set(), set()

    monkeypatch.setattr(module, "validate_monitoring_contract", _validate)
    monkeypatch.setattr(sys, "argv", ["validate_monitoring_contract.py"])
    assert module.main() == 0
    assert seen["forbid_vector_zero"] is True


def test_main_can_allow_vector_zero(monkeypatch) -> None:
    module = _load_monitoring_contract_module()
    seen: dict[str, bool] = {}

    def _validate(*_args, **kwargs):
        seen["forbid_vector_zero"] = kwargs["forbid_vector_zero"]
        return [], set(), set()

    monkeypatch.setattr(module, "validate_monitoring_contract", _validate)
    monkeypatch.setattr(sys, "argv", ["validate_monitoring_contract.py", "--allow-vector-zero"])
    assert module.main() == 0
    assert seen["forbid_vector_zero"] is False
