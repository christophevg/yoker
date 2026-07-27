# Testing-Engineer Review — `protected_files` Guardrail (MBI-009 T12)

**Stage c — Quality review (testing focus)**
**Branch:** feature/protected-files
**Verdict: APPROVED** (with non-blocking observations)

## Summary

39 tests across three files, all passing. The suite is behavior-focused,
covers the core guardrail matching, the interactive approval hook, and both
UI handler implementations. It verifies every one of the owner's accepted
proposals (1–8) at the unit level. Three integration-level gaps are noted
below; none warrant rejection given the strength of the unit coverage and
the cost of full end-to-end infrastructure.

## Test files reviewed

- `tests/tools/test_path_guardrail_protected.py` — 15 tests, PathGuardrail logic
- `tests/test_core/test_protected_files_approval.py` — 14 tests, approval hook + diff helper
- `tests/test_ui/test_confirm_approval.py` — 10 tests, UIHandler.confirm_approval

## Owner's proposals — coverage verification

| # | Proposal | Covered by | Verdict |
|---|----------|-----------|---------|
| 1 | filename-based check on write and update (not read) | `TestProtectedFilesDefault` (write + update), `TestProtectedFilesReadNotChecked` | ✅ |
| 2 | protected_files check before extension check | Implicit — `Makefile` (no extension) is blocked; `.toml` is in default allowed_extensions yet `pyproject.toml` is still blocked | ✅ (implicit; see obs. 5) |
| 3 | read tool unchanged | `test_read_makefile_not_blocked_by_protected` | ✅ |
| 4 | empty list disables all protections | `TestProtectedFilesEmpty` (write + update); `test_is_protected_respects_empty_list` | ✅ |
| 5 | SOFT guardrail semantics | Reflected in test assertions (`"protected" in reason.lower()`); no test claims malicious-agent protection | ✅ |
| 6 | Option A: interactive approve-on-diff | `TestProtectedFilesInteractiveSkip`, `test_approval_approved/denied/...`, `test_interactive_confirm_approval_*` | ✅ |
| 7 | fnmatch glob matching | `test_glob_matches_git_hooks`, `test_glob_matches_github_workflows`, `test_basename_match_at_depth` | ✅ |
| 8 | yoker.toml + expanded scope in denylist | `_DEFAULT_CASES` enumerates all 16 entries incl. `yoker.toml`, `Justfile`, `Taskfile.yml`, `uv.lock`, `poetry.lock`, `.github/workflows/ci.yml` | ✅ |

## What the tests verify well

**Guardrail matching**
- Every default denylist entry blocks both write and update (parametrized over 16 entries).
- Glob patterns `.git/hooks/*` and `.github/workflows/*.yml` match real files.
- Basename match at arbitrary depth (`subdir/deep/Makefile`).
- Empty tuple disables protections on write, update, and `is_protected`.
- `is_protected` public entry point: true for protected, false for normal, false for empty-list, true for unresolvable path (basename fallback).
- `interactive_approvals=True` skips the simple block on write and update.

**Approval hook (`_maybe_block_protected`)**
- Non-write tool → no approval needed.
- No handler wired → returns None (simple block fallback).
- Path not protected → returns None.
- Approved → returns None (fall through to execute).
- Denied → returns blocked `(message, False, None)` with path in message.
- Handler raises → fail-safe denial.
- Namespaced tool name (`yoker:write`) handled via `split(":")`.

**Diff helper (`generate_diff` + `_build_approval_diff`)**
- Identical content → empty diff.
- Modified line, new file (all additions), write overwrite, update replace, update delete — all assert expected `+`/`-` lines.

**UI handlers**
- `BatchUIHandler.confirm_approval` always False (with diff and with empty diff).
- `InteractiveUIHandler.confirm_approval`: `y`, `yes`, `Y` → True; `n`, empty, EOF, Ctrl+C → False.
- Diff content is rendered before prompting.
- Fail-safe on EOF/Ctrl+C/empty is explicitly tested — this is security-critical and correctly verified.

## Non-blocking observations (gaps)

### 1. `insert_before` / `insert_after` diff path not tested

`_build_approval_diff` has an `else` branch (line 930 in `_processing.py`) that
sets `new_content = new_string` for any operation other than `replace`/`delete`.
For `insert_before`/`insert_after`, `new_string` is the content to insert, not
the full resulting file — so the diff shown to the user would be misleading
(just the insert fragment as additions, not the file with the insertion
applied). No test exercises this branch. A `test_update_insert_before_diff`
and `test_update_insert_after_diff` would catch a regression here and pin down
the expected display behavior. **Recommended addition.**

### 2. `_wire_approval_handler` wiring logic not tested

