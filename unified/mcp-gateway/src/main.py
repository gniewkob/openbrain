"""
OpenBrain Unified MCP Gateway — exposes brain_* tools to Claude Code via stdio.

Lightweight proxy to the unified memory service at BRAIN_URL (default: http://127.0.0.1:7010).
Runs as stdio transport for Claude Code MCP integration.

Tools:
  brain_capabilities    — runtime capability summary
  brain_store           — save a new memory (corporate/build/personal domain)
  brain_get             — retrieve memory by ID
  brain_list            — list with filters
  brain_search          — semantic similarity search
  brain_update          — update memory (corporate: append-only versioning, build/personal: in-place)
  brain_delete          — delete memory (build/personal only, corporate forbidden)
  brain_get_context     — synthesize grounding context pack
  brain_store_bulk      — batch store records
  brain_upsert_bulk     — idempotent batch upsert
  brain_maintain        — dedup + owner normalization
  brain_export          — controlled transfer export
  brain_sync_check      — memory sync/existence check by ID, match_key, or obsidian_ref
  brain_obsidian_vaults — list local Obsidian vaults
  brain_obsidian_read_note — read a local Obsidian note
  brain_obsidian_sync   — one-way sync from Obsidian into OpenBrain
  brain_obsidian_write_note — write a local Obsidian note
  brain_obsidian_export — export memories to local Obsidian notes
  brain_obsidian_collection — build an Obsidian collection note from memories
  brain_obsidian_bidirectional_sync — sync OpenBrain and Obsidian in both directions
  brain_obsidian_sync_status — inspect bidirectional sync status
  brain_obsidian_update_note — update an existing local Obsidian note
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

from .capabilities_health import build_capabilities_health
from .capabilities_manifest import load_capabilities_manifest
from .capabilities_metadata import load_capabilities_metadata
from .http_error_adapter import backend_error_message, backend_request_failure_message
from .memory_paths import memory_absolute_path, memory_item_absolute_path
from .obsidian_cli import ObsidianCliAdapter, ObsidianCliError, note_to_write_payload
from .request_builders import (
    build_find_list_payload,
    build_find_search_payload,
    build_list_filters,
    build_sync_check_payload,
    canonical_updated_by,
    normalize_optional_text,
    normalize_updated_by,
    validate_store_inputs,
)
from .response_normalizers import (
    normalize_find_hits_to_records,
    normalize_find_hits_to_scored_memories,
)
from .runtime_limits import load_runtime_limits

_gateway_logger = logging.getLogger("mcp_gateway")

BRAIN_URL: str = os.environ.get("BRAIN_URL", "http://localhost:7010")
BACKEND_TIMEOUT_RAW: str = os.environ.get("BACKEND_TIMEOUT_S", "30")
BACKEND_TIMEOUT: float
HEALTH_PROBE_TIMEOUT_RAW: str = os.environ.get("MCP_HEALTH_PROBE_TIMEOUT_S", "5.0")
HEALTH_PROBE_TIMEOUT: float
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "").strip()
OBSIDIAN_LOCAL_TOOLS_ENV = "ENABLE_LOCAL_OBSIDIAN_TOOLS"
MCP_SOURCE_SYSTEM_RAW: str = os.environ.get(
    "MCP_SOURCE_SYSTEM",
    os.environ.get("SOURCE_SYSTEM", "other"),
)
MCP_SOURCE_SYSTEM: str

_MIN_KEY_LEN = 32


def _normalize_brain_url(value: str | None) -> str:
    normalized = (value or "").strip()
    if any(ch.isspace() for ch in normalized):
        raise ValueError("BRAIN_URL must not include whitespace")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("BRAIN_URL must be a valid http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("BRAIN_URL must not include credentials")
    if parsed.path not in {"", "/"}:
        raise ValueError("BRAIN_URL must not include path")
    if parsed.query or parsed.fragment:
        raise ValueError("BRAIN_URL must not include query params or fragment")
    return normalized.rstrip("/")


def _normalize_backend_timeout(value: str | None) -> float:
    try:
        normalized = float((value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("BACKEND_TIMEOUT_S must be a valid float") from exc
    if not math.isfinite(normalized):
        raise ValueError("BACKEND_TIMEOUT_S must be finite")
    if normalized <= 0:
        raise ValueError("BACKEND_TIMEOUT_S must be > 0")
    if normalized > 120:
        raise ValueError("BACKEND_TIMEOUT_S must be <= 120")
    return normalized


def _normalize_health_probe_timeout(value: str | None, backend_timeout: float) -> float:
    try:
        normalized = float((value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be a valid float") from exc
    if not math.isfinite(normalized):
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be finite")
    if normalized <= 0:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be > 0")
    if normalized > 30:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be <= 30")
    if normalized > backend_timeout:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be <= BACKEND_TIMEOUT_S")
    return normalized


def _normalize_source_system(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", normalized):
        raise ValueError("MCP_SOURCE_SYSTEM must match [a-z0-9][a-z0-9_-]{0,31}")
    return normalized


BRAIN_URL = _normalize_brain_url(BRAIN_URL)
BACKEND_TIMEOUT = _normalize_backend_timeout(BACKEND_TIMEOUT_RAW)
HEALTH_PROBE_TIMEOUT = _normalize_health_probe_timeout(
    HEALTH_PROBE_TIMEOUT_RAW,
    BACKEND_TIMEOUT,
)
MCP_SOURCE_SYSTEM = _normalize_source_system(MCP_SOURCE_SYSTEM_RAW)

if INTERNAL_API_KEY and len(INTERNAL_API_KEY) < _MIN_KEY_LEN:
    _gateway_logger.warning(
        "INTERNAL_API_KEY is only %d chars (minimum %d recommended). "
        "Use a longer key in production.",
        len(INTERNAL_API_KEY),
        _MIN_KEY_LEN,
    )
elif not INTERNAL_API_KEY:
    _gateway_logger.warning(
        "INTERNAL_API_KEY is not set. Requests to backend will fail in public mode."
    )

# Parameter validation bounds (PERF-007)
_LIMITS = load_runtime_limits()
MAX_SEARCH_TOP_K: int = _LIMITS["max_search_top_k"]
MAX_LIST_LIMIT: int = _LIMITS["max_list_limit"]
MAX_SYNC_LIMIT: int = _LIMITS["max_sync_limit"]
MAX_BULK_ITEMS: int = _LIMITS["max_bulk_items"]


def _normalize_obsidian_read_concurrency(value: str | None) -> int:
    raw = (value or "").strip()
    if not raw:
        return 8
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError("OBSIDIAN_READ_CONCURRENCY must be an integer") from exc
    if not 1 <= parsed <= 32:
        raise ValueError("OBSIDIAN_READ_CONCURRENCY must be in range 1..32")
    return parsed


MAX_OBSIDIAN_READ_CONCURRENCY = _normalize_obsidian_read_concurrency(
    os.environ.get("OBSIDIAN_READ_CONCURRENCY")
)


def _normalize_obsidian_write_concurrency(value: str | None) -> int:
    raw = (value or "").strip()
    if not raw:
        # Matches .env.example default; bumped from 1 to enable mild parallelism
        # for multi-chunk syncs while staying conservative for the backend.
        return 2
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError("OBSIDIAN_WRITE_CONCURRENCY must be an integer") from exc
    if not 1 <= parsed <= 8:
        raise ValueError("OBSIDIAN_WRITE_CONCURRENCY must be in range 1..8")
    return parsed


MAX_OBSIDIAN_WRITE_CONCURRENCY = _normalize_obsidian_write_concurrency(
    os.environ.get("OBSIDIAN_WRITE_CONCURRENCY")
)
DEFAULT_CORPORATE_OWNER = (
    os.environ.get("OBSIDIAN_CORPORATE_DEFAULT_OWNER", "obsidian-sync").strip()
    or "obsidian-sync"
)
_DATA_URI_RE = re.compile(r"data:[^\s,]+;base64,[A-Za-z0-9+/=\s]+", re.IGNORECASE)

# Known backend error signatures. Best-effort: the backend should expose
# stable `error.code` values long-term so we can drop the string matching.
_OBSIDIAN_OWNER_MARKER = "owner is required for corporate domain"
_OBSIDIAN_EMBED_MARKER = "/api/embed"
_OBSIDIAN_DLP_BLOCK_MARKERS = ("secret_detected", "plaintext secret detected")


def _obsidian_extract_error_detail(response: httpx.Response) -> str:
    """Return a best-effort string description of an error response body."""
    try:
        payload = response.json()
    except Exception:
        return response.text or ""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str):
                return message
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return str(payload)


def _obsidian_extract_status_error(response: httpx.Response) -> str:
    if response.status_code == 429:
        return "rate_limited"
    if response.status_code == 422:
        return "validation_error"
    return f"http_{response.status_code}"


def _obsidian_classify_error(
    detail_lowered: str, status_code: int | None = None
) -> str:
    """Classify a backend error into a known remediation kind."""
    if any(marker in detail_lowered for marker in _OBSIDIAN_DLP_BLOCK_MARKERS):
        return "secret_detected"
    if _OBSIDIAN_OWNER_MARKER in detail_lowered:
        return "owner_required_corporate"
    if _OBSIDIAN_EMBED_MARKER in detail_lowered and (
        status_code is None or status_code == 400 or "400 bad request" in detail_lowered
    ):
        return "embed_400"
    return "other"


def _clean_content_for_embedding(text: str, limit: int) -> str:
    cleaned = _DATA_URI_RE.sub("[removed-data-uri]", text or "")
    return cleaned[:limit]


class _ObsidianSyncRunner:
    """Encapsulates state and remediation logic for brain_obsidian_sync.

    Pulled out of the tool function so helpers are testable and not rebuilt
    on every call. Holds mutable aggregates (summary, stats, results) so
    callers can read them after `run` completes.
    """

    _RETRY_ATTEMPTS = 5
    _EMBED_CONTENT_LIMITS = (4000, 1500)

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self.summary_totals: dict[str, int] = {}
        self.aggregated_results: list[dict[str, Any]] = []
        self.sync_stats: dict[str, int] = {
            "note_read_failed": 0,
            "write_retry_429": 0,
            "write_fallback_422_batches": 0,
            "write_nonrecoverable_batches": 0,
            "owner_autofix_retries": 0,
            "embed_retry_reduced_content": 0,
            "secret_quarantined": 0,
        }

    # --- bookkeeping -------------------------------------------------------

    def init_summary(self, received: int) -> None:
        self.summary_totals = {"received": received, "failed": 0}

    def accumulate_summary(self, summary: dict[str, Any]) -> None:
        for key, value in summary.items():
            if key == "received":
                continue
            if isinstance(value, int):
                self.summary_totals[key] = self.summary_totals.get(key, 0) + value

    def append_result_items(
        self, items: list[dict[str, Any]], input_index_map: list[int]
    ) -> None:
        for item in items:
            normalized = dict(item)
            idx = normalized.get("input_index")
            if isinstance(idx, int) and 0 <= idx < len(input_index_map):
                normalized["input_index"] = input_index_map[idx]
            self.aggregated_results.append(normalized)

    def record_note_read_failure(self, input_index: int) -> None:
        self.summary_totals["failed"] = self.summary_totals.get("failed", 0) + 1
        self.sync_stats["note_read_failed"] += 1
        self.aggregated_results.append(
            {
                "input_index": input_index,
                "status": "failed",
                "errors": ["note_read_failed"],
                "warnings": [],
            }
        )

    def record_skipped(self, input_index: int, warning: str) -> None:
        self.accumulate_summary({"skipped": 1})
        self.aggregated_results.append(
            {
                "input_index": input_index,
                "status": "skipped",
                "errors": [],
                "warnings": [warning],
            }
        )

    def record_failed(self, input_index: int, error: str) -> None:
        self.aggregated_results.append(
            {
                "input_index": input_index,
                "status": "failed",
                "errors": [error],
                "warnings": [],
            }
        )

    # --- HTTP --------------------------------------------------------------

    async def post_write_many(
        self, batch_records: list[dict[str, Any]]
    ) -> httpx.Response:
        """POST /write_many with exponential backoff + jitter on 429."""
        payload = {"records": batch_records, "write_mode": "upsert"}
        response: httpx.Response | None = None
        for attempt in range(self._RETRY_ATTEMPTS):
            response = await _request_or_raise(
                self._client,
                "POST",
                memory_absolute_path("write_many"),
                json=payload,
                allow_statuses={400, 422, 429},
            )
            if response.status_code != 429:
                return response
            self.sync_stats["write_retry_429"] += 1
            # Exp backoff with jitter: 0.25s, 0.5s, 1s, 2s, 4s ± 25%
            base = 0.25 * (2**attempt)
            await asyncio.sleep(base * (1.0 + random.uniform(-0.25, 0.25)))
        assert response is not None  # _RETRY_ATTEMPTS >= 1
        return response

    # --- remediation -------------------------------------------------------

    async def apply_remediation(
        self,
        record: dict[str, Any],
        input_index: int,
        kind: str,
        *,
        allow_owner_fix: bool = True,
    ) -> bool:
        """Try a known recovery path. Returns True if handled (success or quarantined)."""
        if kind == "secret_detected":
            self.sync_stats["secret_quarantined"] += 1
            self.record_skipped(input_index, "secret_quarantined")
            return True

        if kind == "embed_400":
            content = str(record.get("content", ""))
            for limit in self._EMBED_CONTENT_LIMITS:
                reduced = dict(record)
                reduced["content"] = _clean_content_for_embedding(content, limit)
                self.sync_stats["embed_retry_reduced_content"] += 1
                resp = await self.post_write_many([reduced])
                if resp.status_code == 200:
                    data = resp.json()
                    self.accumulate_summary(data.get("summary", {}))
                    self.append_result_items(data.get("results", []), [input_index])
                    return True
            # All attempts exhausted: quarantine.
            self.record_skipped(input_index, "embed_quarantined")
            return True

        if kind == "owner_required_corporate" and allow_owner_fix:
            fixed = dict(record)
            fixed["owner"] = DEFAULT_CORPORATE_OWNER
            self.sync_stats["owner_autofix_retries"] += 1
            resp = await self.post_write_many([fixed])
            if resp.status_code == 200:
                data = resp.json()
                self.accumulate_summary(data.get("summary", {}))
                self.append_result_items(data.get("results", []), [input_index])
                return True
            # Owner fix didn't resolve; reclassify and try next-layer remediation
            # without recursing back into another owner fix.
            new_detail = _obsidian_extract_error_detail(resp).lower()
            new_kind = _obsidian_classify_error(new_detail, resp.status_code)
            if new_kind != "other":
                _gateway_logger.debug(
                    "Owner fix failed, applying secondary remediation for kind=%s",
                    new_kind,
                )
                return await self.apply_remediation(
                    fixed, input_index, new_kind, allow_owner_fix=False
                )
            return False

        return False

    # --- chunk processing --------------------------------------------------

    async def process_chunk(
        self,
        batch_records: list[dict[str, Any]],
        batch_input_indices: list[int],
    ) -> None:
        response = await self.post_write_many(batch_records)

        if response.status_code == 200:
            await self._handle_200_response(
                response, batch_records, batch_input_indices
            )
            return

        # Batch validation failure: salvage record-by-record.
        if response.status_code == 422 and len(batch_records) > 1:
            self.sync_stats["write_fallback_422_batches"] += 1
            for local_index, record in enumerate(batch_records):
                original_idx = batch_input_indices[local_index]
                single_response = await self.post_write_many([record])
                if single_response.status_code == 200:
                    data = single_response.json()
                    self.accumulate_summary(data.get("summary", {}))
                    self.append_result_items(data.get("results", []), [original_idx])
                    continue
                if await self._remediate_from_response(
                    record, original_idx, single_response
                ):
                    continue
                self.accumulate_summary({"errors": 1})
                self.record_failed(
                    original_idx, _obsidian_extract_status_error(single_response)
                )
            return

        # Non-recoverable for the whole chunk; try remediation per record.
        self.sync_stats["write_nonrecoverable_batches"] += 1
        self.accumulate_summary({"errors": len(batch_records)})
        err = _obsidian_extract_status_error(response)
        for local_index, original_idx in enumerate(batch_input_indices):
            if await self._remediate_from_response(
                batch_records[local_index], original_idx, response
            ):
                continue
            self.record_failed(original_idx, err)

    async def _remediate_from_response(
        self,
        record: dict[str, Any],
        input_index: int,
        response: httpx.Response,
    ) -> bool:
        detail = _obsidian_extract_error_detail(response).lower()
        kind = _obsidian_classify_error(detail, response.status_code)
        if kind == "other":
            return False
        return await self.apply_remediation(record, input_index, kind)

    async def _handle_200_response(
        self,
        response: httpx.Response,
        batch_records: list[dict[str, Any]],
        batch_input_indices: list[int],
    ) -> None:
        """Backend may return 200 with per-item `status: failed`. For single-record
        chunks, try remediation on the failed item before accepting the failure.

        Prefers the backend's structured `error_code` field when present;
        falls back to substring classification on `error` for older backends.
        """
        result = response.json()
        items = result.get("results", [])
        if (
            len(batch_records) == 1
            and len(items) == 1
            and isinstance(items[0], dict)
            and items[0].get("status") == "failed"
        ):
            item = items[0]
            kind = item.get("error_code") or _obsidian_classify_error(
                str(item.get("error", "")).lower()
            )
            if kind and kind != "other":
                if await self.apply_remediation(
                    batch_records[0], batch_input_indices[0], kind
                ):
                    return
            # Fall through to accept the per-item failure as-is.

        self.accumulate_summary(result.get("summary", {}))
        self.append_result_items(items, batch_input_indices)

    def merge_sync_stats(self) -> None:
        """Fold internal counters into the final summary."""
        self.accumulate_summary(self.sync_stats)


_CAPS = load_capabilities_manifest()
_CAP_META = load_capabilities_metadata()
CORE_TOOLS = _CAPS["core_tools"]
ADVANCED_TOOLS = _CAPS["advanced_tools"]
ADMIN_TOOLS = _CAPS["admin_tools"]
OBSIDIAN_LOCAL_TOOLS = _CAPS["local_obsidian_tools"]

mcp = FastMCP(
    name="OpenBrain",
    instructions=(
        "OpenBrain is your unified knowledge base — one brain for all domains.\n"
        "Use domain='corporate' for professional work decisions, policies, and meeting notes.\n"
        "Use domain='build' for technical code, side projects, and architecture.\n"
        "Use domain='personal' for personal notes, goals, ideas.\n\n"
        "Corporate memories are append-only (versioned, audited, cannot be deleted).\n"
        "Build/personal memories are mutable and deletable.\n\n"
        "Always tag memories with relevant domain + area tags.\n"
        "Use brain_search to find relevant context across all domains."
    ),
)


class BrainMemory(BaseModel):
    id: str
    tenant_id: str | None = None
    domain: str
    entity_type: str
    title: str | None = None
    summary: str | None = None
    content: str
    owner: str = ""
    status: str
    version: int
    sensitivity: str
    superseded_by: str | None = None
    tags: list[str] = []
    relations: dict[str, Any] = {}
    obsidian_ref: str | None = None
    custom_fields: dict[str, Any] = {}
    content_hash: str = ""
    match_key: str | None = None
    previous_id: str | None = None
    root_id: str | None = None
    valid_from: str | None = None
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str | None = None
    source: dict[str, Any] | None = None
    governance: dict[str, Any] | None = None


_http_client: httpx.AsyncClient | None = None
_http_client_config_key: tuple[str, float, str] | None = None


def _current_http_client_config_key() -> tuple[str, float, str]:
    return (BRAIN_URL, BACKEND_TIMEOUT, INTERNAL_API_KEY)


class _SharedClient:
    """Context-manager wrapper that lazily creates and reuses a single AsyncClient.

    All 'async with _client() as c:' call sites work unchanged while the underlying
    client (and its connection pool) is shared across requests.
    """

    async def __aenter__(self) -> httpx.AsyncClient:
        global _http_client, _http_client_config_key
        current_key = _current_http_client_config_key()
        if _http_client is not None and _http_client_config_key != current_key:
            old_key = _http_client_config_key
            try:
                await _http_client.aclose()
            except Exception as exc:  # pragma: no cover - defensive logging path
                _gateway_logger.warning(
                    "mcp_client_close_failed", extra={"error": str(exc)}
                )
            _gateway_logger.info(
                "mcp_client_refreshed_due_to_config_drift",
                extra={
                    "old_base_url": (old_key[0] if old_key else None),
                    "new_base_url": current_key[0],
                },
            )
            _http_client = None
            _http_client_config_key = None

        if _http_client is None:
            headers: dict[str, str] = {}
            if INTERNAL_API_KEY:
                headers["X-Internal-Key"] = INTERNAL_API_KEY
            _http_client = httpx.AsyncClient(
                base_url=BRAIN_URL,
                timeout=BACKEND_TIMEOUT,
                headers=headers,
            )
            _http_client_config_key = current_key
        return _http_client

    async def __aexit__(self, *_: object) -> None:
        pass  # Keep client alive for connection-pool reuse


def _client() -> _SharedClient:
    return _SharedClient()


def _raise(r: httpx.Response) -> None:
    if r.is_error:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise ValueError(backend_error_message(r.status_code, detail))


async def _request_or_raise(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    allow_statuses: set[int] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    try:
        # Prefer verb-specific methods first to preserve existing test/mocking
        # patterns, then fall back to generic request().
        method_fn = getattr(client, method.lower(), None)
        if callable(method_fn):
            response = await method_fn(path, **kwargs)
        else:
            request_fn = getattr(client, "request", None)
            if not callable(request_fn):
                raise ValueError(f"Client does not support method {method}")
            response = await request_fn(method, path, **kwargs)
    except httpx.RequestError as exc:
        raise ValueError(backend_request_failure_message(exc)) from exc

    if response.is_error and (
        allow_statuses is None or response.status_code not in allow_statuses
    ):
        _raise(response)
    return response


def _obsidian_local_tools_enabled() -> bool:
    return os.environ.get(OBSIDIAN_LOCAL_TOOLS_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _local_obsidian_tools_registered() -> bool:
    return all(
        callable(globals().get(f"brain_{tool}")) for tool in OBSIDIAN_LOCAL_TOOLS
    )


def _obsidian_local_tools_disabled_reason() -> str:
    return (
        "Local Obsidian tools are disabled by default. "
        f"Set {OBSIDIAN_LOCAL_TOOLS_ENV}=1 only on a trusted local stdio gateway."
    )


def _require_obsidian_local_tools_enabled() -> None:
    if _obsidian_local_tools_enabled():
        return
    raise ValueError(_obsidian_local_tools_disabled_reason())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def _get_backend_status() -> dict:
    """Probe backend readiness without conflating degradation with outage."""
    readyz_paths = ("/readyz", "/api/v1/readyz")
    readyz_failures: list[str] = []
    for readyz_path in readyz_paths:
        try:
            async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT) as client:
                r = await client.get(f"{BRAIN_URL}{readyz_path}")
            data = r.json()
            if r.status_code in {200, 503} and isinstance(data, dict):
                return {
                    "status": data.get(
                        "status",
                        "ok" if r.status_code == 200 else "degraded",
                    ),
                    "url": BRAIN_URL,
                    "api": "reachable",
                    "db": data.get("db", "unknown"),
                    "vector_store": data.get("vector_store", "unknown"),
                    "readyz_status_code": r.status_code,
                    "probe": "readyz",
                    "primary_path": readyz_path,
                }
            readyz_failures.append(
                f"{readyz_path}: Unexpected response ({r.status_code})"
            )
        except Exception as exc:
            readyz_failures.append(f"{readyz_path}: {exc}")
    readyz_error = "; ".join(readyz_failures)

    try:
        async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT) as client:
            r = await client.get(f"{BRAIN_URL}/healthz")
        if r.status_code == 200:
            return {
                "status": "degraded",
                "url": BRAIN_URL,
                "api": "reachable",
                "db": "unknown",
                "vector_store": "unknown",
                "probe": "healthz_fallback",
                "reason": f"/readyz probe failed: {readyz_error}",
            }
        healthz_error = f"Unexpected /healthz response ({r.status_code})"
    except Exception as exc:
        healthz_error = str(exc)

    try:
        async with _client() as c:
            r = await c.request("GET", "/api/v1/health", timeout=HEALTH_PROBE_TIMEOUT)
        if r.status_code == 200:
            return {
                "status": "degraded",
                "url": BRAIN_URL,
                "api": "reachable",
                "db": "unknown",
                "vector_store": "unknown",
                "probe": "api_health_fallback",
                "reason": (
                    f"/readyz probe failed: {readyz_error}; "
                    f"/healthz probe failed: {healthz_error}"
                ),
            }
        api_health_error = f"Unexpected /api/v1/health response ({r.status_code})"
    except Exception as exc:
        api_health_error = str(exc)

    return {
        "status": "unavailable",
        "url": BRAIN_URL,
        "api": "unreachable",
        "db": "unknown",
        "vector_store": "unknown",
        "probe": "api_health_fallback",
        "reason": (
            f"/readyz probe failed: {readyz_error}; "
            f"/healthz probe failed: {healthz_error}; "
            f"/api/v1/health probe failed: {api_health_error}"
        ),
    }


@mcp.tool()
async def brain_capabilities() -> dict:
    """Check the operational status of the Memory Platform V1."""
    obsidian_enabled = (
        _obsidian_local_tools_enabled() and _local_obsidian_tools_registered()
    )
    backend = await _get_backend_status()
    tier_2_tools = [*ADVANCED_TOOLS]
    obsidian_tools = [*OBSIDIAN_LOCAL_TOOLS] if obsidian_enabled else []
    obsidian_status = "enabled" if obsidian_enabled else "disabled"
    obsidian_reason = (
        None if obsidian_enabled else _obsidian_local_tools_disabled_reason()
    )
    if obsidian_tools:
        tier_2_tools.extend(obsidian_tools)
    health = build_capabilities_health(backend, obsidian_status)

    return {
        "platform": "OpenBrain V1 (Gateway)",
        "api_version": _CAP_META["api_version"],
        "schema_changelog": _CAP_META["schema_changelog"],
        "backend": backend,
        "health": health,
        "obsidian": {
            "mode": "local",
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
        "obsidian_local": {
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
        "tier_1_core": {
            "status": "stable",
            "tools": CORE_TOOLS,
        },
        "tier_2_advanced": {
            "status": "active",
            "tools": tier_2_tools,
        },
        "tier_3_admin": {
            "status": "guarded",
            "tools": ADMIN_TOOLS,
        },
    }


@mcp.tool()
async def brain_store(
    content: str,
    domain: Literal["corporate", "build", "personal"] = "corporate",
    entity_type: str = "Decision",
    title: str | None = None,
    sensitivity: str = "internal",
    owner: str = "",
    tenant_id: str | None = None,
    tags: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    obsidian_ref: str | None = None,
    match_key: str | None = None,
) -> BrainMemory:
    """
    Save a new memory to OpenBrain.

    domain:
      - corporate: professional work. Append-only, audited.
      - build: technical/side projects. Mutable.
      - personal: personal notes, goals. Mutable.

    entity_type examples:
      Corporate: Decision | Policy | Risk | MeetingNote | Vendor | Service | Architecture
      Build: Project | CodeSnippet | Bug | Feature | Idea
      Personal: Note | Book | Music | Recipe | Travel | Goal

    tags — add at least one domain tag + area tag:
      ["engineering", "auth"], ["project-x", "frontend"], ["personal", "reading"]

    match_key — optional idempotency key for bulk sync (prevents duplicates).
    obsidian_ref — path to source note in Obsidian vault.
    """
    owner_normalized = normalize_optional_text(owner) or ""
    match_key_normalized = normalize_optional_text(match_key)
    validate_store_inputs(
        domain=domain,
        owner=owner_normalized,
        match_key=match_key_normalized,
    )

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("write"),
            json={
                "record": {
                    "content": content,
                    "domain": domain,
                    "entity_type": entity_type,
                    "title": title,
                    "sensitivity": sensitivity,
                    "owner": owner_normalized,
                    "tenant_id": tenant_id,
                    "tags": tags or [],
                    "custom_fields": custom_fields or {},
                    "obsidian_ref": obsidian_ref,
                    "match_key": match_key_normalized,
                    "source": {"type": "agent", "system": MCP_SOURCE_SYSTEM},
                },
                "write_mode": "upsert",
            },
        )
        return BrainMemory(**r.json()["record"])


@mcp.tool()
async def brain_get(memory_id: str) -> BrainMemory:
    """Retrieve a specific memory by its ID."""
    async with _client() as c:
        r = await _request_or_raise(
            c, "GET", memory_item_absolute_path(memory_id), allow_statuses={404}
        )
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_list(
    domain: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    sensitivity: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    include_test_data: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """
    Browse memories with metadata filters.

    status options: active | superseded (default: active only)
    domain options: corporate | build | personal
    include_test_data: include records marked with metadata.test_data=true
    offset: Number of results to skip for pagination
    """
    if not isinstance(include_test_data, bool):
        raise ValueError(
            f"include_test_data must be bool, got {type(include_test_data).__name__}"
        )
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise ValueError(f"limit must be 1–{MAX_LIST_LIMIT}, got {limit}")
    if not 0 <= offset <= 10_000:
        raise ValueError(f"offset must be 0–10000, got {offset}")
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        status=status,
        sensitivity=sensitivity,
        owner=owner,
        tenant_id=tenant_id,
        include_test_data=include_test_data,
    )
    payload = build_find_list_payload(limit=limit, filters=filters, offset=offset)

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("find"),
            json=payload,
        )
        return normalize_find_hits_to_records(r.json())


@mcp.tool()
async def brain_get_context(query: str, domain: str | None = None) -> dict:
    """Synthesize a grounding pack for the current conversation topic."""
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("get_context"),
            json={"query": query, "domain": domain, "max_items": 10},
        )
        return r.json()


@mcp.tool()
async def brain_search(
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    entity_type: str | None = None,
    owner: str | None = None,
    sensitivity: str | None = None,
    include_test_data: bool = False,
    offset: int = 0,
) -> list[dict]:
    """
    Semantic search across the unified knowledge base.
    Returns top-k memories most relevant to the query.
    Optionally filter by domain (corporate|build|personal), entity_type, owner, sensitivity.
    include_test_data: include records marked with metadata.test_data=true
    offset: Number of results to skip for pagination
    """
    if not isinstance(include_test_data, bool):
        raise ValueError(
            f"include_test_data must be bool, got {type(include_test_data).__name__}"
        )
    if not 1 <= top_k <= MAX_SEARCH_TOP_K:
        raise ValueError(f"top_k must be 1–{MAX_SEARCH_TOP_K}, got {top_k}")
    if not 0 <= offset <= 10_000:
        raise ValueError(f"offset must be 0–10000, got {offset}")
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        owner=owner,
        sensitivity=sensitivity,
        include_test_data=include_test_data,
    )
    payload = build_find_search_payload(
        query=query, limit=top_k, filters=filters, offset=offset
    )

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("find"),
            json=payload,
        )
        return normalize_find_hits_to_scored_memories(r.json())


@mcp.tool()
async def brain_update(
    memory_id: str,
    content: str,
    updated_by: str = "agent",
    title: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    tags: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    obsidian_ref: str | None = None,
    sensitivity: str | None = None,
) -> BrainMemory:
    """
    Update a memory by ID.
    - Corporate: creates new version (append-only). Old version marked as superseded.
    - Build/Personal: updates in place.
    - `updated_by` is compatibility-only and not authoritative for audit identity.
    """
    _ = normalize_updated_by(updated_by)
    # Build patch payload — only include fields explicitly provided
    payload: dict[str, Any] = {
        "content": content,
        "updated_by": canonical_updated_by(),
    }
    if title is not None:
        payload["title"] = title
    if sensitivity is not None:
        payload["sensitivity"] = sensitivity
    if owner is not None:
        payload["owner"] = owner
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if tags is not None:
        payload["tags"] = tags
    if custom_fields is not None:
        payload["custom_fields"] = custom_fields
    if obsidian_ref is not None:
        payload["obsidian_ref"] = obsidian_ref

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "PATCH",
            memory_item_absolute_path(memory_id),
            allow_statuses={404},
            json=payload,
        )
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_delete(memory_id: str) -> dict:
    """
    Delete a memory. Only allowed for build/personal domains.
    Corporate memories cannot be deleted (returns 403).
    """
    async with _client() as c:
        r = await _request_or_raise(
            c, "DELETE", memory_item_absolute_path(memory_id), allow_statuses={403, 404}
        )
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        if r.status_code == 403:
            raise ValueError(
                "Cannot delete corporate memories. Use deprecation instead."
            )
        return {"deleted": True, "id": memory_id}


@mcp.tool()
async def brain_maintain(
    dry_run: bool = True,
    dedup_threshold: float = 0.05,
    normalize_owners: dict[str, str] | None = None,
    fix_superseded_links: bool = True,
) -> dict:
    """
    Bulk maintenance: dedup, owner normalization, superseded_by repair.
    Always run with dry_run=True first to preview changes.
    """
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("maintain"),
            json={
                "dry_run": dry_run,
                "dedup_threshold": dedup_threshold,
                "normalize_owners": normalize_owners or {},
                "retype_rules": [],
                "fix_superseded_links": fix_superseded_links,
            },
        )
        return r.json()


@mcp.tool()
async def brain_test_data_report(sample_limit: int = 20) -> dict[str, Any]:
    """Return admin diagnostic report for hidden test-data records."""
    if not 1 <= sample_limit <= 100:
        raise ValueError(f"sample_limit must be 1–100, got {sample_limit}")
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "GET",
            memory_absolute_path("test_data_report"),
            params={"sample_limit": sample_limit},
        )
        return r.json()


@mcp.tool()
async def brain_cleanup_build_test_data(
    dry_run: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Controlled cleanup for build-domain test-data records."""
    if not 1 <= limit <= 500:
        raise ValueError(f"limit must be 1–500, got {limit}")
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("cleanup_build_test_data"),
            json={"dry_run": dry_run, "limit": limit},
        )
        return r.json()


