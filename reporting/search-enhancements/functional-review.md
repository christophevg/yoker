# Functional Review: search enhancements (MBI-009 T3)

**Date:** 2026-07-27
**Reviewer:** functional-analyst
**Files reviewed:**
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/search.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_search.py`

**Verdict:** approved

## Acceptance Criteria (from TODO.md)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `case_insensitive: bool = False` | met | `search.py:71`; regex compiled with `re.IGNORECASE` (line 316); filename lowercased (lines 383-388) |
| 2 | `context_before: int = 0` | met | `search.py:72`; collected in `_search_content` via `_render_context_lines` (line 356) |
| 3 | `context_after: int = 0` | met | `search.py:73`; collected at line 357 |
| 4 | `include_pattern: str = ""` | met | `search.py:74`; applied in `_walk_files` (line 277) |
| 5 | `exclude_pattern: str = ""` | met | `search.py:75`; applied in `_walk_files` (line 279) |
| 6 | `count_only: bool = False` | met | `search.py:76`; switches result to `counts` dict (lines 182-189) |
| 7 | Cap context lines at 20 | met | `MAX_CONTEXT_LINES = 20` (line 31); `_clamp(..., 0, MAX_CONTEXT_LINES)` (lines 115-116) |

All 7 acceptance criteria are satisfied.

## Edge Cases

| Edge case | Status | Evidence |
|-----------|--------|----------|
| Context clamped to 20 | handled | `test_context_clamped_to_max`: `context_before=50` → 20 lines; metadata records 20 |
| Negative context clamped to 0 | handled | `test_context_negative_clamped_to_zero`: `context_before=-5` → 0, no context keys, `enhanced=False`, no content_metadata |
| count_only with context | handled | `collect_context = (...) and not count_only` (line 321); `test_count_only_with_context_ignored` confirms counts path wins, no matches list |
| count_only for filename | handled | filename branch ignores `count_only` (no `counts` key); `test_count_only_ignored_for_filename` |
| include + exclude combined | handled | `_walk_files` applies include first, then exclude (lines 277-279); `test_include_and_exclude_combined` confirms `*.py` + `main*` → only `utils.py` |
| Context at file start | handled | `before_start = max(0, match_idx - context_before)` (line 354); `test_context_boundary_at_file_start` confirms 0 lines returned |
| Pattern too long (include/exclude) | handled | lines 123-127 reject > 500 chars; `test_include_pattern_too_long` |
| Hidden files / skip dirs | preserved | `_walk_files` retains prior skip behavior (lines 272, 275-276) |
| Symlinks / large files / Unicode | preserved | untouched in `_search_content` (lines 331-336) |

## Default-Path Backward Compatibility

`enhanced` flag (lines 148-155) is `False` only when all six new params are at default. Verified by:

- `test_default_path_no_content_metadata`: `content_metadata is None`
- `test_default_path_match_dict_shape`: match dict keys exactly `{file, line, content}` (no `context_before`/`context_after` added when `collect_context=False`)
- `test_default_path_result_keys`: result dict keys exactly `{success, matches, total_matches, truncated, files_searched}`

The default path is byte-identical to pre-enhancement behavior: no new keys, no `content_metadata`, no extra match fields.

## Flat content_metadata Shape

When `enhanced=True`, `_build_search_content_metadata` (lines 436-462) emits a flat dict:

```
{operation, path, content_type, content, metadata}
```

where `metadata` is a nested 7-key dict: `{case_insensitive, context_before, context_after, include_pattern, exclude_pattern, count_only, total_matches}`.

Verified by:
- `test_flat_shape_keys`: top-level keys exactly `{operation, path, content_type, content, metadata}`
- `test_metadata_keys`: metadata keys exactly the 7 specified keys
- `test_grep_style_content`: content is `file:line:content` grep-style
- `test_grep_style_with_context`: context lines use `-` separator (grep-style `file-line-text`)
- `test_count_only_metadata`: count_only path emits `file:count` grep-c style

The shape matches the task spec's 7-key metadata set (not the broader 13-key set from the analysis doc) — per the developer's note, this is intentional and aligns with owner's proposal.

## No Regressions

- `uv run pytest tests/test_tools/test_search.py`: 75 passed
- `uv run make check`: 2048 passed, 7 skipped, 14 warnings — full suite green

## Owner's Proposal Satisfaction

Owner's proposal (TODO.md lines 76-79): all 6 params + context cap at 20.

- All 6 params present with exact signatures and defaults ✓
- Context cap at 20 enforced via `_clamp` ✓
- No deviation from owner's proposal ✓

## Developer Decisions (reviewed, accepted)

1. **`include_pattern`/`exclude_pattern` case-sensitive regardless of `case_insensitive`** — matches grep `--include`/`--exclude` semantics. File filters operate on filenames, not content. Justified, no concern.
2. **Context indexing `lines[max(0, match_idx - context_before) : match_idx]`** — natural clamp at file start. Verified by `test_context_boundary_at_file_start`. Justified.
3. **7-key metadata (not 13-key from analysis doc)** — task spec is the authoritative source; analysis doc is broader context. Justified.
4. **macOS HFS+/APFS case-insensitive filesystem workaround** — `test_case_insensitive_filename` uses pattern-based case matching (`main.py` matching `Main.py`) rather than creating same-name case-variant files. Avoids filesystem collision. Justified.
5. **Test location `tests/test_tools/test_search.py`** — TODO.md mentions `tests/test_builtin/test_search.py` but no `tests/test_builtin/` directory exists; all tool tests live in `tests/test_tools/`. Consistent with existing layout. Minor doc path mismatch in TODO.md, not a functional issue.

## Minor Observations (non-blocking)

- When `count_only=True` is passed with `type="filename"`, the metadata still records `count_only: True` even though filename search ignores it. This is a cosmetic inconsistency in the metadata echo, not a functional bug — the result shape is correct (matches list, no counts). No action required for this task.
- `search_count_only_with_context_ignored` warning is logged (line 130) but not surfaced to the user. Acceptable for an LLM-facing tool; the result shape itself communicates the behavior.

## Conclusion

The implementation fully satisfies all 7 acceptance criteria, handles all enumerated edge cases, preserves byte-identical default-path behavior, emits the specified flat content_metadata shape on the enhanced path, and introduces no regressions (full `make check` green). Owner's proposal is satisfied with no deviation.