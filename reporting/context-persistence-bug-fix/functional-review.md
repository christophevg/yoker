# Functional Review — Context Persistence Bug Fix (PR #55)

**Branch:** `fix/context-persistence`
**Stage:** Phase 5.6 Stage a (functional review)
**Reviewer:** functional-analyst
**Date:** 2026-07-28
**Verdict:** APPROVED

## Scope

Review the python-developer's implementation against the 6 acceptance
criteria from the owner-approved plan for the context-persistence bug
fix. Source analysis: `analysis/context-persistence-bug.md`.

The plan covers three bugs:
- Bug #1 (critical): Tool results never persisted — `Persisted._persist_full_state` used `get_messages()` (excludes role=tool) instead of `get_context()`.
- Bug #2 (high): Assistant narration content lost on tool-call turns — `add_tool_calls` hardcoded `content=""`; processing loop did not thread `content` through.
- Bug #3 (medium): User messages persisted twice — `turn_start` marker duplicated the `message` record's content.

Bug #4 (synthetic timestamps) was explicitly out of scope per the approved plan.

## Files Reviewed

- `src/yoker/context/persisted.py` — Bug #1 (10 call sites), Bug #2 (`_item_to_record` + `_process_record`), Bug #3 (`turn_start` marker)
- `src/yoker/context/manager.py` — Bug #2 (`add_tool_calls` content param)
- `src/yoker/context/wrapper.py` — Bug #2 (forwarding content)
- `src/yoker/context/protocol.py` — Bug #2 (Protocol signature)
- `src/yoker/core/_processing.py` — Bug #2 (`_execute_tool_calls` content threading)
- `tests/test_context_persisted.py` — 8 new tests in `TestPersistedBugFixes`

## Acceptance Criteria Verification

### 1. Tool results ARE persisted to JSONL files — PASS

All 10 `_persist_full_state` call sites in `persisted.py` now use
`self._wrapped.get_context()` (verified via grep — no `get_messages()`
remain in any persist path). The `tool_result` serialization branch in
`_item_to_record` (lines 339-345) is now live.

Test evidence: `test_tool_result_persisted_to_jsonl` asserts exactly one
`tool_result` record with correct `tool_name`, `tool_id`, `result`, and
`success` fields.

### 2. Assistant reasoning content is preserved on tool-call turns — PASS

Four coordinated changes implemented exactly per the plan:
- `BaseContextManager.add_tool_calls` accepts `content: str = ""` and stores it (manager.py:110-135).
- `ContextManagerWrapper.add_tool_calls` forwards `content` (wrapper.py:71-77).
- `Persisted.add_tool_calls` forwards `content`; `_item_to_record` includes `content` in the `tool_call_message` record; `_process_record` reads `content` from `data.get("content", "")` (persisted.py:167-174, 346-351, 486-493).
- `_execute_tool_calls` in `_processing.py` accepts `content: str = ""` and passes it to `add_tool_calls`; `process_message` threads the streamed `content` at line 271.

The Protocol signature in `protocol.py` was updated to match.

Test evidence: `test_assistant_content_preserved_on_tool_call_turn` and
`test_assistant_content_persisted_and_replayed` confirm both in-memory
and on-disk persistence of narration content.

### 3. User messages are NOT duplicated in the JSONL — PASS

`_persist_full_state` now emits `turn_start` with `data: {}` (pure
boundary marker); the user content lives only in the `message` record
emitted by `_item_to_record` (persisted.py:307-314).

Test evidence: `test_user_message_not_duplicated_in_jsonl` asserts
exactly one `message` record with `role=user`, and that the
`turn_start` record does NOT carry a `user_message` field. The
regression guard `test_turn_start_still_emitted_for_turn_count`
verifies `turn_start` markers are still emitted (preserving
`list_sessions` turn counting).

### 4. Regression: tool result available for next turn via get_context() — PASS

Test evidence: `test_tool_result_available_for_next_turn` drives
`start_turn` + `add_tool_calls(content=...)` + `add_tool_result` and
asserts 3 messages in `get_context()` (user, assistant with tool_calls
+ content, tool), with the tool result carrying the correct `tool_id`.

### 5. Full loop (tool call → result → next turn) survives save/load — PASS

Test evidence: `test_full_loop_survives_save_load` drives a complete
loop (start_turn → add_tool_calls with content → add_tool_result →
end_turn), saves, closes, reloads into a fresh `Persisted`, and
asserts 4 messages replayed with tool-call/tool-result pairing intact
and assistant narration preserved. This directly addresses the
"orphaned tool calls cause agent loops" failure mode from the
analysis.

### 6. make check passes — PASS

`make check` (format + lint + typecheck + test) reports
**2195 passed, 8 skipped, 15 warnings** with no failures. The 8 new
`TestPersistedBugFixes` tests all pass; the 25 pre-existing
`test_context_persisted.py` tests still pass (including the
line-count assertions in `test_add_message_persists_to_jsonl` and
`test_bulk_rewrite_on_every_mutation`, which remain valid because
the `turn_start` marker is still emitted — just with empty data).

## Owner's Stated Worries

The owner's worries quoted in the analysis:

1. **"things were missing ... in the context"** — Addressed by Bug #1.
   Tool results now reach the JSONL file. The dead-code
   `tool_result` branch is now live.

2. **"things ... double" / "things in the context that were out of order"** —
   Addressed by Bug #3 (deduplication) and Bug #2 (preserving narration
   so the model does not re-narrate). Bug #4 (synthetic timestamps
   causing apparent out-of-order records) was explicitly out of scope
   per the approved plan; the implementation correctly does NOT attempt
   it.

3. **Agent loops (re-reading same files, re-deriving conclusions)** —
   Addressed by the combination of Bug #1 (tool results visible on
   resume, so the model does not re-invoke the same tools) and Bug #2
   (narration visible, so the model can continue its investigative
   state rather than restarting). The full-loop regression test
   confirms the pairing invariant required by OpenAI/Anthropic/Ollama
   (assistant tool_calls must be followed by matching tool_result
   messages) is preserved across save/load.

## Completeness Check — Remaining Gaps

None identified for the in-scope work. Specifically:

- All 9 persist call sites named in the plan (plus the `agent` setter,
  the original analysis named 9 but the file has 10 — all are
  converted). Verified by grep.
- All 4 coordinated changes for Bug #2 are present and consistent.
- The Protocol signature change is backward-compatible (`content:
  str = ""` default).
- No new `get_messages()` calls were introduced as a side effect.
- The `turn_start` marker is preserved (not removed) so
  `list_sessions` turn counting continues to work.
- Bug #4 (synthetic timestamps) is correctly left unaddressed — it
  was out of scope per the approved plan, and attempting it would
  have required either adding an internal `_ts` field stripped by
  `get_context()` (backend-compatibility risk) or a larger
  append-only rewrite (out of scope per Bug #5 in the analysis).

## Regressions

None. The full test suite passes (2195 passed, 8 skipped — same as
the python-developer's report). The pre-existing
`test_add_message_persists_to_jsonl` and
`test_bulk_rewrite_on_every_mutation` tests still pass because the
`turn_start` marker is still emitted; only its `data` payload
changed (empty dict instead of carrying `user_message`), and those
tests count lines, not payload fields.

## Verdict

**APPROVED.**

All 6 acceptance criteria are met. The implementation faithfully
follows the owner-approved plan with no deviations. The owner's
three stated worries are each addressed by specific changes with
test coverage. No regressions. The fix is complete — no remaining
gaps would cause the loop within the scope of the approved plan.