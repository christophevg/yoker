# Functional Review — `github` tool (MBI-009 T7)

**Reviewer:** Functional Analyst
**Date:** 2026-07-27
**Files reviewed:**
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/github.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/__init__.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/config/__init__.py` (`GitHubToolConfig`)
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_github.py`

**Result:** approved

## Acceptance Criteria (from TODO.md)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Read-only MVP: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view | Pass | `_OPERATION_DISPATCH` (github.py:64-98) defines all 9 operations; `TestGithubOperations` covers each |
| 2 | `subprocess` with list args, no shell | Pass | `subprocess.Popen(cmd, ...)` with `cmd: list[str]` (github.py:218-226); `TestGithubSubprocessSecurity::test_command_is_list_no_shell` asserts `shell is not True` and `start_new_session is True` |
| 3 | Operation allowlist (fixed enum, configurable per-project); subcommand blocking | Pass | `_GITHUB_OPERATIONS` frozenset (github.py:49-61) + `GitHubToolConfig.allowed_operations` (config/__init__.py:519-529) validated against the enum in `__post_init__` (config/__init__.py:540-546); runtime check at github.py:170-179 |
| 4 | Timeout enforcement (default 30s) | Pass | `GitHubToolConfig.timeout_ms = 30000` (config/__init__.py:530); `_clamp_timeout` (github.py:390-394) ceilings caller value at config; `Popen` + `communicate(timeout=...)` + `os.killpg(SIGKILL)` (github.py:237-248); `TestGithubTimeout` |
| 5 | Result count limits (max 100 for lists) | Pass | `GitHubToolConfig.max_results = 100` (config/__init__.py:531); `effective_limit = max(1, min(limit, gh_config.max_results))` (github.py:203); `TestGithubParamValidation::test_limit_clamped_to_max_results` |
| 6 | For PR workflow (PR view + workflow view) | Pass | `pr_view` and `workflow_view` operations both implemented with required-`number` positional behind `--` separator |

## Review Checklist

- **All 9 operations implemented**: yes — repo_view, issue_list, issue_view, pr_list, pr_view, workflow_list, workflow_view, release_list, release_view (github.py:49-61, 64-98)
- **Hardcoded dispatch table (no passthrough)**: yes — `_OPERATION_DISPATCH` maps each operation to a fixed `(subcmd, fields, required)` triple; the agent never picks the subcommand, only validated args of a fixed one. Module docstring states this explicitly (github.py:5-8, 46-48).
- **List args only (no shell=True)**: yes — `Popen(cmd, ...)` with `cmd` being a `list[str]`; `shell` is never set. `TestGithubSubprocessSecurity::test_command_is_list_no_shell`.
- **Operation allowlist configurable per-project**: yes — `GitHubToolConfig.allowed_operations` (tuple, default-allow full MVP set); validated against the fixed enum at config construction; runtime check at github.py:170-179. Per-project TOML under `[tools.github]` overrides via the standard Clevis cascade.
- **Timeout enforcement (default 30s)**: yes — 30000 ms default; `_clamp_timeout` enforces `[1000, ceiling_ms]` so the caller can lower but never raise. Process-group kill via `start_new_session=True` + `os.killpg(pid, SIGKILL)` (github.py:225, 239, 457-462).
- **Result count limits (max 100 for lists)**: yes — `max_results=100`; `_LIMIT_OPS = {issue_list, pr_list, workflow_list, release_list}`; clamp at github.py:203.
- **Flat content_metadata shape**: yes — `{operation, path, content_type, content, metadata}` (github.py:272-288). `operation` is `"github"` (tool name, not per-call op) per developer decision; per-call op is implicit via `gh_subcommand` inside `metadata`. `TestGithubResultShape::test_flat_content_metadata_keys` asserts the exact key set.
- **Error handling**: yes — `FileNotFoundError` → "gh not found, install from cli.github.com" (github.py:227-232); auth errors, rate limits, and not-found mapped by `_map_error` regex/substring match (github.py:465-488); timeout returns clean error after killpg. Tests: `TestGithubErrorMapping` covers all five paths.
- **Output redaction**: yes — `_REDACT_PATTERNS` covers `ghp_*`, `github_pat_*`, AWS key IDs (`AKIA`/`ASIA`), Slack (`xox*`), npm tokens, and URL-embedded credentials (github.py:122-129). Applied to stdout AND stderr BEFORE truncation (github.py:251-252) so a secret just past the cut is not retained. Logs only counts, never matched text (github.py:254-260). `TestGithubOutputRedaction` covers ghp, url_creds, AWS.
- **Windows platform gate**: yes — explicit `sys.platform == "win32"` refusal before Popen (github.py:195-199); `TestWindowsPlatformGate` (Windows-only) asserts Popen is not called.
- **No regressions (existing tests still pass)**: yes — `tests/test_tools/test_github.py` 58 passed, 1 skipped (Windows gate on POSIX); full `tests/test_tools/` suite: 601 passed, 8 skipped, 0 failures.
- **No env_vars parameter**: yes — function signature (github.py:133-143) has no `env_vars`; `Popen(env=os.environ)` passes only the inherited environment (github.py:222). `TestGithubSubprocessSecurity::test_no_env_passthrough` asserts `env is os.environ`. Matches the security analysis requirement (security-github-tool.md:139-141, 286).

