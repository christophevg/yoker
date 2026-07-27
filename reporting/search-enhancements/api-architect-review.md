# API Review: search Enhancements (MBI-009 T3)

**Date:** 2026-07-27
**Reviewer:** API Architect Agent
**Task:** Verify API design quality of `search` enhancements against `analysis/api-search-enhancements.md`

## Summary

The implementation faithfully realizes the owner's proposal and the approved design. No unauthorized classes, wrappers, or indirections were introduced. The default path is byte-identical to pre-enhancement behavior, the flat `content_metadata` shape matches the consumer contract (`core/_processing.py:441-453`), and the grep-style rendering is appropriate for agent consumption. One justified simplification vs. the design doc's metadata sketch, and two low-severity cosmetic notes — none blocking.

**Verdict: approved.**

## Owner's Proposal (Baseline)

> "Add case_insensitive: bool = False, context_before: int = 0, context_after: int = 0, include_pattern: str = "", exclude_pattern: str = "", count_only: bool = False; Cap context lines at 20 to prevent output flooding"

The implementation matches this exactly:
- 6 parameters with the specified names, types, and defaults (`search.py:71-76`).
- `MAX_CONTEXT_LINES = 20` enforced via `_clamp(...)` at `search.py:115-116` — clamping, not a validation error, consistent with the existing `max_results`/`timeout_ms` clamp pattern.

No parameter was added, renamed, or re-typed beyond the proposal.

## Findings

### Strengths

1. **Signature consistency** — The 6 new params are appended after the existing defaulted params, use plain types (no spurious `Annotated`/`Text` markers), and match the style of the existing `max_results`/`timeout_ms`/`type` params. `path` and `ctx` remain in positions 1 and 2, preserving the codebase convention (`read.py:25-30`, `update.py:38-52`).

2. **Flat `content_metadata` shape** — `_build_search_content_metadata` (`search.py:436-462`) emits exactly the 5 flat keys the consumer reads: `operation`, `path`, `content_type`, `content`, `metadata`. This is the contract at `core/_processing.py:441-453`. Verified by `TestSearchEnhancementsContentMetadataShape::test_flat_shape_keys`.

3. **Default-path bypass is clean** — When all 6 params are at defaults, `enhanced` is `False` (`search.py:148-155`), no `content_metadata` is attached (`search.py:236`), match dicts carry only `{file, line, content}` (`_search_content` doesn't set context keys because `collect_context` is `False`), and `_walk_files`'s include/exclude guards short-circuit on empty strings (`search.py:277-280`) — zero `fnmatch` calls on the default path. The only extra work is 6 trivial `effective_*` assignments and one boolean computation. Byte-identical behavior is verified by `TestSearchEnhancementsDefaultPath`.

4. **No new abstractions** — No new classes, modules, guardrails, or config. `SearchToolConfig` is unchanged. The manifest is unchanged (schema auto-updates via introspection). `PathGuardrail` still covers the only path-like parameter. This matches design doc §7.2.

5. **Helpers are single-responsibility, no duplication**:
   - `_render_context_lines` (`search.py:285-294`) — renders `cat -n` style context slices, used in `_search_content`. Justified: the design doc §4.2 explicitly requires `cat -n` format for cross-tool consistency with `read`.
   - `_parse_cat_n` (`search.py:402-407`) — 5-line utility to split `"   123\ttext"` back into `(line_num, text)` for the grep-style rendering. Justified: context is stored as `cat -n` strings (per design doc), but the grep-style `content` field needs `file-123-text` format, so the line number must be extracted. Without this helper, the parsing would be inline in `_render_search_text` (duplicate logic).
   - `_render_search_text` (`search.py:410-433`) — grep-style rendering for the `content` field. Single responsibility.
   - `_build_search_content_metadata` (`search.py:436-462`) — assembles the flat dict. Single responsibility.
   - `_walk_files` extended with two optional params (`search.py:265-282`) — the cleanest integration point per design doc §7.4; keeps include/exclude filtering in one place for both content and filename search.

6. **Grep-style rendering is appropriate** — Matched lines use `file:line:content`, context lines use `file-line-text` (standard grep `-`/`:` convention). Count-only uses `file:count`. Filename uses bare paths. All verified by `TestSearchEnhancementsContentMetadataShape`.

7. **State/flag interactions match the design doc**:
   - `count_only` wins over context: `collect_context = (... ) and not count_only` (`search.py:321`). Warning logged when both are set (`search.py:129-130`).
   - `count_only` ignored for filename search: `_search_filename` doesn't receive `count_only`; result keeps default filename shape. Verified by `test_count_only_ignored_for_filename`.
   - `truncated` for count_only is set only by timeout, not `max_results` (`search.py:364-366`). Matches design doc §4.4.
   - Negative context clamps to 0 → `enhanced` is False → no `content_metadata`, no context keys. Verified by `test_context_negative_clamped_to_zero`.

### Observations (Low Severity — Not Blockers)

1. **Metadata dict is slimmer than design doc §6.2 sketched.** The implementation's `metadata` has 7 keys: `case_insensitive`, `context_before`, `context_after`, `include_pattern`, `exclude_pattern`, `count_only`, `total_matches`. The design doc §6.2 also listed `type`, `pattern`, `matches`, `truncated`, `files_searched`, `counts`. The implementation omits these because they already live in the `result` dict (which the LLM consumes via `str(result)`) and would be redundant duplication. This is a simplification in the direction the Simplicity Principle endorses, and the consumer contract only requires the 5 flat top-level keys — the contents of `metadata` are tool-specific. Flagging as a deviation from the approved design for owner awareness; recommend accepting the simpler shape and updating the design doc to match.

2. **Filename search with `context_before`/`context_after` set records the requested values in `metadata` even though they're not applied.** `_search_filename` doesn't use context params, but `_build_search_content_metadata` records the effective values. The `result` dict is correct (no context keys). Cosmetic only — metadata reflects "what was requested", not "what was applied". No test covers this specific combination. Low severity.

3. **No test for filename search with `context_before`/`context_after`.** The "ignored for filename search" behavior is implied by the absence of context keys in filename match dicts (`{file}` only), but not explicitly asserted when `context_before` is set alongside `type="filename"`. Minor test gap.

### Compliance Check

- [x] Function signature consistent with other built-in tools (`read`, `update`, `make`).
- [x] Parameter naming/typing consistent with codebase conventions (plain types for non-annotated params, `Annotated[str, PathArg/Text]` for path/pattern).
- [x] Return shape (`ToolResult` with flat `content_metadata`) used correctly — 5 flat keys match `core/_processing.py:441-453`.
- [x] Helpers well-designed (single responsibility, no duplication).
- [x] Default-path bypass clean (no unnecessary work when all params at defaults).
- [x] Grep-style content rendering appropriate for agent consumption.
- [x] No over-engineering or unnecessary abstractions. No classes, wrappers, or guardrails beyond the owner's proposal.
- [x] RESTful/RPC: N/A (tool function, not HTTP endpoint). Parameter names are noun/mode-oriented; `count_only` is a mode flag (grep `-c` analogue), not an RPC verb.

## Action Items

1. (Optional) Update `analysis/api-search-enhancements.md` §6.2 to reflect the slimmer `metadata` dict actually implemented (7 keys, not 13) — brings the design doc in sync with the code.
2. (Optional) Add one test asserting `context_before` is ignored for `type="filename"` (verifies metadata records the value but result dict has no context keys).

Neither action item blocks approval.