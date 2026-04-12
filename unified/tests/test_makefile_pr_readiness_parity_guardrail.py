from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_makefile_pr_readiness_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_makefile_pr_readiness_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_makefile_pr_readiness_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_makefile_pr_readiness_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_makefile_pr_readiness_parity_module()
    assert module.main() == 0


def test_makefile_pr_readiness_parity_detects_drift() -> None:
    module = _load_makefile_pr_readiness_parity_module()
    pr_source = """
PR_READINESS_STEPS = (
    ("guardrail runner tests", ["x", "unified/tests/a.py", "unified/tests/b.py"]),
    ("contract integrity smoke", ["x", "unified/tests/c.py"]),
)
"""
    make_source = """
guardrail-tests: check-unified-venv
\t"$(UNIFIED_PYTHON)" -m pytest -q \\
\t\tunified/tests/a.py

contract-smoke: check-unified-venv
\t"$(UNIFIED_PYTHON)" -m pytest -q \\
\t\tunified/tests/d.py
"""
    errors = module._check_parity(pr_source, make_source)
    assert any("guardrail-tests drift" in err for err in errors)
    assert any("contract-smoke drift" in err for err in errors)


def test_makefile_pr_readiness_parity_supports_annotated_assignment() -> None:
    module = _load_makefile_pr_readiness_parity_module()
    pr_source = """
PR_READINESS_STEPS: tuple[tuple[str, list[str]], ...] = (
    ("guardrail runner tests", ["x", "unified/tests/a.py"]),
    ("contract integrity smoke", ["x", "unified/tests/b.py"]),
)
"""
    make_source = """
guardrail-tests: check-unified-venv
\t"$(UNIFIED_PYTHON)" -m pytest -q \\
\t\tunified/tests/a.py

contract-smoke: check-unified-venv
\t"$(UNIFIED_PYTHON)" -m pytest -q \\
\t\tunified/tests/b.py
"""
    assert module._check_parity(pr_source, make_source) == []


def test_makefile_pr_readiness_parity_supports_starred_contract_lists(
    tmp_path: Path,
) -> None:
    module = _load_makefile_pr_readiness_parity_module()
    contract = tmp_path / "pr_readiness_runner_contract.json"
    contract.write_text(
        """
{
  "guardrail_runner_test_files": ["unified/tests/a.py"],
  "contract_integrity_test_files": ["unified/tests/b.py"],
  "step_timeouts_seconds": {
    "local guardrails": 180,
    "guardrail runner tests": 300,
    "contract integrity smoke": 300
  }
}
""".strip(),
        encoding="utf-8",
    )
    pr_source = """
PR_READINESS_STEPS = (
    ("guardrail runner tests", ["x", *_GUARDRAIL_TESTS]),
    ("contract integrity smoke", ["x", *_CONTRACT_SMOKE_TESTS]),
)
"""
    make_source = """
guardrail-tests: check-unified-venv
\t"$(UNIFIED_PYTHON)" -m pytest -q \\
\t\tunified/tests/a.py

contract-smoke: check-unified-venv
\t"$(UNIFIED_PYTHON)" -m pytest -q \\
\t\tunified/tests/b.py
"""
    old_contract = module.PR_READINESS_CONTRACT
    module.PR_READINESS_CONTRACT = contract
    try:
        assert module._check_parity(pr_source, make_source) == []
    finally:
        module.PR_READINESS_CONTRACT = old_contract
