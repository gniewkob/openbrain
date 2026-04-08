# Iteration Report 2026-04-08 / 02

## Problem

Local Obsidian flows were only partially covered by tests. The gateway already exposed more Obsidian operations than the test suite verified, which left a contract gap between "available" and "trustworthy."

## Evidence

- Existing gateway tests covered only `vaults`, `read_note`, `sync`, and capability visibility.
- The gateway also exposed `write_note`, `export`, `collection`, `bidirectional_sync`, `sync_status`, and `update_note`.
- All local Obsidian tools rely on the same feature-flag gate, but that guarantee was not tested consistently across the full surface.

## Decision

- Expand gateway contract tests so every local Obsidian tool is covered for:
  - explicit opt-in enforcement,
  - expected backend endpoint/path,
  - expected request payload shape.

## Risk

- This iteration improves confidence in the gateway contract, but it does not validate real local vault I/O or end-to-end sync behavior against a live Obsidian environment.
- The backend HTTP Obsidian endpoints remain operationally distinct from the local stdio-only gateway feature flag.

## Status

- Local Obsidian tool gating: `fixed`
- Local Obsidian gateway path coverage: `fixed`
- Live end-to-end vault/sync verification: `deferred`
