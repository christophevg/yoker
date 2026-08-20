# Guardrail Hardcoded-Gate Audit — Findings & Fix Plan

## Context

During investigation of a guardrail bypass bug (namespaced tool names like
`"yoker:write"` were never in the hardcoded `_FILESYSTEM_TOOLS` set, so
`PathGuardrail.validate()` skipped all validation), we fixed the immediate
bug and then audited the codebase for similar patterns. This document
captures the findings and their resolution status.

**Commit that fixed the original bug:**
`dba698c fix(guardrail): remove _FILESYSTEM_TOOLS gate and unify approval across all agents`

## Findings

### 1. `_maybe_approve_protected` excludes the `file` tool

**Severity: Bug — ✅ FIXED**

**Location:** `src/yoker/core/_processing.py`

**Problem:** The `file` tool (`copy`, `move`, `delete` operations) has
`Path`-annotated parameters (`source`, `destination`) and is subject to
the `PathGuardrail` protected_files check in `validate()`. But
`_maybe_approve_protected` only fired for `write` and `update`. In
interactive mode, if an agent tries to `file(move, source="Makefile",
destination="Makefile.bak")`, the guardrail blocked it and the user
**never got an approval prompt** — the operation was just blocked with
no recourse.

**Fix:** Removed the `("write", "update")` hardcoded gate. The function now
iterates over `spec.guards` to find all `Path`-annotated parameters,
extracts their values from `tool_args`, and checks each against
`guardrail.is_protected()`. If any is protected, the approval flow fires.
`_build_approval_diff` was extended to handle the `file` tool (delete shows
content being removed; copy/move shows a summary diff).

### 2. `_maybe_approve_protected` hardcodes `"path"` parameter name

**Severity: Bug (latent) — ✅ FIXED**

**Location:** `src/yoker/core/_processing.py`

**Problem:** The approval hook hardcoded `tool_args.get("path")`, so it
would miss `make` (uses `cwd`) and `file` (uses `source`/`destination`).
Today this was masked by finding #1 (only `write`/`update` were checked,
and both use `path`), but it was a latent bug for any future tool.

**Fix:** The function now iterates over `spec.guards` to find all
`Path`-annotated parameters by their actual parameter name, extracting
values from `tool_args` dynamically. No hardcoded parameter names remain.

### 3. `_get_tool_config` hardcoded mapping in `PathGuardrail`

**Severity: Maintenance trap — ✅ FIXED**

**Location:** `src/yoker/tools/guardrails/path.py`

**Problem:** This was the same anti-pattern as the removed
`_FILESYSTEM_TOOLS` — a hardcoded mapping that must be manually kept in
sync. If a new built-in filesystem tool was added, this mapping had to be
updated or extension/size checks silently wouldn't fire.

**Fix:** Replaced the 12-line mapping with a 3-line try/except that uses
`self._config.tools[tool_name]` (which uses `__getitem__` → `getattr`).
Unknown tool names return `None` via the except clause.

### 4. Ad-hoc namespace stripping in `_processing.py`

**Severity: Fragile (not a bug today) — ✅ FIXED**

**Locations:**
- `_maybe_approve_protected` — no longer receives `tool_name`; receives
  `spec` and uses `spec.simple_name`.
- `_build_tool_context` — no longer receives `tool_name`; receives `spec`
  and uses `spec.simple_name`.

**Fix:** Both functions now receive the `ToolSpec` object (already
available at the call site in `_run_tool`) and use `spec.simple_name`
instead of ad-hoc `tool_name.split(":")[-1]` string manipulation. This
eliminates the fragile namespace-stripping pattern entirely.

### 5. `_TOOL_CONFIG_MAP` in `registry.py` (not a bug)

**Location:** `src/yoker/tools/registry.py`

This is a similar hardcoded mapping, but it's **correct by design**:
the `namespace != "yoker"` guard at line 53 ensures plugin tools bypass
this mapping entirely. Only built-in yoker tools are filtered, and the
mapping is the dispatch mechanism. No fix needed.

### 6. Primary-vs-subagent divergence (fixed)

**Status: ✅ Resolved in commit `dba698c`**

The approval handler is now stored on the `Session` and propagated to
every agent via `_create_agent`. Subagents in interactive sessions get
the same approval prompt as the primary agent.

## Summary

All actionable findings (#1–#4) have been fixed. Finding #5 is correct by
design and needs no change. Finding #6 was already resolved in the
original fix commit.

## Test Coverage

The regression test for the original bug is at:
`tests/test_core/test_guardrail_namespace_bug.py`

New tests for findings #1/#2 were added to:
`tests/test_core/test_protected_files_approval.py`

New test cases:
- `test_approval_file_tool_delete_protected` — file tool delete on a
  protected file triggers approval and returns True when approved
- `test_approval_file_tool_move_protected` — file tool move on a
  protected file triggers approval and returns False when denied
- `test_approval_file_tool_no_handler_returns_false` — file tool with no
  handler returns False (guardrail blocks)
- `TestBuildApprovalDiffFile.test_file_delete_diff` — delete diff shows
  file content being removed
- `TestBuildApprovalDiffFile.test_file_move_diff` — move diff shows
  operation summary
- `TestBuildApprovalDiffFile.test_file_copy_diff` — copy diff shows
  operation summary

All existing tests updated to use the new `spec`-based API.