## Developer Decisions Review

1. **Duplicated `_truncate` and `_kill_process_group` from make.py** — acceptable. Both are 5-line private helpers; coupling the github tool to `make.py` for two trivial utilities would be worse than the small duplication. The alternative (a shared `_subprocess_utils.py` module) would add an indirection layer for ~10 lines of code. Owner's simplicity principle favors the duplication.
2. **`"operation": "github"` in content_metadata** — acceptable. The flat shape requires a stable `operation` key consumed by `core/_processing.py`; using the tool name keeps the contract uniform across tools (the per-call gh subcommand is preserved in `metadata.gh_subcommand`). The per-call operation name is recoverable from `gh_subcommand` when needed.
3. **Default-allow full MVP enum** — acceptable. The tool's value proposition is the read-only MVP set; defaulting to allow-all-nine matches the "secure-by-default but useful out of the box" intent. Operators narrow via `[tools.github] allowed_operations = [...]`. Empty list is valid and effectively disables the tool.
4. **Error mapper uses regex to catch gh's phrasings** — acceptable. `_map_error` covers "not logged in" / "authentication required" / "auth"+"login", "rate limit", and three "not found" phrasings including the `no \w+ found` regex. Falls back to the (already redacted + truncated) stderr. The fallback is safe because redaction runs before the error message is surfaced.

## Defense-in-Depth Verification

The implementation layers multiple independent defenses (matching the security analysis):

1. **Operation enum** (fixed frozenset) — agent cannot name a subcommand outside the nine.
2. **Config allowlist** — operator can narrow further; enum-and-allowlist is two checks, not one.
3. **Per-parameter regex/enum/int validation** — `_REPO_RE`, `_TAG_LABEL_RE`, `_VALID_STATES`, `_MAX_NUMBER`, `_MAX_REPO_LEN`, `_MAX_TAG_LABEL_LEN`, leading-dash rejection, `_FORBIDDEN_CHARS` reject.
4. **`--` separator before user positionals** (github.py:428-432) — defense in depth against flag injection even after the regexes.
5. **No `env_vars` parameter** — agent cannot inject `GH_TOKEN` / `GH_HOST`.
6. **Output redaction before truncation** — secrets past the byte cap are still redacted.
7. **Per-stream byte cap + truncation notice** — bounded context size.
8. **Process-group kill on timeout** — no orphan `gh`/pager/git-helper processes.
9. **POSIX-only gate** — `os.killpg` + `start_new_session` invariants hold.

## Minor Observations (non-blocking)

- `repo_view` with empty `repo` and `require_explicit_repo=False` will let `gh repo view` auto-detect from the git remote. This is intentional (documented in `TestGithubOperations::test_repo_auto_detect_when_empty`) and matches the `gh` default behavior. Operators who want to force explicit repos set `require_explicit_repo=true`.
- The `content_metadata.metadata` inner dict includes `limit`/`state`/`label` only when the operation accepts them (via `_LIMIT_OPS`/`_STATE_OPS`/`_LABEL_OPS`), keeping the shape tight per operation. Good.
- `workflow_list` and `release_list` correctly omit `--state` (only `issue_list`/`pr_list` accept it); verified by `TestGithubOperations::test_workflow_list`.

## Conclusion

The implementation satisfies every acceptance criterion in TODO.md and every item in the review checklist. The security boundary (operation enum + configurable allowlist + no shell + no env passthrough + redaction + process-group kill + POSIX gate) is intact and matches the design in `analysis/api-github-tool.md` and `analysis/security-github-tool.md`. Tests are comprehensive (58 passing covering schema, all 9 operations, allowlist, param validation, timeout, redaction, truncation, result shape, error mapping, subprocess security, config validation, and the Windows gate) with no regressions in the broader `tests/test_tools/` suite (601 passed, 8 skipped).

**approved**