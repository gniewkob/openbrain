from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_guardrail_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_mcp_transport_import_scope.py"
    spec = importlib.util.spec_from_file_location(
        "check_mcp_transport_import_scope", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mcp_transport_import_scope_guardrail_passes_for_current_sources() -> None:
    module = _load_guardrail_module()
    assert module.main() == 0


def test_import_scope_rejects_non_test_importers() -> None:
    module = _load_guardrail_module()
    errors = module._check_import_scope(
        ["unified/src/combined.py", "unified/src/api/v1/memory.py"]
    )
    assert any("outside approved scope" in err for err in errors)


def test_import_scope_requires_combined_import() -> None:
    module = _load_guardrail_module()
    errors = module._check_import_scope(["unified/tests/test_mcp_transport.py"])
    assert "unified/src/combined.py must import mcp_transport" in errors
