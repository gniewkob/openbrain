# Governance Layer: OpenBrain Unified

## Purpose

OpenBrain is no longer just a memory CRUD service. It is an operational memory system with versioning, bulk ingestion, deduplication, and semantic retrieval. That means the system needs explicit governance rules or it will accumulate conflicting truths, duplicate records, and low-trust retrieval results.

This document defines the minimum governance layer required to run OpenBrain safely in production.

## Operating Principles

- Retrieval must prefer current truth, not historical exhaust.
- Versioning is allowed only when the history itself has value.
- Duplicate creation is tolerated at ingest time only if cleanup is bounded and observable.
- Admin tools are controlled operations, not ad hoc fixes.
- Every ingestion path must have an owner and a cleanup policy.

## Domain Policy

### `corporate`

- Default write model: append-only versioning.
- Rationale: auditability, traceability, and non-repudiation.
- Allowed operations:
  - `store`
  - `update` as version append
  - `search`
  - `get`
  - `get_context`
  - `export`
- Forbidden by policy:
  - direct delete
  - in-place overwrite
- Required metadata:
  - `owner`
  - stable `entity_type`
  - domain-relevant tags
  - `match_key` for records that are expected to be synchronized or repeatedly updated

### `build`

- Default write model: mutable in place.
- Rationale: project notes, architecture records, and technical state often evolve without requiring an audit trail for every edit.
- Use append-only only for:
  - architecture decisions
  - incident reports
  - release approvals
  - security-significant records
- Required metadata:
  - `owner`
  - `match_key` for synchronized or pipeline-managed records

### `personal`

- Default write model: mutable in place.
- Rationale: low-governance notes where truth is personal and change is expected.
- Required metadata:
  - lightweight tags
  - optional `match_key`

## Write Policy

### Single-record writes

- Use `store` for first write.
- Use `update` only when the caller knows the record identity and intends to preserve continuity.
- Do not rely on free-text similarity to determine whether a new record should supersede an existing one.

### Bulk writes

- `store_bulk` is for ingestion of net-new records.
- `upsert_bulk` is for deterministic pipelines only.
- `upsert_bulk` callers must provide stable `match_key` values.
- If `match_key` is missing, the write is ingestion, not upsert.

### Versioning policy

Version append is required when at least one of these is true:

- the record is in `corporate`
- the record represents a decision, policy, risk, approval, or signed state
- the previous version must remain retrievable for audit

In-place mutation is preferred when all of these are true:

- the record is in `build` or `personal`
- the current version is the only version that matters operationally
- historical edits are not required for audit or governance

## Dedup Policy

OpenBrain currently allows duplicates to enter the system and relies on `maintain` to identify them. That is acceptable only with explicit policy.

### Duplicate classes

- Exact duplicate:
  - same `content_hash`
  - same `entity_type`
  - remediation path:
    - mutable domains (`build`, `personal`): superseded by canonical record.
    - append-only domains (`corporate`): marked as `status="duplicate"` with `duplicate_of` metadata. This is a governance-safe remediation that preserves audit trail without violating append-only constraints.
- Pipeline duplicate:
  - same `match_key`
  - more than one active record
- Semantic near-duplicate:
  - similar content, different wording, same operational meaning

### Required response

- Exact duplicates: safe to collapse automatically after dry-run review. Append-only records are remediated logically via `duplicate` status.
- Pipeline duplicates: treat as contract failure in the upstream ingestion path.
- Semantic near-duplicates: do not auto-collapse without human review.

### Maintenance cadence

- Daily:
  - run `maintain` in `dry_run=true`
  - inspect counts and top duplicate classes
- Weekly:
  - execute approved dedup actions
  - normalize owners
  - repair broken supersession links
- Monthly:
  - review whether ingestion pipelines are creating recurring duplicate classes

## Sync Policy

`sync_check` is an integrity helper, not the source of truth. It should be used to validate whether an indexed record exists and whether a provided hash matches the active copy.

### Approved identifier strategy

- `memory_id`: use when the caller already tracks internal OpenBrain identity
- `match_key`: use for deterministic sync pipelines
- `obsidian_ref`: use only for Obsidian-originated records

### Policy

- New ingestion/sync pipelines should standardize on `match_key`.
- `obsidian_ref` must not be the primary identity for non-Obsidian systems.
- CI smoke tests should use `match_key` or `memory_id`, not `obsidian_ref`.

## Admin Tool Guardrails

### `store_bulk`

- Allowed for net-new ingestion.
- Precondition:
  - source is known
  - batch owner is known
  - duplicate tolerance is defined

### `upsert_bulk`

- Allowed only when:
  - each record has a deterministic `match_key`
  - the caller expects idempotent behavior
  - the upstream source has stable identity semantics
- `BulkUpsertResult` now correctly surfaces corporate-domain writes as `updated` (internally they produce `versioned` status via the V1 engine; the result maps this correctly).
- `previous_record_id` is carried in individual `BatchResultItem` entries for versioned writes.

