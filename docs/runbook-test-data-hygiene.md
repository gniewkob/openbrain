# Runbook: Test Data Hygiene

## Overview

Procedures for maintaining clean separation between hidden test data and production memory records in OpenBrain.

## Alerts

### OpenBrainHiddenTestDataPresent

Hidden test records are active in the store. This is expected during CI runs but should not persist in production.

**Action:** Run `brain_cleanup_build_test_data` or check if a CI run left orphaned test data.

### OpenBrainHiddenTestDataShareHigh

Hidden test data exceeds 25% of active memory records.

**Action:** Trigger maintenance: `brain_maintain(domain="build")` or manually delete stale test records.

## MCP HTTP Session Errors

### Missing session ID

Occurs when a client sends a stateless HTTP request without a valid `mcp-session-id` header.

**Cause:** Client does not support streamable-http session negotiation.

**Action:** Ensure the client includes the session ID returned by the `/` initialization response in subsequent requests. Stateless mode (`stateless_http=True`) is required — each request must be self-contained.

## Test Data Lifecycle

- Test records use `match_key` prefix `hidden_test_data_*`
- Cleaned up via `brain_cleanup_build_test_data` tool or `POST /api/v1/maintenance/cleanup-test-data`
- CI pipelines must not leave test data in `status=active` after runs
