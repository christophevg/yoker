# Cost Estimate: Interactive Approve-on-Diff for `protected_files` (MBI-009 T12)

**Date**: 2026-07-27
**Task**: Cost estimate for the interactive "ask for permission" approve-on-diff flow, on top of the simple block accepted for T12.
**Reviewer**: API Architect Agent
**Source**: Owner question — "what would be the added cost of introducing the interactive 'ask for permission' now?"
**Baseline**: `analysis/api-protected-files.md` (the simple-block T12 design the owner already accepted)

## Summary

**Added cost over the accepted simple block: ~190-260 lines of code, across 7 files (3 new methods, 1 new optional Agent attribute, 1 guardrail conditional, 1 processing-loop hook, 1 shared diff helper). No new event type, no new ToolResult shape, no async guardrail. The simple block stays as the non-interactive fallback.**

The interactive flow is a **localized, additive** change on top of the simple block. It does not require reworking the sync guardrail architecture. The recommended approach puts the approval check in the processing loop (`_run_tool` in `_processing.py`), which is already async and has access to the full tool args and the agent.

## Baseline (already accepted for T12)

The owner's accepted T12 design (`analysis/api-protected-files.md`):
- `PermissionsConfig.protected_files: tuple[str, ...]` with the default denylist.
- `PathGuardrail._check_protected_files(resolved) -> str | None` — basename match, called from the `write` and `update` branches.
- Returns `ValidationResult(valid=False, reason="File is protected against agent writes: {name}")` — a simple, unconditional block.
- ~30 lines total (config field + guardrail method + two call sites + tests).

**This baseline ships as-is for T12. The interactive flow is additive on top of it.**

## Recommended Approach: Option D — Approval in the Processing Loop

### Why not the other options

| Option | Verdict |
|---|---|
| **A: Move check to tool functions** | Duplicates the protected_files check across `write` and `update`; the tool has no UI access today (would need ToolContext extension). ~245 lines, split across two files. |
| **B: Async PathGuardrail** | Guardrail base is sync; making it async ripples to `_validate_tool_args` (sync) and every caller. Large architectural change for one feature. Rejected. |
| **C: Two-phase (guardrail blocks, tool asks)** | Close to Option D but splits the logic across guardrail + tool. More files touched, more duplication. |
| **D: Processing-loop hook** | The loop (`_run_tool`) is async, has `agent` + full `tool_args`, and runs before the tool. Single place for the approval check. Reuses `update.py`'s diff generator. **Minimal.** |

### How Option D works

1. **`PathGuardrail._check_protected_files`** stays as the unconditional safety net for non-interactive mode. One change: in interactive mode (`config.ui.mode == "interactive"` AND an approval handler is wired), the guardrail **skips** the protected_files block and lets the processing loop handle it. ~3-line conditional.

2. **`_run_tool` in `_processing.py`** gains a new step after `_validate_tool_args` and before `_execute_tool`: if the tool is `write`/`update`, the path is protected, and `agent._approval_handler` is set, generate a diff and call the handler. On denial, return a blocked `ToolResult` without executing the tool. On approval, proceed. ~40-60 lines.

3. **`Agent`** gains one optional attribute: `_approval_handler: Callable[[str, str], Awaitable[bool]] | None = None`. Typed as a narrow callable (not `UIHandler`) so the Agent stays UI-agnostic. ~5 lines.

4. **`UIHandler`** gains one async method: `confirm_approval(path: str, diff: str) -> bool`. ~5 lines in the protocol.

5. **`InteractiveUIHandler.confirm_approval`**: display the diff (reuse the existing `_show_diff_content`), prompt yes/no via `get_input`, return bool. ~20 lines.

6. **`BatchUIHandler.confirm_approval`**: always return `False` (non-interactive — the guardrail already blocked it, this is defensive). ~5 lines.

7. **Diff generation**: for `update`, reuse `update.py`'s existing `difflib.unified_diff` logic (extract a shared `_generate_diff(old, new)` helper, ~15 lines). For `write`, diff against the existing file content (if overwriting) or show the new content as all-additions (if new file). ~20 lines.

8. **Wiring** (`cli/chat.py` and `cli/loop.py`): set `agent._approval_handler = ui.confirm_approval` when constructing the Session/Agent. ~2 lines per call site.