@mcp.tool()
async def brain_export(ids: list[str]) -> list[dict]:
    """
    Export memories for review or transfer.
    Restricted-sensitivity content is redacted automatically.
    """
    async with _client() as c:
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("export"), json={"ids": ids}
        )
        return r.json()


@mcp.tool()
async def brain_sync_check(
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict:
    """
    Check whether a memory exists or is up to date.
    Provide exactly one of memory_id, match_key, or obsidian_ref.
    If file_hash is omitted, returns existence status only.
    """
    payload = build_sync_check_payload(
        memory_id=memory_id,
        match_key=match_key,
        obsidian_ref=obsidian_ref,
        file_hash=file_hash,
    )
    async with _client() as c:
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("sync_check"), json=payload
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_vaults() -> list[str]:
    """List local Obsidian vaults available to the backend."""
    _require_obsidian_local_tools_enabled()
    adapter = ObsidianCliAdapter()
    try:
        return await adapter.list_vaults()
    except ObsidianCliError as e:
        raise ValueError(str(e))


@mcp.tool()
async def brain_obsidian_read_note(path: str, vault: str = "Documents") -> dict:
    """Read a note from a local Obsidian vault with parsed frontmatter and tags."""
    _require_obsidian_local_tools_enabled()
    adapter = ObsidianCliAdapter()
    try:
        note = await adapter.read_note(vault, path)
    except ObsidianCliError as e:
        raise ValueError(str(e))
    return {
        "vault": note.vault,
        "path": note.path,
        "title": note.title,
        "content": note.content,
        "frontmatter": note.frontmatter,
        "tags": note.tags,
        "file_hash": note.file_hash,
    }


@mcp.tool()
async def brain_obsidian_sync(
    vault: str = "Documents",
    paths: list[str] | None = None,
    folder: str | None = None,
    limit: int = 50,
    domain: Literal["corporate", "build", "personal"] = "build",
    entity_type: str = "Architecture",
    owner: str = "",
    tags: list[str] | None = None,
) -> dict:
    """
    One-way sync from an Obsidian vault into OpenBrain using deterministic match keys.
    Use paths for explicit notes or folder for a bounded folder sync.
    """
    if not 1 <= limit <= MAX_SYNC_LIMIT:
        raise ValueError(f"limit must be 1–{MAX_SYNC_LIMIT}, got {limit}")
    _require_obsidian_local_tools_enabled()
    adapter = ObsidianCliAdapter()
    try:
        resolved_paths = (
            (paths or [])[:limit]
            if paths
            else await adapter.list_files(vault, folder=folder, limit=limit)
        )
        read_concurrency = min(
            MAX_OBSIDIAN_READ_CONCURRENCY, max(1, len(resolved_paths))
        )
        read_semaphore = asyncio.Semaphore(read_concurrency)

        async def _read_note_guarded(note_path: str) -> Any:
            async with read_semaphore:
                return await adapter.read_note(vault, note_path)

        note_results = await asyncio.gather(
            *(_read_note_guarded(path) for path in resolved_paths),
            return_exceptions=True,
        )
    except ObsidianCliError as e:
        raise ValueError(str(e))

    async with _client() as c:
        runner = _ObsidianSyncRunner(c)
        runner.init_summary(len(resolved_paths))

        records: list[dict[str, Any]] = []
        record_input_indices: list[int] = []
        for input_index, note_result in enumerate(note_results):
            if isinstance(note_result, Exception):
                runner.record_note_read_failure(input_index)
                continue
            records.append(
                note_to_write_payload(
                    note_result,
                    default_domain=domain,
                    default_entity_type=entity_type,
                    default_owner=owner,
                    default_tags=tags or [],
                )
            )
            record_input_indices.append(input_index)

        chunk_specs: list[tuple[list[dict[str, Any]], list[int]]] = []
        for start in range(0, len(records), MAX_BULK_ITEMS):
            chunk_specs.append(
                (
                    records[start : start + MAX_BULK_ITEMS],
                    record_input_indices[start : start + MAX_BULK_ITEMS],
                )
            )

        if MAX_OBSIDIAN_WRITE_CONCURRENCY <= 1 or len(chunk_specs) <= 1:
            for batch_records, batch_input_indices in chunk_specs:
                await runner.process_chunk(batch_records, batch_input_indices)
        else:
            write_semaphore = asyncio.Semaphore(MAX_OBSIDIAN_WRITE_CONCURRENCY)

            async def _run_chunk_guarded(
                batch_records: list[dict[str, Any]],
                batch_input_indices: list[int],
            ) -> None:
                async with write_semaphore:
                    await runner.process_chunk(batch_records, batch_input_indices)

            await asyncio.gather(
                *(
                    _run_chunk_guarded(batch_records, batch_input_indices)
                    for batch_records, batch_input_indices in chunk_specs
                )
            )

        runner.merge_sync_stats()

    return {
        "vault": vault,
        "resolved_paths": resolved_paths,
        "scanned": len(resolved_paths),
        "summary": runner.summary_totals,
        "results": runner.aggregated_results,
    }


@mcp.tool()
async def brain_obsidian_write_note(
    vault: str,
    path: str,
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
    frontmatter: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Write a note to Obsidian vault.

    Args:
        vault: Target vault name
        path: Note path (e.g., "Projects/Note.md")
        content: Markdown content
        title: Optional title (added as H1 if provided)
        tags: Optional tags for frontmatter
        frontmatter: Optional additional frontmatter fields
        overwrite: Overwrite existing note
    """
    _require_obsidian_local_tools_enabled()

    # Build full content with title
    full_content = content
    if title:
        full_content = f"# {title}\n\n{content}"

    # Merge frontmatter
    fm = frontmatter or {}
    if tags:
        fm["tags"] = tags
    if title:
        fm["title"] = title

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/write-note",
            json={
                "vault": vault,
                "path": path,
                "content": full_content,
                "frontmatter": fm,
                "overwrite": overwrite,
            },
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_export(
    vault: str,
    folder: str = "OpenBrain Export",
    memory_ids: list[str] | None = None,
    query: str | None = None,
    domain: str | None = None,
    max_items: int = 50,
) -> dict:
    """
    Export memories from OpenBrain to Obsidian notes.

    Args:
        vault: Target vault
        folder: Target folder in vault
        memory_ids: Specific memory IDs to export
        query: Search query to find memories
        domain: Filter by domain (corporate/build/personal)
        max_items: Maximum number of memories to export
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/export",
            json={
                "vault": vault,
                "folder": folder,
                "memory_ids": memory_ids,
                "query": query,
                "domain": domain,
                "max_items": max_items,
            },
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_collection(
    query: str,
    collection_name: str,
    vault: str = "Documents",
    folder: str = "Collections",
    domain: str | None = None,
    max_items: int = 50,
    group_by: str | None = None,
) -> dict:
    """
    Create a collection (index note) from OpenBrain memories.

    Creates a single index note with links to exported memory notes.

    Args:
        query: Search query
        collection_name: Name for the collection
        vault: Target vault
        folder: Target folder
        domain: Filter by domain
        max_items: Maximum memories
        group_by: How to group (entity_type, owner, tags)
    """
    if not 1 <= max_items <= MAX_SYNC_LIMIT:
        raise ValueError(f"max_items must be 1–{MAX_SYNC_LIMIT}, got {max_items}")
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/collection",
            json={
                "query": query,
                "collection_name": collection_name,
                "vault": vault,
                "folder": folder,
                "domain": domain,
                "max_items": max_items,
                "group_by": group_by,
            },
        )
        return r.json()


@mcp.tool()
async def brain_store_bulk(items: list[dict[str, Any]]) -> dict:
    """Bulk store memories. Use for archiving or synchronization."""
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("write_many"),
            json={"records": items, "write_mode": "upsert"},
        )
        return r.json()


