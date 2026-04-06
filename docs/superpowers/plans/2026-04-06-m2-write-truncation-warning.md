# M2: Write-Time Content Truncation Warning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit a structlog warning and populate `MemoryWriteResponse.warnings` when written content exceeds the embedding character limit (6 000 chars), so operators and callers know vector search will only index the first 6 000 chars.

**Architecture:** The embedding truncation already happens silently in `embed.py:get_embedding()`. The fix adds an explicit check in `handle_memory_write()` (before the DB sub-functions are called), logs a structured warning, and appends a human-readable message to the response `warnings` list. No schema changes — `MemoryWriteResponse.warnings` already exists.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, structlog, unittest (no new dependencies)

---

## File Map

| File | Change |
|------|--------|
| `unified/src/memory_writes.py` | Add `_warn_if_truncated()` helper; call it in `handle_memory_write()` and append warning to response |
| `unified/tests/test_memory_writes.py` | Add 3 tests: warning logged, warning in response, short content not warned |

---

### Task 1: Add truncation warning helper and wire it up

**Files:**
- Modify: `unified/src/memory_writes.py:344-408`
- Test: `unified/tests/test_memory_writes.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `unified/tests/test_memory_writes.py`:

```python
import unittest
from unittest.mock import AsyncMock, patch, MagicMock