The CLI integration point in `cli/chat.py` (lines 123–141) is untested. It
encodes three decisions: (a) `BatchUIHandler` → don't wire (let simple block
fire); (b) no `confirm_approval` attr → don't wire; (c) otherwise → wire
handler and set `interactive_approvals = True`. The individual pieces are all
tested in isolation, but the wiring itself — which determines whether
interactive mode actually activates the approval flow — has no test. A small
test with a fake `UIHandler` (has/doesn't-have `confirm_approval`) and a
`BatchUIHandler` would close this. **Recommended addition.**

### 3. End-to-end flow through `_run_tool` not tested

The full path (write to protected file → guardrail skips simple block →
`_maybe_block_protected` invokes handler → diff rendered → approval → execute
or deny) is tested in pieces but not as a single flow through `_run_tool`. The
`_maybe_block_protected` tests with `_FakeAgent` are close but bypass
`_run_tool`'s guardrail validation and tool execution. A full integration test
would require a real `Agent` with tools, guardrails, and a stub handler —
non-trivial infrastructure. The unit coverage is strong enough that this is
**nice-to-have, not blocking.**

### 4. Case sensitivity not explicitly tested

`fnmatch.fnmatchcase` is used (case-sensitive), so `Makefile` does not match
`MAKEFILE`. The default list includes both `Makefile` and `makefile` but not
`MAKEFILE`. No test verifies that `MAKEFILE` passes through. Minor edge case;
the behavior is correct per `fnmatchcase` semantics, but a one-line assertion
would document the intent. **Optional.**

### 5. Ordering (protected before extension) is implicit

Proposal 2 (protected_files check before extension check) is verified only
indirectly: `Makefile` has no extension so the extension check would pass
anyway, and `pyproject.toml` is blocked by protected_files before the
`.toml` extension check. No test constructs a file that is BOTH
extension-blocked AND protected to assert which reason wins. The
implementation order is correct (protected check at lines 172–175 / 198–201,
extension check after). **Optional.**

### 6. Symlinks not tested

A symlink pointing to a protected file should be resolved via
`os.path.realpath` and blocked. The resolution logic is shared with the rest
of the guardrail and is tested elsewhere, but no protected-files-specific
symlink test exists. **Optional.**

## Test quality observations

- **Behavior, not implementation:** tests assert on `result.valid`,
  `result.reason`, return tuples, and rendered output — not on internal
  state. Good.
- **Fail-safe verification:** EOF, Ctrl+C, empty response, and handler
  exceptions are all explicitly tested as denials. This is the
  security-critical path and it is well covered.
- **Flexible assertions:** `"protected" in reason.lower() or "blocked
  pattern" in reason.lower()` correctly accommodates the pre-existing
  `\.git` blocked_pattern that fires before the protected_files check for
  `.git`/`.github` paths. Pragmatic.
- **Minor dead code:** `test_blocks_each_default_on_write` lines 44–46 have
  a skip guard (`if not full.suffix and full == full.parent: continue`) that
  never fires for non-root paths. Harmless but unused.
- **No over-mocking:** `_FakeAgent` and `_FakeGuardrail` are minimal stand-ins
  exposing exactly the attributes the hook reads. The `_make_interactive_handler`
  helper stubs only `prompt_async`. Appropriately tight.

## Coverage of new code paths

| Code path | Tested |
|-----------|--------|
| `PathGuardrail._check_protected_files` | ✅ |
| `PathGuardrail._relative_for_protected` (root match + basename fallback) | ✅ |
| `PathGuardrail.is_protected` | ✅ (4 tests) |
| `interactive_approvals` flag skip on write/update | ✅ |
| `generate_diff` (identical, modified, new file) | ✅ |
| `_build_approval_diff` (write new, write overwrite, update replace, update delete) | ✅ |
| `_build_approval_diff` (insert_before, insert_after) | ❌ (gap 1) |
| `_maybe_block_protected` (7 scenarios) | ✅ |
| `BatchUIHandler.confirm_approval` | ✅ |
| `InteractiveUIHandler.confirm_approval` (8 scenarios) | ✅ |
| `_wire_approval_handler` (3 branches) | ❌ (gap 2) |
| Full `_run_tool` → approval → execute/deny | ❌ (gap 3) |

## Verdict

**APPROVED.** The tests are behavior-focused, tightly written, and cover all
eight owner-approved proposals at the unit level. The fail-safe paths
(EOF/Ctrl+C/exception/empty) are correctly verified — the security-critical
concern. The three gaps (insert diff path, wiring logic, end-to-end flow)
are integration-level and recommended as follow-ups, not blockers. The core
guardrail matching and approval logic is sufficiently covered to prevent
regressions.

**Recommended follow-up tests (non-blocking):**
1. `test_update_insert_before_diff` / `test_update_insert_after_diff`
2. `test_wire_approval_handler_skips_batch` / `test_wire_approval_handler_wires_interactive`
3. `test_wire_approval_handler_skips_handler_without_confirm_approval`