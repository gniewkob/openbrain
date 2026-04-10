from __future__ import annotations

import re
from typing import Any

from .contract_loader import load_contract

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _validate_metadata(data: dict[str, Any]) -> dict[str, Any]:
    api_version = data.get("api_version")
    changelog = data.get("schema_changelog")
    if not isinstance(api_version, str) or not _SEMVER.fullmatch(api_version):
        raise ValueError("capabilities_metadata.api_version must match MAJOR.MINOR.PATCH")
    if not isinstance(changelog, dict):
        raise ValueError("capabilities_metadata.schema_changelog must be an object")
    for version, description in changelog.items():
        if not isinstance(version, str) or not _SEMVER.fullmatch(version):
            raise ValueError(
                "capabilities_metadata.schema_changelog keys must match MAJOR.MINOR.PATCH"
            )
        if not isinstance(description, str) or not description.strip():
            raise ValueError(
                "capabilities_metadata.schema_changelog values must be non-empty strings"
            )
    if api_version not in changelog:
        raise ValueError(
            "capabilities_metadata.schema_changelog must include api_version entry"
        )
    return {"api_version": api_version, "schema_changelog": changelog}


def load_capabilities_metadata() -> dict[str, Any]:
    data = load_contract("capabilities_metadata.json")
    return _validate_metadata(data)
