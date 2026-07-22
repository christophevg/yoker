# API Design: `read` Offset/Limit Enhancement (MBI-009 T2)

**Date**: 2026-07-22
**Branch**: `feature/read-offset-limit`
**Task**: MBI-009 T2 — Add optional `offset`/`limit` parameters to the `read` tool
**Related**: `analysis/mbi-toolset-coverage.md` (T2.1 line-number format open question)

## Summary

Extend the built-in `read` tool with optional `offset` and `limit` parameters for paginated file reads. The default path is byte-identical to today's behavior — no prefix, no metadata. When offset/limit are used, the response carries an inline `cat -n` line-number prefix and a `content_metadata["read"]` sub-dict describing the slice.

## 1. Verification: Not Yet Implemented

Current `read` signature in `src/yoker/builtin/read.py`:

```python
async def read(
  path: Annotated[str, PathArg("Path to the file to read (or plugin:// URL)")],
  ctx: ToolContext,
) -> ToolResult:
```

Only `path` and `ctx` are accepted. There is no `offset`/`limit`, no line-number prefix, and no `content_metadata` on the result. The tool returns the full file contents via `ToolResult(success=True, result=content)`.

## 2. Proposed Function Signature

```python
async def read(
  path: Annotated[str, PathArg("Path to the file to read (or plugin:// URL)")],
  offset: int | None = None,
  limit: int | None = None,
  ctx: ToolContext,
) -> ToolResult:
```

`offset` and `limit` sit after `path` and before `ctx`. Both default to `None`. The harness continues to bind `ctx` positionally; the two new parameters are keyword/positional with defaults and do not break existing callers.

## 3. Parameter Semantics

| Parameter | Meaning | Default |
|-----------|---------|---------|
| `offset` | 1-indexed line number to start reading from | `None` (start of file) |
| `limit` | Maximum number of lines to return | `None` (all remaining lines) |

- **1-indexed**: `offset=1` reads from the first line (matches `cat -n` numbering and user intuition).
- **Count semantics**: `limit=20` returns up to 20 lines.
- **Both provided**: read `limit` lines starting at line `offset`.
- **Default unchanged**: when both are `None`, the tool returns the full file contents exactly as today — no prefix, no metadata, byte-identical `result` string.

## 4. Return Shape

### Default path (offset and limit both `None`)

Unchanged. `ToolResult.success=True`, `result=<full file contents>`, no `content_metadata`.

### Offset/limit path

`result` is the sliced lines with an inline `cat -n`-style prefix, and `content_metadata["read"]` carries the slice descriptor:

```python
ToolResult(
  success=True,
  result="     1\tfirst line\n     2\tsecond line\n",
  content_metadata={
    "read": {
      "offset": 1,
      "limit": 2,
      "total_lines": 42,
      "returned_lines": 2,
    }
  }
)
```

`cat -n` prefix format: right-aligned line number in a 6-wide field, then a tab, then the line content — matching `cat -n` output (e.g. `     1\tfirst line`).

## 5. Line-Number Format Decision

Inline `cat -n` prefix in the `result` string. This resolves the open question flagged in `analysis/mbi-toolset-coverage.md` (MBI-009 T2.1) about whether line numbers live in `result` vs. `content_metadata`.

Rationale:
- The model reads `result` directly; an inline prefix keeps line references unambiguous in the model's context window without requiring it to cross-reference a separate metadata field.
- `cat -n` is the universally recognized convention — minimal surprise for human reviewers inspecting traces.
- `content_metadata["read"]` carries the structured slice bounds for programmatic consumers (UI pagination, tests).

## 6. Edge Case Handling

| Input | Behavior |
|-------|----------|
| `offset=None`, `limit=None` | Default path. Full file, no prefix, no metadata. Byte-identical to current behavior. |
| `offset=None`, `limit=N` | Read first `N` lines. Prefix applied. Metadata `offset=1`. |
| `offset=N`, `limit=None` | Read from line `N` to EOF. Prefix applied. Metadata `limit=null` or omitted; `returned_lines=total_lines-offset+1`. |
| `offset=N`, `limit=M` | Read `M` lines starting at line `N`. Prefix applied. |
| `offset=0` | Rejected with `ToolResult(success=False, error="offset must be >= 1")`. |
| `limit=0` | Rejected with `ToolResult(success=False, error="limit must be >= 1")`. |
| Negative `offset` or `limit` | Rejected with the same validation error. |
| Non-integer `offset` or `limit` | Rejected by the schema/annotation layer before the function body runs (typed `int | None`); if a value slips through, return `success=False, error="offset/limit must be integers"`. |
| `offset > total_lines` | Return `success=True, result=""`, metadata `returned_lines=0`. Not an error — the slice is empty. |
| `limit` exceeds remaining lines | Return the available lines. `returned_lines` reflects the actual count, not the requested `limit`. |
| `plugin://` URLs | Offset/limit apply to the resolved package resource content, same semantics as filesystem reads. |
| Binary/undecodable content | Existing `errors="replace"` behavior is preserved; offset/limit operate on the decoded text. |

## 7. Files to Modify

| File | Change |
|------|--------|
| `src/yoker/builtin/read.py` | Add `offset`/`limit` parameters; add `_apply_offset_limit(text, offset, limit)` helper; branch in `read()` and `_read_plugin_resource()` to apply the helper when either parameter is non-`None`; populate `content_metadata["read"]` on the offset/limit path. |
| `tests/test_tools/test_read.py` | Extend with cases: default unchanged, offset-only, limit-only, both, offset>total, limit exceeds remaining, zero/negative rejection, `plugin://` with offset/limit, metadata shape. |

No changes to: `config/`, `tools/guardrails/`, `builtin/__init__.py` manifest, `tools/schema.py`, or `tools/annotations.py`. The new parameters are plain typed optionals; no new annotation or guardrail is needed.

## 8. Acceptance Criteria Mapping

| Criterion (from MBI-009 T2) | Met by |
|-----------------------------|--------|
| Optional offset/limit parameters | Section 2 — `int | None = None` on both |
| 1-indexed offset, count-based limit | Section 3 |
| Default behavior unchanged | Section 4 + Section 6 — byte-identical `result`, no metadata when both `None` |
| Line-numbered output when paginated | Section 4 + Section 5 — inline `cat -n` prefix |
| Structured slice metadata | Section 4 — `content_metadata["read"]` with `offset`, `limit`, `total_lines`, `returned_lines` |
| Edge cases defined | Section 6 — validation, empty slice, truncation, `plugin://` |
| No config/guardrail/manifest changes | Section 7 |

## 9. Simplicity

No new classes, no new modules, no new guardrails, no new config fields, no manifest/schema changes. The implementation is one small helper:

```python
def _apply_offset_limit(
  text: str, offset: int | None, limit: int | None
) -> tuple[str, dict]:
  lines = text.splitlines(keepends=True)
  total = len(lines)
  start = (offset or 1) - 1
  end = start + limit if limit is not None else total
  sliced = lines[start:end]
  numbered = "".join(
    f"{i + start + 1:>6}\t{line}" for i, line in enumerate(sliced)
  )
  metadata = {
    "read": {
      "offset": offset or 1,
      "limit": limit,
      "total_lines": total,
      "returned_lines": len(sliced),
    }
  }
  return numbered, metadata
```

The default path (both `None`) bypasses the helper entirely and returns `ToolResult(success=True, result=content)` exactly as today. The helper is only invoked when at least one of `offset`/`limit` is not `None`. Validation (zero, negative, non-integer) runs before the helper.