# Iteration Report 2026-04-08 / 01

## Problem

`brain_capabilities` could overstate backend failure and understate exposed Obsidian functionality. The gateway also lacked an explicit behavioral contract for update audit attribution.

## Evidence

- Gateway readiness reporting treated non-200 `/readyz` outcomes as `unavailable`, even when the backend could still be reached.
- The gateway exposed more local Obsidian tools than `brain_capabilities` reported.
- PATCH audit attribution used the authenticated subject, while request payloads still accepted `updated_by`.

## Decision

- Treat backend reachability and backend readiness as separate signals in `brain_capabilities`.
- Report all local Obsidian tools in capabilities when the local feature flag is enabled.
- Lock the governance contract so audit actor attribution comes from authenticated identity, not a caller-provided `updated_by`.

## Risk

- Clients that treated any non-`ok` status as a hard outage may need to handle `degraded` explicitly.
- Users may assume `updated_by` in request payloads is authoritative; current behavior keeps compatibility but does not trust it for audit identity.

## Status

- `brain_capabilities` backend truthfulness: `fixed`
- Obsidian tool visibility in capabilities: `fixed`
- `updated_by` audit attribution semantics: `confirmed`