class TestWriteTruncationWarning(unittest.TestCase):
    """handle_memory_write warns when content exceeds EMBED_MAX_CHARS."""

    def _make_request(self, content: str) -> "MemoryWriteRequest":
        from src.schemas import MemoryWriteRequest, MemoryWriteRecord, WriteMode
        return MemoryWriteRequest(
            record=MemoryWriteRecord(
                content=content,
                domain="build",
                entity_type="Test",
            ),
            write_mode=WriteMode.upsert,
        )

    def test_warning_logged_when_content_too_long(self):
        """A structlog warning is emitted when content > EMBED_MAX_CHARS."""
        from src.embed import EMBED_MAX_CHARS
        from src.memory_writes import _warn_if_truncated
        import structlog

        long_content = "x" * (EMBED_MAX_CHARS + 1)
        with patch("src.memory_writes.log") as mock_log:
            result = _warn_if_truncated(long_content, domain="build", entity_type="Test")
        mock_log.warning.assert_called_once()
        call_kwargs = mock_log.warning.call_args
        assert call_kwargs[0][0] == "write_content_will_be_truncated"
        assert result is not None  # returns warning message string

    def test_no_warning_for_short_content(self):
        """No warning is emitted when content is within the limit."""
        from src.embed import EMBED_MAX_CHARS
        from src.memory_writes import _warn_if_truncated

        short_content = "x" * EMBED_MAX_CHARS  # exactly at limit — no warning
        with patch("src.memory_writes.log") as mock_log:
            result = _warn_if_truncated(short_content, domain="build", entity_type="Test")
        mock_log.warning.assert_not_called()
        assert result is None

    def test_warning_appears_in_response_warnings(self):
        """MemoryWriteResponse.warnings contains truncation message when content > limit."""
        import asyncio
        from src.embed import EMBED_MAX_CHARS

        long_content = "x" * (EMBED_MAX_CHARS + 500)
        request = self._make_request(long_content)

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock(return_value=None)

        fake_embedding = [0.1] * 768

        with patch("src.memory_writes._get_embedding_compat", new=AsyncMock(return_value=fake_embedding)):
            from src.memory_writes import handle_memory_write
            response = asyncio.run(handle_memory_write(mock_session, request))

        assert any("6" in w and "chars" in w for w in response.warnings), (
            f"Expected truncation warning in response.warnings, got: {response.warnings}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_memory_writes.py::TestWriteTruncationWarning -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '_warn_if_truncated'` or similar FAIL.

- [ ] **Step 3: Add `_warn_if_truncated` helper to `memory_writes.py`**

In `unified/src/memory_writes.py`, add this import at the top (after the existing imports from `.embed`):

```python
from .embed import get_embedding, EMBED_MAX_CHARS
```

Replace the existing line `from .embed import get_embedding` with the above.

Then add this helper function **before** `handle_memory_write` (around line 343):

```python
def _warn_if_truncated(content: str, *, domain: str, entity_type: str) -> str | None:
    """
    Log a warning and return a warning message if content exceeds EMBED_MAX_CHARS.

    Returns the warning string (to append to response.warnings), or None if no warning.
    """
    if len(content) <= EMBED_MAX_CHARS:
        return None
    log.warning(
        "write_content_will_be_truncated",
        content_len=len(content),
        embed_max_chars=EMBED_MAX_CHARS,
        domain=domain,
        entity_type=entity_type,
    )
    return (
        f"Content ({len(content)} chars) exceeds embedding limit "
        f"({EMBED_MAX_CHARS} chars); only the first {EMBED_MAX_CHARS} chars "
        "will be indexed for vector search."
    )
```

- [ ] **Step 4: Wire `_warn_if_truncated` into `handle_memory_write`**

In `handle_memory_write` (around line 390, after `_log_duplicate_risk(rec)`), add:

```python
    # Warn if content will be truncated during embedding
    _truncation_warning = _warn_if_truncated(
        rec.content, domain=domain, entity_type=rec.entity_type
    )
```

Then, wherever `handle_memory_write` returns a non-failed response, append the warning.
Replace the existing four return paths with versions that carry the warning:

```python
    # Create new memory if none exists
    if not existing:
        result = await _create_new_memory(
            session, rec, actor, content_hash, append_only_policy, _commit
        )
        if _truncation_warning and result.status != "failed":
            result.warnings.append(_truncation_warning)
        return result

    # Skip if content hasn't changed
    if _record_matches_existing(existing, rec, content_hash):
        return MemoryWriteResponse(status="skipped", record=_to_record(existing))

    # Version or update based on mode and policy
    if mode == WriteMode.append_version or append_only_policy:
        result = await _version_memory(
            session, existing, rec, actor, content_hash, _commit
        )
        if _truncation_warning and result.status != "failed":
            result.warnings.append(_truncation_warning)
        return result

    result = await _update_memory(session, existing, rec, actor, content_hash, _commit)
    if _truncation_warning and result.status != "failed":
        result.warnings.append(_truncation_warning)
    return result
```

The full updated `handle_memory_write` function (replace lines 344–408):

```python
async def handle_memory_write(
    session: AsyncSession,
    request: MemoryWriteRequest,
    actor: str = "agent",
    _commit: bool = True,
) -> MemoryWriteResponse:
    """
    Handle single memory write with domain-aware governance.

    Args:
        session: Database session
        request: Memory write request containing record and write mode
        actor: Actor performing the write (default: "agent")
        _commit: Whether to commit transaction (for batch operations)

    Returns:
        MemoryWriteResponse with status and record info

    Raises:
        ValueError: For invalid write operations
    """
    rec = request.record
    mode = request.write_mode
    domain = rec.domain
    append_only_policy = _requires_append_only(domain, rec.entity_type)

    # Validate corporate domain requirements
    if domain == "corporate":
        mode, errors = _validate_corporate_domain(rec, mode)
        if errors:
            return MemoryWriteResponse(status="failed", errors=errors)

    # Find existing record
    existing = await _find_existing_memory(session, rec.match_key)

    # Validate write mode
    mode_errors = _validate_write_mode(mode, existing, rec.match_key)
    if mode_errors:
        return MemoryWriteResponse(status="failed", errors=mode_errors)

    # Compute content hash
    from .models import compute_hash

    content_hash = compute_hash(rec.content)

    # Log duplicate risk
    _log_duplicate_risk(rec)

    # Warn if content will be truncated during embedding
    _truncation_warning = _warn_if_truncated(
        rec.content, domain=domain, entity_type=rec.entity_type
    )

    # Create new memory if none exists
    if not existing:
        result = await _create_new_memory(
            session, rec, actor, content_hash, append_only_policy, _commit
        )
        if _truncation_warning and result.status != "failed":
            result.warnings.append(_truncation_warning)
        return result

    # Skip if content hasn't changed
    if _record_matches_existing(existing, rec, content_hash):
        return MemoryWriteResponse(status="skipped", record=_to_record(existing))

    # Version or update based on mode and policy
    if mode == WriteMode.append_version or append_only_policy:
        result = await _version_memory(
            session, existing, rec, actor, content_hash, _commit
        )
        if _truncation_warning and result.status != "failed":
            result.warnings.append(_truncation_warning)
        return result

    result = await _update_memory(session, existing, rec, actor, content_hash, _commit)
    if _truncation_warning and result.status != "failed":
        result.warnings.append(_truncation_warning)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m pytest tests/test_memory_writes.py -v 2>&1 | tail -30
```

Expected: All tests PASS including the 3 new `TestWriteTruncationWarning` tests.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
cd /Users/gniewkob/Repos/openbrain/unified
python -m unittest discover -s tests -v 2>&1 | tail -30
```

Expected: All previously passing tests still PASS. No new failures.

- [ ] **Step 7: Commit**

```bash
cd /Users/gniewkob/Repos/openbrain
git add unified/src/memory_writes.py unified/tests/test_memory_writes.py
git commit -m "fix(M2): warn at write-time when content exceeds embedding limit

Add _warn_if_truncated() to memory_writes.py. Emits structlog warning
and appends message to MemoryWriteResponse.warnings when content > 6000
chars so callers know vector search will only index the first 6000 chars.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- M2 requirement: "Dodaj ostrzeżenie przy write gdy len(content) > EMBED_MAX_CHARS" ✅ Task 1 covers it
- Warning in logs ✅ (structlog warning with domain/entity_type context)
- Warning in API response ✅ (appended to `MemoryWriteResponse.warnings`)
- No warning for short content ✅ (test_no_warning_for_short_content)

**Placeholder scan:** None found.

**Type consistency:** `_warn_if_truncated` returns `str | None`, consumed consistently across all 3 return paths in `handle_memory_write`.

**N3 status:** Already implemented in `app_factory.py` (FastAPI title/version/description at lines 70-76). No action needed.