### Why this is minimal

- **No new event type.** Events are fire-and-forget; getting a response would need a Future-carrying event, which is a new pattern. A direct callable on the Agent is simpler.
- **No new ToolResult shape.** The approval denial returns a standard `ToolResult(success=False, error="...")`.
- **No async guardrail.** The guardrail stays sync; the async approval lives in the already-async processing loop.
- **No ToolContext change.** The approval handler lives on the Agent, not in ToolContext. The processing loop reaches it via `agent._approval_handler` before the tool is even invoked.
- **Reuses existing diff code.** `update.py` already has `difflib.unified_diff` + truncation logic; extract a shared helper.
- **Reuses existing UI diff rendering.** `InteractiveUIHandler._show_diff_content` already renders colored unified diffs.

## Is the Simple Block Still Needed?

**Yes — it is the non-interactive fallback and the safety net.**

| Scenario | What blocks |
|---|---|
| Batch mode (`ui.mode == "batch"`) | `PathGuardrail._check_protected_files` (simple block) |
| Interactive mode, no approval handler wired (e.g. library/programmatic use) | `PathGuardrail._check_protected_files` (simple block) |
| Interactive mode, approval handler wired, user denies | Processing loop returns blocked `ToolResult` |
| Interactive mode, approval handler wired, user approves | Tool proceeds |

The guardrail's simple block is the **unconditional safety net**. The interactive flow only short-circuits it when (a) interactive mode is active AND (b) an approval handler is wired. If the handler is ever unset or the mode flips to batch, the simple block re-engages automatically.

## How the Diff is Generated and Displayed

- **`update` tool**: the tool args contain `old_string` and `new_string`. The existing file content is read from disk (same as the tool already does). `difflib.unified_diff(old_lines, new_lines)` produces the diff. This is the exact logic in `update.py`'s `_build_content_or_diff_metadata` — extracted to a shared helper.

- **`write` tool**: the tool args contain `content`. If the file exists (overwrite), read the current content and diff against the new content. If new file, show the full content as additions (all `+` lines).

- **Display**: `InteractiveUIHandler.confirm_approval` calls the existing `_show_diff_content` to render the colored diff, then prompts: `Approve write to Makefile? [y/N] `. The user's answer maps to bool.

## How Approval/Resume Works

The processing loop is a single async function (`_run_tool`). There is no "pause and resume" — the loop simply `await`s the approval handler:

```python
# In _run_tool, after _validate_tool_args passes:
if _is_protected(tool_name, tool_args, agent) and agent._approval_handler:
  diff = _generate_approval_diff(tool_name, tool_args)
  approved = await agent._approval_handler(path, diff)
  if not approved:
    return f"Error: User denied write to protected file: {path}", False, None
# proceed to _execute_tool
```

The `await` suspends the coroutine until the user responds. No callbacks, no futures, no state machine. The agent's `process()` serializes turns via `_process_queue`, so no other turn runs while waiting.

## Files to Modify/Create

| File | Change | Est. Lines |
|---|---|---|
| `src/yoker/config/__init__.py` | (baseline T12) `protected_files` field | ~5 (already counted in T12) |
| `src/yoker/tools/guardrails/path.py` | (baseline T12) `_check_protected_files` + conditional skip in interactive mode | ~10 (T12) + ~3 (conditional) |
| `src/yoker/ui/handler.py` | Add `confirm_approval` to UIHandler protocol | ~5 |
| `src/yoker/ui/interactive.py` | Implement `confirm_approval` (diff display + yes/no prompt) | ~20 |
| `src/yoker/ui/batch.py` | Implement `confirm_approval` (always False) | ~5 |
| `src/yoker/core/__init__.py` | Add `_approval_handler` attr to Agent | ~5 |
| `src/yoker/core/_processing.py` | Add approval check in `_run_tool` + shared diff helper | ~55 |
| `src/yoker/builtin/update.py` | Extract `_generate_diff` shared helper (refactor existing, no new logic) | ~15 (net ~0 — moved code) |
| `src/yoker/cli/chat.py` | Wire `agent._approval_handler = ui.confirm_approval` | ~2 |
| `src/yoker/cli/loop.py` | Same wiring | ~2 |
| Tests (new file or extend existing) | Interactive approve/deny, batch block, no-handler block, diff generation | ~100 |
| **Total added over T12 baseline** | | **~200-260 lines** |

