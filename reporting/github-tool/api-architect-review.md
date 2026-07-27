# API Review: GitHub Tool (MBI-009 T7)

**Date**: 2026-07-27
**Reviewer**: API Architect Agent
**Task**: Review github tool implementation against `analysis/api-github-tool.md` v1.1

## Summary

The implementation is clean, follows established codebase patterns (make.py, read.py), and faithfully implements the approved design. No over-engineering, no unnecessary classes or wrappers. All abstractions present are justified by the spec or required for security. The operation dispatch table is hardcoded with no passthrough — the security boundary is sound.

**Verdict: approved** (with minor observations below).

## Files Reviewed

- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/github.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/__init__.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/config/__init__.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_github.py`
- `/Users/xtof/Workspace/agentic/yoker/analysis/api-github-tool.md` (v1.1, baseline)
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/make.py` (reference)
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/read.py` (reference)
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/core/_processing.py:441-453` (consumer contract)

## Checklist Results

### Function signature consistency — PASS

`async def github(operation, ctx, repo="", number=None, tag="", limit=30, state="open", label="", timeout_ms=None) -> ToolResult` matches the make.py/git.py pattern: async, `ctx: ToolContext` second positional, `Annotated[str, Text("...")]` markers on string params, `ToolResult` return. `operation` is required (first positional), consistent with `make`'s `target`.

### Operation dispatch table — PASS

`_OPERATION_DISPATCH` is a hardcoded `dict[str, tuple[list[str], str, str | None]]` mapping each of the 9 operations to a fixed `(gh_subcommand_prefix, json_fields, required_param)`. No passthrough — the agent cannot influence which `gh` subcommand runs, only the validated arguments. This is the security boundary the owner confirmed.

### Parameter naming/typing — PASS

Naming and typing are consistent with codebase conventions. `repo: str`, `number: int | None`, `tag: str`, `limit: int`, `state: str`, `label: str`, `timeout_ms: int | None` — all match the spec §2.1 table and the codebase style.

### Return shape (flat content_metadata) — PASS (with note)

The flat 5-key shape is correct: `{operation, path, content_type, content, metadata: {...}}`. The consumer contract at `_processing.py:441-453` reads these exact keys. Tests assert the shape explicitly (`test_flat_content_metadata_keys`).

**Note**: `"operation": "github"` (the tool name) rather than `"operation": operation` (e.g. "issue_view") as the spec §4.4 comment suggests. This is actually *more* consistent with `read.py` which sets `"operation": "read"` (tool name). The specific operation is preserved in `metadata["gh_subcommand"]`. The implementation chose codebase consistency over the spec's inline comment — this is the right call.

### GitHubToolConfig — PASS

5 fields (`allowed_operations`, `timeout_ms`, `max_results`, `require_explicit_repo`, `max_output_kb`) plus inherited `enabled`. Validation in `__post_init__` calls `validate_positive_int` for the three numeric fields and checks each `allowed_operations` entry against `_GITHUB_OPERATIONS`. Follows the `MakeToolConfig` / `SearchToolConfig` pattern exactly. Wired into `ToolsConfig` via `field(default_factory=GitHubToolConfig)`.

### Error handling mapping — PASS

`_map_error` covers the spec §4.5 cases: not authenticated, rate limited, not found (with per-operation detail), and falls back to sanitized stderr. `gh` not installed is caught at `Popen` (`FileNotFoundError`). Timeout returns a clear message with the effective ms.

### No over-engineering — PASS

No classes, no wrappers, no unnecessary indirection. Helpers are small and justified:
- `_validate_params` — keeps the main function readable
- `_build_command` — isolates argv construction
- `_clamp_timeout` — trivial but clear
- `_redact` / `_truncate` / `_kill_process_group` — duplicated from make.py per spec §4.1 ("either import them or duplicate the small functions; they are trivial")
- `_map_error` — error classification
- `_contains_forbidden` — one-liner, harmless

All functions are module-level, no class hierarchy, no registry pattern. Matches the owner's proposal.

## Findings

### Strengths

