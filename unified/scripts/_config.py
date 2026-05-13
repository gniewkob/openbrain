"""Shared configuration helpers for OpenBrain maintenance scripts.

Path resolution (highest priority first):
1. Env vars: OPENBRAIN_CONFIG, OPENBRAIN_LOG_DIR, OBSIDIAN_VAULT_ROOT
2. Auto-derived from __file__: scripts/ → unified/ → <repo-root>/
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# Repo root is 2 levels up: scripts/ -> unified/ -> openbrain/
_REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH: Path = Path(
    os.environ.get("OPENBRAIN_CONFIG", str(_REPO_ROOT / ".mcp.json"))
)
LOG_DIR: Path = Path(
    os.environ.get("OPENBRAIN_LOG_DIR", str(_REPO_ROOT / "unified" / "logs"))
)


@dataclass(frozen=True)
class Conn:
    """Backend connection parameters."""

    base_url: str
    api_key: str


def load_conn() -> Conn:
    """Load backend connection parameters from .mcp.json config."""
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env = data["mcpServers"]["openbrain"]["env"]
    return Conn(base_url=env["BRAIN_URL"].rstrip("/"), api_key=env["INTERNAL_API_KEY"])


def vault_root() -> Path:
    """Return the personal Obsidian vault root.

    Reads OBSIDIAN_VAULT_ROOT env var (required for scripts touching vault filesystem).
    Raises RuntimeError if unset to prevent silent wrong-path failures.
    """
    val = os.environ.get("OBSIDIAN_VAULT_ROOT")
    if val:
        return Path(val)
    # Fallback: derive from OBSIDIAN_PERSONAL_VAULT if set (same var used by docker-compose)
    val = os.environ.get("OBSIDIAN_PERSONAL_VAULT")
    if val:
        return Path(val)
    raise RuntimeError(
        "Set OBSIDIAN_VAULT_ROOT (or OBSIDIAN_PERSONAL_VAULT) to the vault filesystem path."
    )
