# API Design: search Enhancements (MBI-009 T3, Tier 1)

**Date:** 2026-07-22
**Task:** MBI-009 T3 — Add context lines, case-insensitive, file-type filter, count mode to `search`
**Source:** `analysis/mbi-toolset-coverage.md` §7.3, TODO.md `search` enhancements
**Status:** Design ready for implementation

---

## 1. Summary

Add six optional parameters to the existing `search` tool, all defaulted to preserve byte-identical default behavior. No new classes, modules, or guardrails — the existing `PathGuardrail` on `path` already covers the security surface. The result dict is enriched in-place; `content_metadata` (flat shape) is emitted only on the enhanced path so the UI can render grep-style output.

**Coverage gained:** ~147 grep commands (30.8% of recorded Bash usage).

---

## 2. Current State

### 2.1 Current Function Signature

```python
async def search(
  path: Annotated[str, PathArg("Directory to search in")],
  ctx: ToolContext,
  pattern: Annotated[str, Text("Search pattern. For 'content' type: regex pattern. For 'filename' type: glob pattern (e.g., '*.py')")] = "",
  type: str = "content",
  max_results: int | None = None,  # None means use config default
  timeout_ms: int | None = None,    # None means use config default
) -> ToolResult:
```

### 2.2 Current Return Shape

```python
# content search
ToolResult(success=True, result={
  "matches": [{"file": str, "line": int, "content": str}, ...],
  "total_matches": int,
  "truncated": bool,
  "files_searched": int,
})
# filename search
ToolResult(success=True, result={
  "matches": [{"file": str}, ...],
  "total_matches": int,
  "truncated": bool,
})
```

No `content_metadata` is emitted. `SearchToolConfig` has `max_results` (default 500) and `timeout_ms` (default 10000). No config changes are needed for the 6 new parameters — they are all per-call parameters with hardcoded caps, not tunable config.

### 2.3 Verification

None of the 6 new parameters exist in `src/yoker/builtin/search.py` (confirmed via grep — zero matches for `case_insensitive`, `context_before`, `context_after`, `include_pattern`, `exclude_pattern`, `count_only`).

---

## 3. Proposed Function Signature

```python
async def search(
  path: Annotated[str, PathArg("Directory to search in")],
  ctx: ToolContext,
  pattern: Annotated[
    str,
    Text(
      "Search pattern. For 'content' type: regex pattern. "
      "For 'filename' type: glob pattern (e.g., '*.py')"
    ),
  ] = "",
  type: str = "content",
  max_results: int | None = None,
  timeout_ms: int | None = None,
  # NEW — MBI-009 T3:
  case_insensitive: bool = False,    # -i flag: case-insensitive regex/glob matching
  context_before: int = 0,           # -B flag: lines of context before each match (capped at 20)
  context_after: int = 0,            # -A flag: lines of context after each match (capped at 20)
  include_pattern: str = "",         # --include: glob filter for files to search (e.g., "*.py")
  exclude_pattern: str = "",          # --exclude: glob filter for files to skip (e.g., "*.pyc")
  count_only: bool = False,           # -c flag: return per-file counts only, no matched content
) -> ToolResult:
```

### 3.1 Parameter Ordering Rationale

Python requires non-default parameters before default parameters. `path` is required (no default), `ctx` is required (no default, injected by the harness). All other parameters have defaults. The 6 new parameters are appended after the existing defaulted parameters, preserving the existing signature order and keeping the diff minimal. `ctx` remains in position 2 — it must come before all defaulted parameters, which it does.

---

## 4. Parameter Semantics

### 4.1 `case_insensitive: bool = False`

- **Content search:** compiles the regex with `re.IGNORECASE`. Implemented by passing `re.IGNORECASE` to `re.compile(pattern, flags=...)`.
- **Filename search:** uses `fnmatch.fnmatch` which is already case-insensitive on some platforms; to make it deterministic, use `fnmatch.fnmatch(file_path.name.lower(), pattern.lower())` when `case_insensitive=True`.
- **Validation:** boolean; no cap. Coerce non-bool truthy/falsy via `bool()` if needed (harness passes JSON types, so it arrives as `bool`).

### 4.2 `context_before: int = 0` and `context_after: int = 0`