## Tests Needed

1. **Interactive approve** → tool executes, content written, `ToolResult(success=True)`.
2. **Interactive deny** → tool blocked, `ToolResult(success=False, error="User denied...")`, file unchanged.
3. **Batch mode** → guardrail simple block fires, tool never reached, `"Error: File is protected..."`.
4. **Interactive mode, no approval handler wired** → guardrail simple block fires (safety net).
5. **`write` new protected file** → diff shows all-additions; approve → file created.
6. **`write` overwrite protected file** → diff against existing content; approve → file overwritten.
7. **`update` protected file** → diff from `old_string`/`new_string`; approve → file updated.
8. **Non-protected file in interactive mode** → no approval prompt, tool proceeds normally.
9. **Empty `protected_files` list** → no approval prompt, no block (protection disabled).
10. **Approval handler raises exception** → caught in processing loop, treated as denial (fail-safe).

## Architectural Concerns and Risks

1. **Agent gains an optional `_approval_handler` attribute.** The Agent is designed to be UI-agnostic (events are the only UI coupling). Adding a direct callable is a small pragmatic leak. **Mitigation**: type it as a narrow `Callable[[str, str], Awaitable[bool]]`, not `UIHandler`. The Agent never imports UI types. The attribute is optional (None = no interactive approval).

2. **Guardrail conditional on `config.ui.mode`.** The guardrail currently does not branch on UI mode. The protected_files check would be the first mode-conditional guardrail logic. **Mitigation**: the condition is narrowly scoped (`ui.mode == "interactive" AND approval handler wired`) and the default is always block. The safety net fires on any ambiguity.

3. **Diff generation reads file content in the processing loop.** For `write` overwrite, the loop reads the existing file to diff against it. This is a new read I/O in the loop (currently the loop does no file I/O). **Mitigation**: the read is small (protected files are config files, typically <100 lines) and only fires for protected files in interactive mode. The `update` path already reads the file in the tool itself; the loop's read is only for `write` overwrite.

4. **User denial message goes back to the agent.** The agent receives `"Error: User denied write to protected file: Makefile"` and may retry or attempt a different approach. This is the same behavior as the simple block — the agent sees an error string and adapts. No new agent-facing contract.

5. **No timeout on the approval prompt.** If the user walks away, the turn hangs. **Mitigation**: this matches `get_input` behavior (the REPL also waits indefinitely). A timeout can be added later if needed (out of scope for the minimal cost).

6. **Sub-agents and sessions.** The `_approval_handler` is set on the primary Agent by the CLI. Sub-agents spawned via the `agent` tool would need the handler propagated. **Mitigation**: `Session.create_primary_agent` and `_spawn_internal` would set `_approval_handler` from the session's primary agent (or from the session itself). ~3 lines in `session/__init__.py` (not counted above — add ~5 lines if sub-agent approval is required for 1.0).

## Simplicity Principle: Comparison Against the Owner's Proposal

The owner's accepted T12 proposal is the simple block in PathGuardrail. This cost estimate does **not** replace or alter that proposal. It adds an **optional, conditional, additive** interactive flow on top of it. The simple block remains the default and the fallback. The interactive flow is gated on (a) interactive mode and (b) a wired approval handler — both opt-in. If either is absent, the system behaves exactly as the owner's accepted T12 design.

No abstraction, class, or indirection is added beyond what is strictly needed:
- One optional attribute on Agent (a narrow callable).
- One method on UIHandler.
- One conditional in the guardrail.
- One hook in the processing loop.
- One shared diff helper (extracted from existing code).

## Action Items

- [ ] Owner reviews this cost estimate and decides: ship interactive approval for 1.0, or ship the simple block for T12 and defer interactive to a follow-up.
- [ ] If shipping for 1.0: implement Option D alongside T12.1-T12.2.
- [ ] If deferring: T12 ships the simple block only; this estimate becomes the scope document for the follow-up task.
- [ ] If shipping: decide whether sub-agent approval propagation is needed for 1.0 (adds ~5 lines to `session/__init__.py`).