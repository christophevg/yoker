# Functional Review: read offset/limit (MBI-009 T2)

**Reviewed files:**
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/read.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/tools/test_read.py`

## Acceptance Criteria Verification

| # | Criterion (from TODO.md) | Status | Evidence |
|---|---|---|---|
| 1 | `read(path)` returns all lines byte-identical to prior behavior | PASS | `read.py:168-169` returns `content` unchanged when `offset is None and limit is None`; `test_default_path_unchanged` asserts `result == content` and `content_metadata is None` |
| 2 | `read(path, offset=10)` returns lines 10 to EOF | PASS | `read.py:75-76` computes `start = (offset or 1) - 1`, `end = total`; `test_offset_only` confirms lines 3-5 returned with cat -n prefix |
| 3 | `read(path, limit=5)` returns lines 1 to 5 | PASS | `read.py:75-76` with offset=None → start=0, end=limit; `test_limit_only` confirms lines 1-2 returned |
| 4 | `read(path, offset=10, limit=5)` returns lines 10-14 | PASS | `test_offset_and_limit` creates 20-line file, asserts lines 10-14 with correct prefix and metadata |
| 5 | Total line count in metadata | PASS | `read.py:84` sets `total_lines`; `test_metadata_total_and_returned_lines` asserts `meta["total_lines"] == 8` |
| 6 | Line numbers when offset/limit used (cat -n style) | PASS | `read.py:79` formats `{start + i + 1:>6}\t{line}`; `test_line_number_prefix_format` asserts `"     1\tfirst\n     2\tsecond\n"` |

## Edge Case Coverage

| Edge case | Status | Evidence |
|---|---|---|
| offset=0 rejected | PASS | `_validate_offset_limit` returns "offset must be >= 1"; `test_offset_zero_rejected` confirms success=False |
| limit=0 rejected | PASS | `_validate_offset_limit` returns "limit must be >= 1"; `test_limit_zero_rejected` confirms |
| Negative offset rejected | PASS | Same validator; `test_negative_offset_rejected` confirms |
| Negative limit rejected | PASS | Same validator; `test_negative_limit_rejected` confirms |
| offset beyond EOF | PASS | `test_offset_beyond_eof` — offset=100 on 3-line file returns `result == ""`, `returned_lines=0`, `success=True` |
| limit exceeds remaining | PASS | `test_limit_exceeds_remaining` — offset=2, limit=50 on 3-line file returns lines 2-3, no padding |
| bool rejected as int | PASS | `_validate_offset_limit` explicitly rejects `isinstance(offset, bool)` (Python bool is int subclass) |
| Non-int offset/limit | PASS | `isinstance(offset, int)` check returns "offset must be an integer" |
| Validation before I/O | PASS | `_validate_offset_limit` called at `read.py:41` before any file access |

## Owner's Proposal Satisfaction

Owner's proposal (quoted from task): *"Add offset/limit params; skip to line (1-indexed); return at most N lines; total line count in metadata; line numbers included when offset/limit used."*

- "Add offset/limit params" — PASS: signature `read(path, ctx, offset=None, limit=None)`; schema exposes both as `integer` (verified via `build_tool_spec` output).
- "skip to line (1-indexed)" — PASS: `start = (offset or 1) - 1` (1-indexed → 0-indexed slice).
- "return at most N lines" — PASS: `end = start + limit if limit is not None else total`; slicing naturally caps.
- "total line count in metadata" — PASS: `total_lines` in `content_metadata["read"]`.
- "line numbers included when offset/limit used" — PASS: cat -n style prefix applied only when offset or limit provided.

## Default Path Byte-Identical Behavior

PASS. When `offset is None and limit is None`, the code path at `read.py:168-169` returns `ToolResult(success=True, result=content)` with no `content_metadata` and no line-number prefix. The `test_default_path_unchanged` and `test_existing_default_assertions_still_pass` tests assert raw content equality and `content_metadata is None`. Existing tests (TestReadTool class, 15 tests) all pass unchanged — confirming no regression in the default path.

## plugin:// URL Support

PASS. `_read_plugin_resource` (read.py:91-134) handles `plugin://` URLs. When offset/limit are both None, returns raw content; otherwise applies `_apply_offset_limit`. `test_plugin_url_with_offset_limit` reads `plugin://yoker/builtin/__init__.py` with offset=1, limit=2 and verifies cat -n prefix, metadata, and line counts.

## Parameter Order Deviation

The developer placed `ctx` before `offset`/`limit`: `read(path, ctx, offset=None, limit=None)` instead of the design doc's `read(path, offset=None, limit=None, ctx)`. This is a Python syntax requirement — non-default parameter `ctx` cannot follow defaulted parameters. The harness binds `ctx` by position (injected) and `offset`/`limit` by keyword (from LLM calls), so call sites are unaffected. This is an earned deviation, explicitly noted in the task. Approved.

## Schema Exposure

Verified via `build_tool_spec` runtime introspection: the tool's JSON schema exposes `offset` and `limit` as optional `integer` properties with `path` as the only required field. The LLM can discover and use both parameters.

## Test Coverage

32 tests total, all passing:
- 15 existing tests (TestReadTool) — no regressions in default behavior.
- 17 new tests (TestReadOffsetLimit) — cover all acceptance criteria, all edge cases, line-number format, metadata fields, and plugin:// URL integration.

## No Regressions

`make test` (via `pytest tests/tools/test_read.py`): 32 passed, 0 failed. Existing TestReadTool tests unchanged and passing.

## Verdict

**APPROVED.** All six acceptance criteria met. All edge cases handled. Default path byte-identical. plugin:// URLs work with offset/limit. Schema exposes new parameters. Owner's proposal satisfied in full. Parameter order deviation is earned (Python syntax requirement). No regressions.