- **Meaning:** number of lines of context to include before/after each matched line in content search results.
- **Only applies to `type="content"`** — ignored for filename search (filename matches have no line context).
- **Cap at 20:** enforced by clamping, NOT by validation error. Rationale: "cap to prevent output flooding" is a safety measure, not a user error. Clamping is friendlier and matches the existing `_clamp` pattern used for `max_results` and `timeout_ms`.
  ```python
  effective_context_before = _clamp(int(context_before), 0, MAX_CONTEXT_LINES)  # MAX_CONTEXT_LINES = 20
  effective_context_after = _clamp(int(context_after), 0, MAX_CONTEXT_LINES)
  ```
- **Negative values:** clamped to 0 (no context).
- **Match dict enrichment:** when either is > 0, each match dict gains two keys:
  ```python
  {
    "file": str,
    "line": int,
    "content": str,           # the matched line (stripped, as today)
    "context_before": [str, ...],  # up to N lines before the match (unstripped, with line numbers)
    "context_after": [str, ...],   # up to N lines after the match (unstripped, with line numbers)
  }
  ```
  Context lines are rendered `cat -n` style: `"{line_num:>6}\t{line_text}"` (same format as the `read` tool's offset/limit output, for cross-tool consistency). Each entry is a string like `"   123\tdef foo():"`.
- **Boundary:** at file start/end, fewer than requested context lines are returned (natural clamping by file boundaries, no error).

### 4.3 `include_pattern: str = ""` and `exclude_pattern: str = ""`

- **Meaning:** glob patterns to filter which files are searched. Applied during `_walk_files` (or in `_search_content`/`_search_filename` before reading the file).
- **`include_pattern`** (e.g., `"*.py"`): only search files matching this glob. Empty string = no include filter (search all files).
- **`exclude_pattern`** (e.g., `"*.pyc"`): skip files matching this glob. Empty string = no exclude filter.
- **Both can be set:** a file is searched iff it matches `include_pattern` (or include is empty) AND does NOT match `exclude_pattern` (or exclude is empty).
- **Matching:** uses `fnmatch.fnmatch(file_path.name, pattern)` against the filename (not the full path). This is consistent with grep's `--include`/`--exclude` semantics.
- **Applies to both content and filename search types** — it filters the file set before the search runs.
- **Validation:** glob patterns are not regex; no ReDoS concern. No validation needed beyond the existing `MAX_PATTERN_LENGTH` check (apply the same 500-char cap to these for consistency).

### 4.4 `count_only: bool = False`

- **Meaning:** return only per-file match counts, not the matched line content. Equivalent to `grep -c`.
- **Only applies to `type="content"`** — for filename search, count_only has no meaningful effect (filename matches are already just paths; `total_matches` already gives the count). If `count_only=True` with `type="filename"`, treat it as a no-op (return the same shape as default filename search) — or, cleaner, ignore it with a warning log. Decision: **ignore silently** for filename search (simplest; the count is already in `total_matches`).
- **Result shape when `count_only=True` (content search):**
  ```python
  {
    "success": True,
    "counts": {"<file_path>": <int>, ...},  # per-file match counts
    "total_matches": int,                    # sum across files
    "truncated": bool,
    "files_searched": int,
    # NO "matches" key — content is omitted
  }
  ```
- **`max_results` interaction:** `max_results` caps the matches list, but `count_only` removes the matches list entirely. `total_matches` still reflects the true count (may exceed `max_results`); `truncated` is set if the count was capped by timeout (not by max_results, since we don't collect matches). For count_only, we count all matches without storing them, so `max_results` does not cause truncation — only timeout does.
- **Context lines interaction:** `context_before`/`context_after` are meaningless with `count_only=True` (no content to show context around). If both are set, `count_only` wins — context lines are not collected (saves memory). Log a warning if both are set together.

### 4.5 `case_insensitive` Interaction with `count_only`

Independent. `case_insensitive=True, count_only=True` is valid: count case-insensitive matches per file.

---

## 5. Context Line Cap (MAX_CONTEXT_LINES = 20)

### 5.1 Where Enforced

Clamping in the parameter-processing section of `search()`, alongside the existing `max_results`/`timeout_ms` clamping:

```python
MAX_CONTEXT_LINES: int = 20  # module-level constant

# inside search():
try:
  effective_context_before = _clamp(int(context_before), 0, MAX_CONTEXT_LINES)
  effective_context_after = _clamp(int(context_after), 0, MAX_CONTEXT_LINES)
except (ValueError, TypeError):
  return ToolResult(success=False, error="Invalid numeric parameter")
```

### 5.2 Why Clamping (Not Validation Error)

- The cap exists to prevent output flooding, not to enforce a contract. A user requesting 30 lines of context gets 20 — useful, not an error.
- Consistent with the existing `_clamp` pattern for `max_results` (capped at `ABSOLUTE_MAX_RESULTS=1000`) and `timeout_ms` (capped at `ABSOLUTE_TIMEOUT_MS=30000`).
- No error path means no new error message to test/document.

---

## 6. Return Shape and `content_metadata`

### 6.1 Default Path — Byte-Identical

When all 6 new parameters are at defaults (`case_insensitive=False, context_before=0, context_after=0, include_pattern="", exclude_pattern="", count_only=False`):

- `ToolResult(success=True, result={same dict as today})` — NO `content_metadata`.
- The `result` dict is structurally identical to the current output. Match dicts have exactly `{file, line, content}` (content search) or `{file}` (filename search).
- This guarantees zero regression for existing callers and tests.

### 6.2 Enhanced Path — Flat `content_metadata`

When any of the 6 new parameters is non-default, emit `content_metadata` using the flat shape consumed by `core/_processing.py:441-453`:

```python
content_metadata = {
  "operation": "search",
  "path": str(resolved),
  "content_type": "text/plain",
  "content": _render_search_text(...),  # grep-style text rendering (see §6.3)
  "metadata": {
    "type": search_type,
    "pattern": search_pattern,
    "matches": matches,           # enriched match dicts (with context keys if applicable)
    "total_matches": total,
    "truncated": truncated,
    "files_searched": files_searched,  # content search only; absent for filename search
    "case_insensitive": effective_case_insensitive,
    "context_before": effective_context_before,
    "context_after": effective_context_after,
    "include_pattern": include_pattern,
    "exclude_pattern": exclude_pattern,
    "count_only": count_only,
    "counts": counts if count_only else None,  # per-file counts, only in count_only mode
  }
}
return ToolResult(success=True, result=result_dict, content_metadata=content_metadata)
```

**Why emit `content_metadata` on the enhanced path:**
- Consistent with `read` (emits content_metadata when offset/limit is used) and `update` (always emits content_metadata).
- The flat shape is required because `core/_processing.py:441-453` reads flat keys (`operation`, `path`, `content_type`, `content`, `metadata`) — nesting them differently causes the `ToolContentEvent` to carry wrong data (the C1 bug from `read` offset/limit).
- The `result` dict is still set (LLM consumes `str(result)`); `content_metadata` gives the UI a structured grep-style rendering.

### 6.3 `_render_search_text` — grep-style text content

Renders the search results as grep-style text for the `content` field of `content_metadata`:

```
main.py:3:    # TODO: implement main
utils.py:1:# TODO: add docstrings
```

For content search with context lines:
```
main.py-1-def main():
main.py:2:    # TODO: implement main
main.py-3-    pass
```
(matched line uses `:` separator, context lines use `-` separator — standard grep convention).

For `count_only=True`:
```
main.py:1
utils.py:1
README.md:1
```

For filename search:
```
main.py
utils.py
README.md
```

If there are no matches, `content` is an empty string.

### 6.4 `result` Dict Shape (Enhanced Path)

The `result` dict (what the LLM sees via `str(result)`) is the same structure as the default path, enriched:

- **Content search with context:** match dicts gain `context_before` and `context_after` keys (lists of `cat -n`-style strings). Other keys unchanged.
- **Content search with count_only:** `matches` key is omitted (or set to empty list); `counts: {file: int}` key is added.
- **Content search with case_insensitive / include / exclude (no context, no count_only):** `result` dict is structurally identical to default (same keys), but `content_metadata` is still emitted (with the flag values recorded in `metadata`).
- **Filename search:** `result` dict unchanged in structure; `content_metadata.metadata` records the active flags.

---

## 7. Implementation Plan

### 7.1 Files to Modify

- `src/yoker/builtin/search.py` — add 6 parameters, `MAX_CONTEXT_LINES` constant, `_render_search_text` helper, enrich `_search_content`/`_search_filename` signatures, wire `content_metadata`.

### 7.2 No Other Files Need Changes

- **Config (`src/yoker/config/__init__.py`):** NO change. The 6 new parameters are per-call with hardcoded caps, not tunable config. `SearchToolConfig` stays as-is.
- **Manifest (`src/yoker/builtin/__init__.py`):** NO change. The `search` tool is already declared; adding parameters to the function signature automatically updates the schema via `build_tool_spec()` introspection.
- **Guardrails:** NO change. `PathGuardrail` already applies to the `path` parameter. The new parameters don't introduce path-like or URL-like arguments — `include_pattern`/`exclude_pattern` are glob strings applied to filenames within the already-guarded search root, not new path arguments.
- **Consumer (`core/_processing.py`):** NO change. It already handles `content_metadata` with flat keys.

### 7.3 Implementation Steps

1. Add `MAX_CONTEXT_LINES: int = 20` module constant.
2. Extend the `search()` signature with 6 new defaulted parameters.
3. In `search()`, after the existing `effective_max_results`/`effective_timeout_ms` clamping, add clamping for `context_before`/`context_after` (0..20) and `bool()` coercion for `case_insensitive`/`count_only`.
4. Determine `enhanced = (case_insensitive or context_before > 0 or context_after > 0 or include_pattern or exclude_pattern or count_only)`.
5. Pass the 6 effective values through to `_search_content`/`_search_filename` (extend their signatures).
6. In `_search_content`:
   - Compile regex with `re.IGNORECASE` if `case_insensitive`.
   - Filter files via `fnmatch.fnmatch(file_path.name, include_pattern)` / `exclude_pattern` before reading (can be done in `_walk_files` or inline).
   - When `count_only=True`: count matches per file, don't collect match dicts; return `counts` dict instead of `matches` list.
   - When `context_before`/`context_after` > 0: read all lines into a list, on match extract the surrounding slice, render context lines `cat -n` style.
7. In `_search_filename`: apply `include_pattern`/`exclude_pattern` as an additional filter on top of the glob `pattern` match. `case_insensitive` lowers both sides for `fnmatch`.
8. Build `result` dict (enriched or default-shaped).
9. If `enhanced`, build `content_metadata` (flat shape) via `_render_search_text` + metadata dict; return `ToolResult(result=..., content_metadata=...)`.
10. If not `enhanced`, return `ToolResult(result=...)` with no `content_metadata` (byte-identical to current).

### 7.4 `_walk_files` Filtering

The cleanest integration point for `include_pattern`/`exclude_pattern` is inside `_walk_files`, adding two optional parameters:

```python
def _walk_files(
  root: Path,
  include_pattern: str = "",
  exclude_pattern: str = "",
) -> Iterator[Path]:
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
    for filename in filenames:
      if filename.startswith("."):
        continue
      if include_pattern and not fnmatch.fnmatch(filename, include_pattern):
        continue
      if exclude_pattern and fnmatch.fnmatch(filename, exclude_pattern):
        continue
      yield Path(dirpath) / filename
```

This keeps the filtering in one place and applies to both content and filename search. For filename search, `include_pattern`/`exclude_pattern` act as additional filters on top of the `pattern` glob (a file must match `include_pattern` AND match the search `pattern`, and not match `exclude_pattern`).

---

## 8. Edge Cases and Interactions

| Scenario | Behavior |
|----------|----------|
| `case_insensitive=True` alone (content) | Same result shape, regex compiled with `IGNORECASE`. `content_metadata` emitted with `case_insensitive: True`. |
| `context_before=5, context_after=5` | Match dicts gain `context_before`/`context_after` lists (up to 5 `cat -n` lines each). |
| `context_before=50` | Clamped to 20 silently. |
| `context_before=-3` | Clamped to 0. |
| `include_pattern="*.py"` | Only `.py` files searched. |
| `exclude_pattern="test_*"` | Files matching `test_*` skipped. |
| `include_pattern="*.py", exclude_pattern="*_test.py"` | `.py` files except `*_test.py`. |
| `count_only=True` | No `matches` list; `counts: {file: int}` returned. `content_metadata.content` is grep-c-style text. |
| `count_only=True, context_before=5` | `count_only` wins — no context collected. Warning logged. |
| `count_only=True, type="filename"` | Ignored for filename search (filename results are already count-like). `total_matches` is the count. |
| `include_pattern` with `type="filename"` | Include filter applied as additional filter on top of the `pattern` glob. |
| All 6 at defaults | Byte-identical to current `search()` output (no `content_metadata`). |
| Timeout during context collection | `truncated=True`; partial results returned with whatever context was collected. |

---

## 9. RESTful / API Compliance

This is a tool function (not an HTTP endpoint), so RESTful constraints don't directly apply. The design follows the existing tool-function conventions: noun-oriented parameter names, boolean flags for mode switches, no verb-encoded operations. The `count_only` flag is a mode switch (analogous to grep's `-c`), not an RPC-style action verb.

---

## 10. Security

No new security surface.

- **PathGuardrail:** already applies to `path` (the search root). No new path-like parameters.
- **`include_pattern`/`exclude_pattern`:** glob strings applied to filenames within the already-guarded search root. No path traversal risk — they filter filenames, they don't resolve paths. The existing 500-char `MAX_PATTERN_LENGTH` cap (reused) prevents pattern abuse. Glob patterns are not regex, so no ReDoS concern.
- **`case_insensitive`:** no security implication; just a regex flag.
- **`context_before`/`context_after`:** capped at 20; the existing `MAX_FILE_SIZE_KB=500` and per-file read limits still apply. Context lines come from already-read file content, no additional I/O.
- **`count_only`:** reduces output; no security concern.

---

## 11. Testing

### 11.1 Test File

`tests/test_tools/test_search.py` (extend existing).

### 11.2 Test Cases

- `case_insensitive=True` matches "Foo" and "foo" for pattern `"foo"`.
- `context_before=2, context_after=2` returns 2 lines before/after each match, rendered `cat -n` style.
- `context_before=50` is clamped to 20 (verify 20 context lines max).
- `context_before=-5` is clamped to 0 (no context).
- `include_pattern="*.py"` searches only `.py` files.
- `exclude_pattern="*.md"` skips `.md` files.
- `include_pattern="*.py", exclude_pattern="test_*"` applies both filters.
- `count_only=True` returns `counts` dict, no `matches` list.
- `count_only=True, context_before=5` — count_only wins, no context collected.
- Default path (all 6 at defaults) — byte-identical result dict, no `content_metadata`.
- Enhanced path — `content_metadata` emitted with flat shape (verify `operation`, `path`, `content_type`, `content`, `metadata` keys).
- `content_metadata.content` for content search is grep-style text.
- `content_metadata.content` for count_only is grep-c-style text.
- Filename search with `include_pattern` filters correctly.
- Filename search with `case_insensitive` matches case-variant filenames.

### 11.3 Byte-Identical Default Test

Add an explicit test that calls `search(path, ctx, pattern="TODO")` and asserts the result dict equals the pre-enhancement shape (no `context_before`/`context_after` keys in match dicts, no `counts` key, no `content_metadata`).

---

## 12. Acceptance Criteria (from MBI-009 T3.1)

- [ ] `search(".", pattern="foo", case_insensitive=True)` matches "Foo" and "foo".
- [ ] `search(".", pattern="class", context_before=2, context_after=2)` returns 2 lines before/after each match.
- [ ] `search(".", pattern="TODO", include_pattern="*.py")` only searches `.py` files.
- [ ] `search(".", pattern="TODO", count_only=True)` returns match counts, not content.
- [ ] Context line cap at 20 enforced (via clamping).
- [ ] Default path byte-identical to current behavior.

---

## 13. Action Items

1. Implement the 6 parameters in `src/yoker/builtin/search.py` per §7.
2. Extend `tests/test_tools/test_search.py` per §11.
3. Run `make check` — must be green.
4. No config, manifest, guardrail, or consumer changes required.