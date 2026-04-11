from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_capabilities_truthfulness_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_capabilities_truthfulness.py"
    spec = importlib.util.spec_from_file_location(
        "check_capabilities_truthfulness", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_truthfulness_guardrail_passes_for_current_sources() -> None:
    module = _load_capabilities_truthfulness_module()
    assert module.main() == 0


def test_capabilities_truthfulness_ast_helpers() -> None:
    module = _load_capabilities_truthfulness_module()

    src_ok = """
async def _get_backend_status():
    return {
        "probe": "readyz",
        "readyz_status_code": 200,
        "primary_path": "/readyz",
        "compat_path": "/api/v1/readyz",
        "secondary_probe": "healthz_fallback",
        "secondary_path": "/healthz",
        "fallback_probe": "api_health_fallback",
        "fallback_path": "/api/v1/health",
    }

async def brain_capabilities():
    health = {"overall": "healthy"}
    return {"health": health}
"""
    assert module._has_health_payload_in_brain_capabilities(src_ok) is True
    assert module._check_health_probe_fallback_semantics(src_ok, "x") == []

    src_missing_health = """
async def brain_capabilities():
    return {"backend": {"status": "ok"}}
"""
    assert module._has_health_payload_in_brain_capabilities(src_missing_health) is False

    src_missing_fallback = """
async def _get_backend_status():
    return {"probe": "readyz", "primary_path": "/readyz"}
"""
    errors = module._check_health_probe_fallback_semantics(src_missing_fallback, "x")
    assert any("api_health_fallback" in err for err in errors)
    assert any("/api/v1/health" in err for err in errors)
    assert any("/api/v1/readyz" in err for err in errors)
    assert any("healthz_fallback" in err for err in errors)
    assert any("/healthz" in err for err in errors)
    assert any("readyz_status_code" in err for err in errors)


def test_capabilities_truthfulness_metadata_check_uses_dynamic_api_version(
    tmp_path,
) -> None:
    module = _load_capabilities_truthfulness_module()
    metadata_path = tmp_path / "capabilities_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "api_version": "2.4.0",
                "schema_changelog": {
                    "2.4.0": "Added another health validation note",
                    "2.3.0": "Added health.overall in capabilities payload",
                },
            }
        ),
        encoding="utf-8",
    )
    original = module.METADATA
    module.METADATA = metadata_path
    try:
        assert module._check_metadata() == []
    finally:
        module.METADATA = original


def test_capabilities_truthfulness_metadata_check_requires_health_entry(tmp_path) -> None:
    module = _load_capabilities_truthfulness_module()
    metadata_path = tmp_path / "capabilities_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "api_version": "2.4.0",
                "schema_changelog": {
                    "2.4.0": "Introduced routing tweaks",
                    "2.3.0": "Initial public contract",
                },
            }
        ),
        encoding="utf-8",
    )
    original = module.METADATA
    module.METADATA = metadata_path
    try:
        errors = module._check_metadata()
    finally:
        module.METADATA = original
    assert any("health semantics entry" in err for err in errors)


def test_capabilities_truthfulness_contract_requires_tier_keys(tmp_path) -> None:
    module = _load_capabilities_truthfulness_module()
    contract_path = tmp_path / "capabilities_response_contract.json"
    contract_path.write_text(
        json.dumps(
            {
                "required_top_level_keys": ["health"],
                "health_required_keys": ["overall", "source", "components"],
                "health_component_required_keys": [
                    "api",
                    "db",
                    "vector_store",
                    "obsidian",
                ],
                "health_overall_values": ["healthy", "degraded", "unavailable"],
                "tier_required_keys": ["status"],
            }
        ),
        encoding="utf-8",
    )
    original = module.CONTRACT
    module.CONTRACT = contract_path
    try:
        errors = module._check_contract()
    finally:
        module.CONTRACT = original
    assert any("tier_required_keys" in err for err in errors)


def test_capabilities_truthfulness_checks_health_source_and_obsidian_mapping(
    tmp_path,
) -> None:
    module = _load_capabilities_truthfulness_module()
    ok_path = tmp_path / "capabilities_health_ok.py"
    ok_path.write_text(
        """
def build_capabilities_health(backend, obsidian_status):
    return {
        "overall": "healthy",
        "source": backend.get("probe", "unknown"),
        "components": {
            "obsidian": "enabled" if obsidian_status == "enabled" else "disabled",
        },
    }
""",
        encoding="utf-8",
    )
    assert module._check_capabilities_health_contract(ok_path, "x") == []

    bad_path = tmp_path / "capabilities_health_bad.py"
    bad_path.write_text(
        """
def build_capabilities_health(backend, obsidian_status):
    return {
        "overall": "healthy",
        "source": "healthz_fallback",
        "components": {
            "obsidian": obsidian_status,
        },
    }
""",
        encoding="utf-8",
    )
    errors = module._check_capabilities_health_contract(bad_path, "x")
    assert any("health.source" in err for err in errors)
    assert any("obsidian component" in err for err in errors)
