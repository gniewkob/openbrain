from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_response_normalizers_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_response_normalizers_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_response_normalizers_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_response_normalizers_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_response_normalizers_parity_module()
    assert module.main() == 0


def test_response_normalizers_parity_guardrail_detects_actor_drift() -> None:
    module = _load_response_normalizers_parity_module()
    http_src = """
def _normalize_actor(value, fallback):
    return fallback

def to_legacy_memory_shape(record):
    return record

def normalize_find_hits_to_records(hits):
    return hits

def normalize_find_hits_to_scored_memories(hits):
    return hits
"""
    gateway_src = """
def _normalize_actor(value, fallback):
    return value

def to_legacy_memory_shape(record):
    return record

def normalize_find_hits_to_records(hits):
    return hits

def normalize_find_hits_to_scored_memories(hits):
    return hits
"""
    errors = module._check_normalizers_parity(http_src, gateway_src)
    assert any("_normalize_actor logic must stay identical" in err for err in errors)
