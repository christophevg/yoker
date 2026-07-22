# Testing Review: `read` offset/limit (MBI-009 T2)

**Reviewer:** testing-engineer
**Date:** 2026-07-22
**Files reviewed:**
- `src/yoker/builtin/read.py` (implementation)
- `tests/tools/test_read.py` (tests, `TestReadOffsetLimit` class)

## Verdict: approved (one minor gap noted)

The test suite is meaningful, behavior-focused, and covers the acceptance criteria from `analysis/api-read-offset-limit.md` Section 8. All 32 tests in `tests/tools/test_read.py` pass. Assertions check concrete values (exact rendered strings, full metadata dicts), not smoke-test presence. The one gap is non-integer / `bool` type rejection (see Gaps below).

## Acceptance criteria coverage

| Criterion (API doc Section 8) | Test(s) | Covered |
|-------------------------------|---------|---------|
| Optional offset/limit parameters | `test_offset_only`, `test_limit_only`, `test_offset_and_limit` | yes |
| 1-indexed offset, count-based limit | `test_offset_only` (offset=3 returns l3-l5), `test_offset_and_limit` (lines 10-14) | yes |
| Default behavior unchanged (byte-identical, no metadata) | `test_default_path_unchanged`, `test_existing_default_assertions_still_pass` | yes |
| Line-numbered output when paginated | `test_line_number_prefix_format`, `test_offset_only`, `test_limit_only` | yes |
| Structured slice metadata (`offset`, `limit`, `total_lines`, `returned_lines`) | `test_metadata_total_and_returned_lines` + every offset/limit test asserts the full dict | yes |
| Edge cases defined (validation, empty slice, truncation, plugin://) | see Edge cases table below | yes (with one gap) |
| No config/guardrail/manifest changes | N/A — verified by reading `read.py`; no new annotations/guardrails | yes |

## Edge case coverage

| Edge case (checklist) | Test | Status |
|----------------------|------|--------|
| offset=0 | `test_offset_zero_rejected` | covered |
| limit=0 | `test_limit_zero_rejected` | covered |
| negative offset | `test_negative_offset_rejected` | covered |
| negative limit | `test_negative_limit_rejected` | covered |
| offset beyond EOF | `test_offset_beyond_eof` (offset=100 on 3-line file asserts empty result + returned_lines=0) | covered |
| limit exceeds remaining | `test_limit_exceeds_remaining` (offset=2, limit=50 on 3-line file) | covered |
| non-integer types | none | **gap** |
| bool rejection (True/False) | none | **gap** (subset of above) |

## cat -n format verification

`test_line_number_prefix_format` asserts the exact prefix `"     1\tfirst\n     2\tsecond\n"` — 6-wide right-aligned, tab-separated, correct line numbers. `test_offset_only` asserts `"     3\tl3\n     4\tl4\n     5\tl5\n"`, confirming line numbers carry the real (post-offset) value, not a slice-local counter. `test_offset_and_limit` builds the expected string programmatically (`f"{i:>6}\tline{i}\n"`), cross-checking the implementation's own format. Format is well-verified.

## Metadata shape verification

`test_metadata_total_and_returned_lines` asserts all four fields individually (`total_lines`, `returned_lines`, `offset`, `limit`). The other offset/limit tests assert the full `content_metadata` dict via equality, which implicitly verifies the shape and all four keys. Shape is well-verified.

## Default path / backward compat

`test_default_path_unchanged` and `test_existing_default_assertions_still_pass` both assert `result.result == content` (raw, byte-identical) and `result.content_metadata is None`. Backward compatibility is verified.

## plugin:// URL with offset/limit

`test_plugin_url_with_offset_limit` reads `plugin://yoker/builtin/__init__.py` with offset=1, limit=2. Asserts `offset`, `limit`, `returned_lines == 2`, `total_lines >= 2`, and `result.result.startswith("     1\t")`. The `>= 2` on total_lines is appropriately loose (the package file may change over time), while `returned_lines == 2` and the prefix check are tight. Good integration test.

## Test quality

All tests use real files in `tmp_path` and exercise the full `spec.execute(...)` path (registry → ToolSpec → `read` function), not internal helpers. No over-mocking. Assertions are on observable behavior (result string, metadata dict, success flag). Each test targets one concept. Tests would catch real bugs (off-by-one in slicing, wrong prefix width, metadata shape drift, validation regression).

## Gaps

### 1. Non-integer / bool type rejection (minor)

`_validate_offset_limit` (read.py:51-63) explicitly guards two cases that have no test:

```python
if not isinstance(offset, int) or isinstance(offset, bool):
  return "offset must be an integer"
```

The `isinstance(offset, bool)` guard is deliberate: `bool` subclasses `int` in Python, so `isinstance(True, int)` is `True` — without the guard, `offset=True` would silently be treated as `offset=1`. The API doc (Section 6) lists non-integer rejection as an edge case. No test exercises `offset="3"`, `offset=1.5`, or `offset=True`.

**Severity:** low. The typed signature (`offset: int | None`) and JSON schema layer reject non-int values before the function body in normal tool invocation. The function-level guard is defense-in-depth for direct Python callers (and the `bool` trap). A regression here would not affect model-driven tool calls.

**Recommended additions (optional):**
- `test_non_integer_offset_rejected` — pass `offset="3"`, assert `success is False`, `"integer" in error`.
- `test_bool_offset_rejected` — pass `offset=True`, assert `success is False` (guards the deliberate `bool` trap).

### 2. Empty file with offset/limit (very minor)

No test reads a zero-byte file with offset/limit set. `splitlines(keepends=True)` on `""` returns `[]`, so `total_lines=0`, `returned_lines=0`, `result=""`. Worth one test for completeness; the code path is the same as offset-beyond-EOF which is already tested.

### 3. File without trailing newline (very minor)

`splitlines(keepends=True)` handles `"a\nb\nc"` as 3 lines (last without newline). Not explicitly tested with offset/limit. Low risk — `splitlines` is stdlib.

## Notes

- The TODO.md path reference (`tests/test_builtin/test_read.py`) does not match the actual test location (`tests/tools/test_read.py`). This is a TODO.md doc drift, not a test issue.
- `test_offset_zero_rejected` and `test_limit_zero_rejected` assert `">=" in result.error` — this is contract-level (the API doc specifies the exact error format `"offset must be >= 1"`), so exact-substring matching is appropriate here, not a violation of the "don't test exact strings" guideline.
- `test_plugin_url_with_offset_limit` uses `total_lines >= 2` rather than an exact value. This is the right call — the package file is a living artifact and pinning its line count would make the test fragile.