@mcp.tool()
async def brain_upsert_bulk(items: list[dict[str, Any]]) -> dict:
    """Idempotent bulk synchronization using match_key."""
    async with _client() as c:
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("bulk_upsert"), json=items
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_bidirectional_sync(
    vault: str = "Memory",
    strategy: str = "domain_based",
    dry_run: bool = False,
) -> dict:
    """
    Bidirectional sync between OpenBrain and Obsidian.

    Detects and resolves changes in both systems.

    Args:
        vault: Target vault name
        strategy: Conflict resolution strategy (last_write_wins, domain_based, manual_review)
        dry_run: If True, only detect changes without applying

    Returns:
        Sync result with detected changes, conflicts, and applied updates.
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/bidirectional-sync",
            json={
                "vault": vault,
                "strategy": strategy,
                "dry_run": dry_run,
            },
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_sync_status() -> dict:
    """
    Get bidirectional sync status.

    Returns statistics about tracked items and sync state.
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(c, "GET", "/api/v1/obsidian/sync-status")
        return r.json()


@mcp.tool()
async def brain_obsidian_update_note(
    vault: str,
    path: str,
    content: str | None = None,
    append: bool = False,
    tags: list[str] | None = None,
) -> dict:
    """
    Update an existing note in Obsidian.

    Args:
        vault: Target vault name
        path: Note path
        content: New content (or content to append if append=True)
        append: If True, append to existing content
        tags: Tags to update in frontmatter
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/update-note",
            json={
                "vault": vault,
                "path": path,
                "content": content,
                "append": append,
                "tags": tags,
            },
        )
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
