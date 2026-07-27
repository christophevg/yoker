# Testing Review — `github` tool (MBI-009 T7)

**Reviewer:** Testing Engineer
**Date:** 2026-07-27
**Files reviewed:**
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/github.py` (implementation)
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_github.py` (tests)

**Result:** approved

## Checklist Verification

| # | Checklist item | Status | Evidence |
|---|----------------|--------|----------|
| 1 | All 9 operations covered | Pass | `TestGithubOperations` — one test per operation (repo_view, issue_list, issue_view, pr_list, pr_view, workflow_list, workflow_view, release_list, release_view) + auto-detect case |
| 2 | Operation not in enum → rejected | Pass | `test_unknown_operation_rejected` (`"gh_api_bypass"`), `test_non_string_operation_rejected` (`operation=123`) |
| 3 | Operation not in allowlist → rejected | Pass | `test_operation_not_in_allowlist_rejected` (single-op allowlist), `test_empty_allowlist_blocks_all` (`allowed_operations=()`) |
| 4 | Invalid repo/tag/label/state → rejected | Pass | `test_invalid_repo_format_rejected`, `test_invalid_state_rejected`, `test_tag_forbidden_char_rejected`, `test_label_newline_rejected` |
| 5 | Leading-dash rejection | Pass | `test_repo_leading_dash_rejected`, `test_tag_leading_dash_rejected`, `test_label_leading_dash_rejected` |
| 6 | Forbidden chars rejection | Pass | `test_repo_forbidden_char_rejected` (`;rm -rf /`), `test_tag_forbidden_char_rejected`, `test_label_newline_rejected` (`\n`) |
| 7 | Timeout handling (mock Popen, TimeoutExpired) | Pass | `test_timeout_returns_failure` — `_mock_popen(timeout=True)` raises `subprocess.TimeoutExpired`; asserts failure + "timed out" + "1000" in error |
| 8 | Output truncation tested | Pass | `TestGithubOutputTruncation` — over-limit (150 KB → 100 KB cap) asserts `truncated is True`, `[truncated]` present, byte-count bound; under-limit asserts `truncated is False` |
| 9 | Output redaction (ghp_* in stderr → redacted) | Pass | `test_ghp_token_redacted_in_stderr` — verifies raw token absent from `result.error` AND `<redacted>` present; `test_url_creds_redacted_in_stdout` (success path); `test_aws_key_id_redacted` |
| 10 | Windows platform gate | Pass | `TestWindowsPlatformGate` (Windows-only, skipped on POSIX) asserts Popen NOT called + "not available on Windows" message |
| 11 | Flat content_metadata shape | Pass | `test_flat_content_metadata_keys` — `set(md.keys()) == {"operation","path","content_type","content","metadata"}`; verifies inner `metadata` keys, `path=="owner/repo"`, `content_type=="application/json"`, `path=="default"` fallback, error path has `content_metadata is None` |
| 12 | gh not found (FileNotFoundError) | Pass | `test_gh_not_installed` — `Popen(side_effect=FileNotFoundError())`; asserts "not found" + "cli.github.com" install hint |
| 13 | Config validation (unknown op in allowed_operations) | Pass | `TestGithubConfigValidation` — `test_unknown_operation_in_allowlist_raises`, `test_invalid_timeout_raises`, `test_invalid_max_results_raises`, `test_invalid_max_output_kb_raises`, `test_default_allowlist_has_nine_ops`, `test_empty_allowlist_valid` |
| 14 | No env passthrough | Pass | `test_no_env_passthrough` — asserts `kwargs["env"] is github_module.os.environ` (no agent-supplied env) |
| 15 | List args / no shell | Pass | `test_command_is_list_no_shell` — asserts `cmd` is `list[str]`, `cmd[0]=="gh"`, `shell is not True`, `start_new_session is True` |
| 16 | Process-group kill on timeout | Pass | `test_timeout_returns_failure` — mocks `os.killpg`, asserts `killpg.called` AND `_args[1] == signal.SIGKILL`; `start_new_session=True` verified in #15 |
| 17 | Tests meaningful (real value assertions) | Pass | Assertions on argv prefix (`cmd[:3]`), `--` separator index + positional value, returncode, `truncated` flag, redacted content, exact metadata key set, byte-count bounds — not smoke tests |
| 18 | Mocking appropriate (Popen, not the tool) | Pass | `_mock_popen` patches `subprocess.Popen` only; tool function under test runs unmodified |

## Coverage Strengths