### `maintain`

- Always run in `dry_run=true` first.
- Never run destructive maintenance blind.
- Every non-dry-run execution must produce a saved report.

## Retrieval Quality Rules

The system is only trustworthy if retrieval remains anchored to active truth.

- `search` should return active records only.
- `get_context` should summarize active records only.
- superseded records should remain exportable and auditable, but not pollute day-to-day retrieval.
- if duplicate rates rise, retrieval trust falls even when search technically works.

## Observability Requirements

The following metrics are the minimum production set.

### Write metrics

- `memories_created_total`
- `memories_updated_total`
- `memories_versioned_total`
- `memories_skipped_total`
- `bulk_batches_total`
- `bulk_records_total`

### Hygiene metrics

- `active_memories_total`
- `superseded_memories_total`
- `duplicate_candidates_total`
- `orphaned_supersession_links_total`
- `owner_normalizations_total`

### Sync metrics

- `sync_checks_total`
- `sync_exists_total`
- `sync_missing_total`
- `sync_outdated_total`
- `sync_synced_total`

### Retrieval metrics

- `search_requests_total`
- `get_context_requests_total`
- `search_zero_hit_rate`
- `duplicate_hit_rate`

## SLO Targets

Minimum starting targets for production:

- `search` zero-hit rate for known-good operational queries: under 5%
- duplicate candidates among active records: under 2%
- orphaned supersession links: 0
- admin `maintain` dry-run reviewed at least once per day
- all pipeline-driven writes use `match_key`: 100%

### Alert thresholds

- `policy_skip_per_maintain_run_ratio`
  - `watch >= 0.25`
  - `elevated >= 1.0`
- `duplicate_candidates_per_maintain_run_ratio`
  - `watch >= 1.0`
  - `elevated >= 5.0`
- `search_zero_hit_ratio`
  - `watch >= 0.05`
  - `elevated >= 0.15`
- `operational_health_status`
  - `0 = normal`
  - `1 = watch`
  - `2 = elevated`

## Runbook

### Daily

- Check write volume and duplicate candidate count.
- Run `maintain` in dry-run mode.
- Review `sync_outdated_total` and `sync_missing_total`.

### Weekly

- Execute reviewed dedup and link-fix operations.
- Review top producers of duplicate records.
- Validate that bulk pipelines still emit stable `match_key`.

### Monthly

- Review domain policy adherence.
- Reclassify records or entity types that should move from mutable to versioned handling.
- Review retention and export requirements for `corporate`.

## Immediate Engineering Backlog

The following items from the original v2.1 backlog have been resolved in v2.2:
- ~~Add per-record `operation_type` to `upsert_bulk` results.~~ ✅ Done — `versioned` status now propagates correctly.
- ~~Add `previous_record_id` for versioned writes.~~ ✅ Done — carried in `BatchResultItem.previous_record_id`.
- ~~Expose duplicate and supersession metrics.~~ ✅ Done — metrics shipped in v2.1.
- ~~Persist `maintain` execution reports.~~ ✅ Done — stored in `audit_log`, retrievable via `/api/admin/maintain/reports`.
- ~~Move `tenant_id` from `metadata_` JSONB to a dedicated indexed column.~~ ✅ Done — added in v2.3.
- ~~Implement governance-safe remediation for append-only duplicates.~~ ✅ Done — added in v2.3 via `duplicate` status.

Remaining backlog:
1. ~~Replace in-memory `TelemetryRegistry` with a shared counter backend for multi-worker deployments.~~ ✅ Done — telemetry counters now support configurable backend (`memory`/`redis`) with safe fallback and shared Redis mode for multi-worker aggregation.
2. ~~Add regression test ensuring `brain_store(domain="corporate")` succeeds end-to-end via the MCP gateway.~~ ✅ Done — gateway now enforces corporate write contract (`owner` + `match_key`) and includes regression tests for successful corporate store flow.
3. ~~Add policy tests for domain-specific update semantics (corporate versioning, build in-place).~~ ✅ Done — policy enforcement tests now assert corporate uses append-version updates while build remains in-place/upsert.

## Known Technical Debt

These items are known architectural limitations, not current production blockers.

- **Export redaction in application code**: The redaction rules in `_export_record` are implemented as application logic. This is acceptable while the policy surface is small, but a multi-tenant or compliance-heavy deployment should move redaction into a dedicated policy layer. Currently: admin and internal service accounts both receive unredacted export data.

- **Telemetry fallback alert tuning**: fallback visibility is now instrumented via `telemetry_counter_backend_fallback_total` and alerted in Prometheus. Remaining work is operational tuning of thresholds/durations per environment to reduce false positives during controlled restarts.

## Bottom Line

Without this layer, OpenBrain is a capable memory engine that can drift into a data swamp.

With this layer, OpenBrain becomes an operational knowledge system:

- current truth is retrievable
- history is preserved where needed
- ingestion is measurable
- cleanup is intentional