- Operation enum + dispatch table is a clean, hardcoded security boundary — no passthrough possible
- `--` separator before user-supplied positionals (defense in depth beyond spec)
- Process-group kill on timeout follows make.py's R4 pattern exactly
- Output redaction applied BEFORE truncation (so a secret just past the cut isn't kept)
- No env passthrough — agent cannot inject `GH_TOKEN` or `GH_HOST`
- Tests cover all 9 operations, the security boundary, validation, timeout, redaction, truncation, result shape, and error mapping

### Issues Found

#### 1. `_GITHUB_OPERATIONS` duplicated across two modules
- **Severity**: Low (maintainability)
- **Location**: `builtin/github.py:49-61` and `config/__init__.py:486-498`
- **Note**: The config module cannot import from builtin (would create a circular dependency at module load), so duplication is structurally motivated. The config copy carries a comment "Mirrors yoker.builtin.github._GITHUB_OPERATIONS". Acceptable trade-off, but adding an operation requires updating both. Consider a shared `yoker/tools/constants.py` or similar if this pattern recurs.
- **Recommendation**: Leave as-is for MVP; document the dual-location invariant in both comments (already done in config, the builtin side could note it too).

#### 2. Extended redaction patterns beyond spec
- **Severity**: Low (security-positive, but beyond what was earned)
- **Location**: `builtin/github.py:122-129` — 6 redaction patterns (ghp_, github_pat_, AKIA/ASIA, xox, npm_, url creds)
- **Note**: The spec §6.3 only required reusing `git.py`'s `CREDENTIAL_PATTERN` (URL-embedded credentials). The implementation adds 5 more patterns (GitHub PAT, AWS key IDs, Slack tokens, npm tokens). This is more than the spec required but is defensive in depth and does not add abstraction — it adds regex entries to a list. False positives are acceptable (redaction is conservative).
- **Recommendation**: Acceptable. If strict spec adherence is desired, trim to the URL-credential pattern only. Given the security-positive nature and zero added indirection, I lean toward keeping it.

#### 3. `path` default is "default" not "(current repo)"
- **Severity**: Cosmetic
- **Location**: `builtin/github.py:275`
- **Note**: Spec §4.4 shows `"path": repo or "(current repo)"`. Implementation uses `"default"`. Test `test_path_defaults_when_repo_empty` asserts `"default"`. Minor cosmetic deviation; the consumer just passes it through to `ToolContentEvent.path`.
- **Recommendation**: Either is fine. No action required.

#### 4. `state`/`label` validated for all operations, not just consumers
- **Severity**: Cosmetic
- **Location**: `builtin/github.py:362-380` — `_validate_params` validates `state` and `label` regardless of operation
- **Note**: An invalid `state` passed to `repo_view` is rejected even though `repo_view` ignores `state`. This is defensive (fail fast on bad input) but could surprise a caller who passes `state="all"` to a non-list op expecting it to be ignored. The metadata correctly records `None` for non-applicable ops.
- **Recommendation**: Acceptable as defensive validation. No action required.

#### 5. Redundant mock setup in one test
- **Severity**: Nit (test only)
- **Location**: `tests/test_tools/test_github.py:212` and `:215` — `_mock_popen` called twice in `test_default_allowlist_allows_all_nine`
- **Recommendation**: Remove the line-212 call. Cosmetic.

### Compliance Check

- **RESTful**: N/A (this is a tool function, not an HTTP endpoint)
- **Spec adherence**: High — matches v1.1 with the minor deviations noted above
- **Codebase consistency**: High — follows make.py/read.py patterns
- **Security model**: Sound — operation enum + allowlist + no shell + process-group kill + output redaction + no env passthrough
- **Test coverage**: Comprehensive — all operations, boundary, validation, timeout, redaction, truncation, shape, errors, config validation

## Owner's Proposal Baseline Check

> "Read-only MVP: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view; subprocess.run(["gh", ...], ...) — list args, no shell; Operation allowlist (fixed enum, configurable per-project); subcommand blocking is the whole point; Timeout enforcement (default 30s); result count limits (max 100 for lists)"

| Proposal element | Implementation | Status |
|------------------|----------------|--------|
| Read-only MVP ops | 9 operations, all read-only | ✅ |
| `subprocess.run` list args, no shell | `subprocess.Popen` list args, `shell=False` | ✅ (Popen justified by R4 process-group kill; documented in spec §4.1) |
| Operation allowlist, fixed enum, configurable | `_GITHUB_OPERATIONS` + `GitHubToolConfig.allowed_operations` | ✅ |
| Subcommand blocking | Two-gate check (enum + allowlist) | ✅ |
| Timeout default 30s | `timeout_ms: int = 30000` | ✅ |
| Max 100 for lists | `max_results: int = 100`, clamped | ✅ |

**Abstractions added beyond owner's proposal**: none significant. The helpers (`_validate_params`, `_build_command`, `_map_error`, `_redact`, `_truncate`, `_kill_process_group`, `_clamp_timeout`, `_contains_forbidden`) are all small functions that keep the main function readable — not classes, not wrappers, not registries. The extended redaction patterns are the only "more than earned" addition, and they add data (regex entries), not indirection.

## Conclusion

**approved**

The implementation is a faithful, clean realization of the approved design. It follows codebase conventions (make.py subprocess pattern, read.py flat content_metadata shape), adds no unjustified abstractions, and the security boundary (operation enum + allowlist) is correctly implemented. The minor deviations from the spec text (operation field value, path default, extended redaction) either favor codebase consistency or are security-positive. No blocking issues.

## Next Steps

- Address the redundant `_mock_popen` call in `test_default_allowlist_allows_all_nine` (nit)
- Optionally add a comment on the builtin side noting the `_GITHUB_OPERATIONS` dual-location invariant
- Proceed to `make check` and merge