- **Defense-in-depth is tested layer by layer**: enum → allowlist → per-parameter regex → leading-dash → forbidden chars → `--` separator → no shell → no env → redaction-before-truncation → process-group kill → POSIX gate. Each layer has at least one targeted test.
- **Both success and error redaction paths**: `test_url_creds_redacted_in_stdout` (returncode=0, redaction in `result.result`) and `test_ghp_token_redacted_in_stderr` (returncode=1, redaction in `result.error`). This matches the implementation's redaction of both streams before truncation.
- **Truncation byte-count assertion** (`test_stdout_truncated_when_over_limit`) verifies the UTF-8 boundary bound, not just the `truncated` flag — catches off-by-one errors in `_truncate`.
- **Argv snapshot tests** (`TestGithubOperations`) verify not just the subcommand prefix but also flag presence (`--state`, `--label`, `--limit`), the `--` separator placement, and the positional value after `--`. This is the right level for "does the operation build the correct gh command".
- **Config validation tests** verify `__post_init__` rejects unknown operations at construction time (config-load typo defense), distinct from the runtime allowlist check.
- **Error mapping tests** cover all five `_map_error` branches: not-logged-in, rate-limited, repo-not-found, issue-not-found, gh-not-installed.
- **Windows gate test** correctly asserts Popen is NOT invoked (the security invariant: the gate must fire before subprocess creation).
- **Mocking discipline**: only `subprocess.Popen` (and `os.killpg` for the timeout test) is mocked. The tool function, validators, redaction, truncation, and error mapper all run for real — the tests verify behavior, not mock wiring.

## Minor Observations (non-blocking)

These are edge cases below the bar for required coverage. None of them represent a security or correctness gap; they are noted for completeness only.

- **`number > _MAX_NUMBER` (2^31-1) clamp** is not exercised. The `< 1` path is covered (`test_number_zero_rejected`); the upper bound is not. Low value: the clamp is a one-line int comparison.
- **`bool` rejection** for `number`/`limit` (`isinstance(x, bool)` guard) is not tested. Low value: defensive type check.
- **`_clamp_timeout` lower bound of 1000 ms** is not exercised. `test_timeout_clamped_to_config_ceiling` covers the upper bound (caller value > config ceiling → ceiling wins); the floor (caller value < 1000 → 1000 wins) is not. Low value.
- **`github_pat_*`, `xox*` Slack, `npm_*` redaction patterns** are not individually exercised. `ghp_*`, URL creds, and AWS key IDs are tested as representative patterns; the untested patterns share the same `pattern.subn` mechanics. Low value.
- **`_map_error` fallback path** (`return stderr.strip() or "GitHub command failed"`) is not directly tested. The five mapped branches are covered; the fall-through is not. Low value.
- **`_kill_process_group` failure paths** (`ProcessLookupError`, `PermissionError`, `OSError`) are not tested. Best-effort logging-only paths. Low value.
- **Non-string `repo`/`tag`/`label`/`state`** (e.g., `repo=123`) is not tested. The `isinstance` guards are defensive. Low value.
- **`test_default_allowlist_allows_all_nine`** calls `_mock_popen` twice (line 212 then inside the loop). Wasteful but not broken — the loop's call overwrites the mock.
- **Rejection-path tests do not assert Popen was NOT called.** All rejection tests set up `_mock_popen` but none verify `not popen.called`. The implementation's early-return ordering makes this obvious, but an explicit assertion would be a cheap invariant check. Non-blocking.
- **`TestWindowsPlatformGate`** is skipped on POSIX CI, so the Windows gate is only exercised on Windows runners. This is the correct approach (the test is meaningless on POSIX), but means coverage of the gate depends on platform diversity in CI.

## Test Quality (anti-pattern scan)

- **No tests of trivial code**: no `test_GITHUB_OPERATIONS_is_frozenset` or `test_max_repo_len_value`. Good.
- **No over-mocking**: only `Popen` and `killpg` are mocked. Validators, redaction, truncation, error mapper all run for real.
- **No exact-string-assertion brittleness**: error messages are checked with `in ... .lower()` (e.g., `"not found" in result.error.lower()`, `"forbidden" in ... or "invalid" in ...`), matching the python-testing flexible-assertion guidance.
- **No `pass`/`assert True`/empty bodies**: every test has meaningful assertions.
- **No fixture-for-single-use**: `_register`, `_ctx`, `_mock_popen` helpers are used across many tests — proper shared utilities, not single-use fixtures.
- **No parametrize-with-one-case**: parametrization is not used; each operation gets its own named test (appropriate because each has slightly different argv expectations).
- **Naming convention**: `test_<area>_<scenario>` consistently; grouped into `TestGithub*` classes by concern (Schema, Operations, Allowlist, ParamValidation, Timeout, Redaction, Truncation, ResultShape, ErrorMapping, SubprocessSecurity, ConfigValidation, WindowsPlatformGate). Good organization.

## Verdict

The test suite is comprehensive, behavior-focused, and uses mocking appropriately. All 18 checklist items pass. The 9 operations, the security boundary (enum + allowlist + no shell + no env + redaction + process-group kill + POSIX gate), parameter validation, timeout handling, output redaction, truncation, config validation, error mapping, and the flat `content_metadata` shape are all covered with meaningful value assertions. The minor observations are edge cases below the required coverage bar and do not affect the security or correctness guarantees of the tool.

**approved**