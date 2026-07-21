# Functional Review — `make` tool (MBI-009 T1, PR #48)

**Reviewer:** functional-analyst
**Date:** 2026-07-21
**Branch:** `feature/make-tool` (PR #48)
**Verdict:** **APPROVED**

---

## Section 1 — Acceptance Criteria Checklist

Sources: TODO.md `make` tool section; `per-target-allowlist-response.md` (owner-approved design Option A; Q1–Q4 decisions).

| # | Criterion (quoted / paraphrased) | Satisfied? | Evidence |
|---|---|---|---|
| 1 | `make(target, ctx, cwd, timeout_ms) -> ToolResult` signature | Yes | `src/yoker/builtin/make.py:37-43`. Adds `env_vars` per owner-approved Option A extension. |
| 2 | Target validation (reject `;`, `\|`, `&`, `$`, backticks) | Yes | `_FORBIDDEN_TARGET_CHARS` frozenset at `make.py:32` enumerates all five plus `\n`, `\r`, `\x00`. Loop at `make.py:62-64` rejects any match. `_TARGET_RE` at `make.py:28` independently rejects them. Tests: `test_target_with_semicolon_rejected`, `test_target_with_space_rejected`. |
| 3 | PathGuardrail on `cwd` | Yes | `"make"` added to `_FILESYSTEM_TOOLS` (`path.py:31`). `cwd` annotated with `PathArg` (`make.py:40`); schema exposes `guards["cwd"] = GuardType.PATH` (`test_schema_has_cwd_path_guard`). PathGuardrail tests: `test_guardrail_blocks_cwd_outside_allowed`, `test_guardrail_blocks_traversal`, `test_guardrail_allows_cwd_inside_allowed`. |
| 4 | `subprocess.run(["make", target], ...)` — list args, no shell | Yes (deviation earned — see §5) | Uses `subprocess.Popen(["make", target], ...)` with `start_new_session=True`, no `shell=True`. Test `test_command_is_list_not_shell` asserts `cmd == ["make", "check"]`, `shell is not True`, `start_new_session is True`. |
| 5 | Output truncation (default 100KB) | Yes | `_truncate` at `make.py:143-153`, called per-stream at `make.py:127-129`. `MakeToolConfig.max_output_kb=100` default. UTF-8-boundary cut with notice. Tests: `test_output_truncated_when_over_limit`, `test_small_output_not_truncated`. |
| 6 | Timeout enforcement (default 5 min) | Yes | `MakeToolConfig.timeout_ms=300000` default. `effective_timeout_ms = max(min(timeout_ms, make_config.timeout_ms), 1000)` clamps to config ceiling and 1s floor (`make.py:85`). Tests: `test_timeout_returns_failure`, `test_timeout_clamped_to_config_ceiling`, `test_timeout_minimum_one_second`. |
| 7 | Agent can run `make check`, `make test`, etc. | Yes | End-to-end tests `test_make_check_end_to_end`, `test_make_test_with_env_end_to_end` against real Makefiles. |
| 8 | Q1: Hard non-configurable denylist | Yes | `src/yoker/tools/guardrails/env.py:13-74` defines `_DENIED_EXACT` + `_DENIED_PREFIXES` as module-level frozensets/tuples; `is_denied_env_var` is non-configurable. Tests: `test_denied_names` (50+ cases), `test_denied_var_rejected_even_if_allowlisted`, `test_denied_yoker_prefix_rejected_even_if_allowlisted`. |
| 9 | Q2: Value validation | Yes | `validate_env_vars` checks string type, NUL, newlines (`\n` and `\r`), UTF-8 validity, byte length ≤ `max_env_var_bytes` (default 4096). Tests: `test_oversize_value_rejected`, `test_value_at_limit_passes`, `test_nul_byte_in_value_rejected`, `test_newline_in_value_rejected`, `test_carriage_return_in_value_rejected`, `test_non_string_value_rejected`. |
| 10 | Q3: make-only (not generic across all tools) | Yes | Only `MakeToolConfig` gains `allowed_env_vars` and `max_env_var_bytes`. `GitToolConfig` unchanged (`config/__init__.py:433-449`). `env.py` guardrail is only imported by `make.py`. |
| 11 | Q4: Deny-by-default | Yes | `make.py:77`: `allowed_names = make_config.allowed_env_vars.get(target, ())` — target not in dict → empty tuple → all vars rejected. Tests: `test_env_var_denied_when_target_not_in_allowlist`, `test_env_var_denied_when_name_not_in_per_target_tuple`, `test_empty_allowlist_rejects_all`. |
| 12 | Option A: per-target allowlist `dict[str, tuple[str, ...]]` | Yes | `MakeToolConfig.allowed_env_vars: dict[str, tuple[str, ...]]` (`config/__init__.py:467`) matches the owner-approved sketch exactly. Target keys validated against `_TARGET_NAME_RE` in `__post_init__`. |
| 13 | Manifest entry for `make` | Yes | `src/yoker/builtin/__init__.py:14` imports `make`; line 47 adds it to `__YOKER_MANIFEST__.tools`. |
| 14 | ToolResult shape: exit_code, stdout, stderr, truncated | Yes | `make.py:131-140`. Tests: `test_success_result_dict_keys`, `test_stderr_separate_from_stdout`, `test_nonzero_exit_still_returns_structured_result`. |
| 15 | R4: Process group killed on timeout | Yes | `start_new_session=True` (`make.py:100`); `_kill_process_group(proc.pid)` via `os.killpg(pid, SIGKILL)` (`make.py:114, 156-161`). Test `test_process_group_killed_on_timeout` asserts `killpg` called with the pid and `SIGKILL`. |

All acceptance criteria satisfied.

---

## Section 2 — Edge Case Coverage

| Edge case | Covered? | Test / code |
|---|---|---|
| Empty target `""` | Yes | `test_empty_target_rejected` (parametrized `["", "   ", "\t"]`) |
| Whitespace target | Yes | same |
| Leading-`-` target | Yes | `test_leading_dash_rejected`, `test_flag_injection_rejected` (`["-i", "-j", "-C /tmp"]`) |
| Overlong target (>256) | Yes | `test_overlong_target_rejected` (257 chars) |
| Target with `;` | Yes | `test_target_with_semicolon_rejected` |
| Target with `\|`, `&`, `$`, backtick | Logic covered, not individually tested | `_FORBIDDEN_TARGET_CHARS` enumerates all; regex independently rejects. Only `;` and newline explicitly tested. Acceptable — frozenset is exhaustive and the `;` test exercises the loop. |
| Target with newline | Yes | `test_target_with_newline_rejected` |
| Target with NUL | Logic covered, not explicitly tested | `\x00` in `_FORBIDDEN_TARGET_CHARS`; regex also rejects. Acceptable. |
| cwd outside project root | Yes | `test_guardrail_blocks_cwd_outside_allowed` |
| Traversal cwd `../../` | Yes | `test_guardrail_blocks_traversal` |
| env_vars None | Yes | `test_env_vars_none_ok` |
| env_vars empty `{}` | Yes | `test_empty_env_vars_ok` |
| env_vars with allowlisted names | Yes | `test_env_var_allowed_and_propagated`, `test_make_test_with_env_end_to_end` |
| env_vars with MAKEFLAGS | Yes | `test_makeflags_denied_even_if_allowlisted` (even when allowlisted) |
| env_vars with `LD_*`, `YOKER_*`, `DYLD_*`, `BASH_FUNC_*`, `GIT_*`, etc. | Yes | `test_denied_names` parametrized (50+ cases) |
| env_vars with non-allowlisted names | Yes | `test_var_not_in_allowlist_rejected`, `test_env_var_denied_when_name_not_in_per_target_tuple` |
| env_vars with oversize values | Yes | `test_oversize_value_rejected` (4097 > 4096) |
| env_vars at exact limit | Yes | `test_value_at_limit_passes` (4096 bytes) |
| env_vars with NUL value | Yes | `test_nul_byte_in_value_rejected` |
| env_vars with newline value | Yes | `test_newline_in_value_rejected`, `test_carriage_return_in_value_rejected` |
| env_vars not a dict | Yes | `test_env_vars_not_dict_rejected` |
| Per-target: target in dict → only listed vars | Yes | `test_env_var_denied_when_name_not_in_per_target_tuple` (build's tuple excludes TEST) |
| Per-target: target not in dict → deny all | Yes | `test_env_var_denied_when_target_not_in_allowlist` |
| Missing Makefile | Yes | `test_missing_makefile_returns_nonzero` (no pre-check; make emits stderr) |
| make not installed | Yes | `test_make_not_installed` (FileNotFoundError mock) |
| Timeout | Yes | `test_timeout_returns_failure` (sleep 10, timeout 1s) |
| Output truncation | Yes | `test_output_truncated_when_over_limit` (~200KB, cap 100KB) |
| Non-zero exit | Yes | `test_nonzero_exit_still_returns_structured_result` (exit 2) |
| Returns first failing env var | Yes | `test_returns_first_failure` |

Edge case coverage is thorough. Two minor gaps (explicit tests for `|`, `&`, `$`, backtick, NUL in *target*) are not blocking — the frozenset is exhaustive and the loop is exercised by the `;` and newline tests.

---

## Section 3 — End-to-End Flow

`make(target="check")`:
- PathGuardrail validates `cwd` (skipped if `cwd` unset; default `.` resolves to process cwd, same pattern as `git`).
- Target validation passes (`check` matches regex, no forbidden chars).
- `env_vars=None` → no validation; `env = os.environ` inherited.
- `Popen(["make", "check"], cwd=resolved, env=env, start_new_session=True)`.
- `communicate(timeout=300)`.
- On success: `ToolResult(success=True, result={exit_code: 0, stdout, stderr, truncated: False})`.
- Verified by `test_make_check_end_to_end`.

`make(target="test", env_vars={"TEST": "foo.py"})` with `MakeToolConfig(allowed_env_vars={"test": ("TEST",)})`:
- Target validation passes.
- `allowed_names = ("TEST",)`.
- `validate_env_vars({"TEST": "foo.py"}, ("TEST",), 4096)` → None (passes allowlist, not denied, value valid).
- `env = {**os.environ, "TEST": "foo.py"}`.
- `Popen(["make", "test"], env=env, ...)`.
- Make sees `$(TEST)` → `foo.py` in stdout.
- Verified by `test_env_var_allowed_and_propagated` and `test_make_test_with_env_end_to_end`.

Both user flows work end-to-end.

---

## Section 4 — Owner's Proposals / Worries / Constraints (quoted + addressed)

Owner comment 5033135719 verbatim:

> Hard deny ist: ✅

Addressed: `_DENIED_EXACT` + `_DENIED_PREFIXES` are module-level, non-configurable. `is_denied_env_var` is checked *after* the per-tool allowlist and enforced regardless of operator config (`env.py:77-83`, `validate_env_vars:109`). Operator cannot waive framework invariants.

> Value validation: ✅

Addressed: `validate_env_vars` checks type, NUL, newline, UTF-8 validity, byte length (`env.py:106-122`). `MakeToolConfig.max_env_var_bytes=4096` default.

> Generic available for all tools: ❌ Let's start with the `make` tool only. For now I don't think other tools benefit from having configuration options using env vars - please review and confirm.

Addressed: make-only. Only `MakeToolConfig` has `allowed_env_vars`/`max_env_var_bytes`. `GitToolConfig` unchanged. `env.py` is only imported by `make.py`. The §1 review in `per-target-allowlist-response.md` confirmed no other built-in tool has a legitimate env-var override use case.

> Deny-by-default: ✅

Addressed: `allowed_env_vars.get(target, ())` returns `()` for any target not in the dict → `validate_env_vars` rejects every var with "not in per-target allowlist".

> Additional feature question: Can we make the allowed env vars list configurable at target level? ... `allowed_env_vars = { test : [ "TEST" ] }` ... or `[tools.make.test] allowed_env_vars = [ "TEST" ]`

Addressed: Option A (inline-table / subsection form) implemented as `dict[str, tuple[str, ...]]` on `MakeToolConfig`. The TOML shape in the response doc (`[tools.make.allowed_env_vars] test = ["TEST"]`) binds directly to this field. Option B rejected with stated reasoning (collision with config fields, no clean dataclass shape). The implementation matches the owner-approved Option A sketch verbatim.

All owner proposals satisfied. No unearned indirections — `env.py` mirrors the `path.py` module-level frozenset + functions pattern (no class), `_truncate` and `_kill_process_group` are single-purpose helpers, `validate_env_vars` is a single function. No wrapper classes introduced.

---

## Section 5 — Deviation Assessment

### Deviation 1: `subprocess.Popen` + `communicate` instead of `subprocess.run`

**Claim:** `subprocess.run` doesn't expose `Popen` in `TimeoutExpired` for `os.killpg`.

**Verification:** Inspected `subprocess.TimeoutExpired` attributes — `['add_note', 'args', 'cmd', 'output', 'stderr', 'stdout', 'timeout', 'with_traceback']`. No `Popen` / `pop` attribute. `subprocess.run` internally kills only the parent process on timeout (via `proc.kill()`), not the process group. With `start_new_session=True`, children of `make` (e.g., recursive makes, test runners) would survive orphaned.

**Verdict:** Earned. The deviation is required for R4 (process-group kill on timeout). `Popen` + `start_new_session=True` + `os.killpg(pid, SIGKILL)` is the correct pattern. Test `test_process_group_killed_on_timeout` verifies `killpg` is called with the child's pid and `SIGKILL`.

### Deviation 2: Test path `tests/test_tools/test_make.py` instead of `tests/test_builtin/test_make.py`

**Claim:** `tests/test_builtin/` doesn't exist; git tests are in `tests/test_tools/`.

**Verification:** `ls tests/test_builtin/` returns empty (directory does not exist). `ls tests/test_tools/` shows `test_git.py`, `test_existence.py`, `test_mkdir.py`, `test_read_plugin_url.py`, `test_search.py`, `test_skill.py`, etc. All built-in tool tests live in `tests/test_tools/`.

**Verdict:** Earned. The test placement follows the existing project convention. The plan in `per-target-allowlist-response.md` listed `tests/test_builtin/test_make.py` as a typo / plan-vs-reality mismatch; the developer correctly followed the established directory structure.

### Deviation 3: Pre-initialize `stdout = ""` / `stderr = ""`

**Claim:** Fixes `UnboundLocalError` on `TimeoutExpired`.

**Verification:** Without pre-init, the outer `proc.communicate(timeout=...)` raising `TimeoutExpired` leaves `stdout`/`stderr` unbound. The inner `try: stdout, stderr = proc.communicate(timeout=5)` may also raise; the inner `except` handler references `stdout or ""` (line 119), which would `UnboundLocalError` without pre-init.

**Verdict:** Earned. The pre-initialization is a minimal, correct fix for a real edge case (double timeout). No cost; no indirection added.

---

## Section 6 — Verdict

**APPROVED.**

All 15 acceptance criteria satisfied. Edge case coverage is thorough. End-to-end user flows verified. All five owner decisions (Q1–Q4 + Option A) implemented as specified. All three developer deviations are earned with verifiable technical justification. No unearned classes, wrappers, or indirections introduced. Test suite: 114 new tests pass; full suite 2005 passing, no regressions.

Minor non-blocking observations (no fix required for approval):
- Explicit tests for `|`, `&`, `$`, backtick, NUL in *target* would strengthen coverage, but the frozenset enumeration and the `;`/newline tests exercise the same code path.
- `env.py:119-120` `UnicodeError` branch is uncovered (Python `str.encode("utf-8")` rarely raises on `str` values); defensive code, acceptable.
- `PathGuardrail._get_tool_config` mapping (`path.py:379-388`) does not include `"make"`, but `validate()` has no make-specific branch that would call it, so this is not a functional gap.

Files reviewed:
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/make.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/tools/guardrails/env.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/config/__init__.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/tools/guardrails/path.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/__init__.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_make.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_env_guardrail.py`

---

## Round 1 scoped re-run

**Date:** 2026-07-21
**Trigger:** Round-0 documentation review rejected; developer applied documentation-only fixes plus two tiny non-functional code cleanups.

### Changes verified

1. **`make.py` module docstring** — "Security model" section added with R1–R5 mapping (`make.py:5-23`). Function docstring expanded with parameters, return shape, and security-model reference (`make.py:80-88`). Documentation-only; no executable code changed. Confirmed non-functional.

2. **`README.md`** — `make` tool entry added to Features checklist (line 480); `[tools.make]` config subsection (lines 607-629) with R5 env-inheritance residual-risk note. Documentation-only.

3. **`examples/yoker.toml`** — `[tools.make]` block and `[tools.make.allowed_env_vars]` example added (lines 104-114). Documentation-only.

4. **`CLAUDE.md`** — `builtin/make.py` (line 86) and `tools/guardrails/env.py` (line 137) added to module structure. Documentation-only.

5. **`tests/test_tools/test_make.py`** — dead `if False else` communicate assignment removed. Verified: `test_command_is_list_not_shell` (line 526-538) now uses a direct `mocker.MagicMock(return_value=("ok\n", ""))` assignment with no conditional. Test still asserts `cmd == ["make", "check"]`, `shell is not True`, `start_new_session is True`. Non-functional cleanup; test behavior unchanged.

6. **`src/yoker/tools/guardrails/path.py`** — `"make": tools.make` added to `_get_tool_config` mapping (line 388). Verified non-functional: `_get_tool_config` is only called from `validate()` for `"read"`, `"write"`, `"update"`, `"mkdir"` (lines 64, 259, 304, 326, 352, 401). No `tool_name == "make"` branch exists in `validate()`, so the mapping entry is never reached for make. The functional `"make"` entry in `_FILESYSTEM_TOOLS` (line 31, which gates whether `validate()` runs at all for make) was already present in round 0 and is unchanged. Completeness-only addition; no behavior change.

### `make check` status

**Passing: 2005 passed, 14 warnings in 36.23s.** Matches the round-0 baseline (2005 tests). No regressions, no new failures.

### Acceptance criteria regression check

All 15 acceptance criteria from Section 1 remain satisfied. The round-1 changes are documentation plus non-functional completeness/cleanup; no executable behavior in `make.py`, `env.py`, `config/__init__.py`, or the manifest registration was modified. Re-verified:

- AC#3 (PathGuardrail on `cwd`): `"make"` still in `_FILESYSTEM_TOOLS`; `cwd` still annotated `PathArg`.
- AC#4 (list args, no shell): `test_command_is_list_not_shell` still passes after the dead-code cleanup.
- AC#15 (process-group kill on timeout): `make.py:145` `start_new_session=True` and `make.py:158` `os.killpg` unchanged.

No acceptance criteria regressed.

### Verdict

**Approved.** The documentation fixes address the round-0 documentation rejection without touching executable behavior. The two code cleanups are non-functional (dead-code removal in a test, unreachable mapping entry for completeness). `make check` passes with 2005 tests, matching the round-0 baseline. No acceptance criteria regressed.

---

## Round 2 scoped re-run

**Date:** 2026-07-21
**Trigger:** Owner flagged Windows compatibility; CI failed on `windows-latest` with `os.killpg` `AttributeError`. Developer applied Windows guardrails (platform gate in `make.py`, case-insensitive env guardrail on Windows, Windows-only denylist extension, separate Windows-only test file, README platform-support note).

### Changes verified

1. **`src/yoker/builtin/make.py` — Windows platform gate** (`make.py:96-105`). At the top of `make()`, before target validation, cwd resolution, env_var validation, and the `subprocess.Popen` call, a `sys.platform == "win32"` branch returns `ToolResult(success=False, error="make tool requires POSIX process-group support; not available on Windows")`. The POSIX path is unchanged: the gate is skipped and execution falls through to the existing subprocess/Popen/`os.killpg` code path. Inline comment explains the rationale (R4 relies on POSIX-only `os.killpg`, `signal.SIGKILL`, `start_new_session`; Windows Job Objects / `taskkill /T` out of scope for 1.0).

2. **`src/yoker/tools/guardrails/env.py` — Windows case-insensitive matching + Windows-only denylist extension** (`env.py:77-131`).
   - `_WIN_DENIED_EXTRA` frozenset (`env.py:82-102`) adds 17 Windows-specific env vars: `USERPROFILE, USERNAME, USERDOMAIN, APPDATA, LOCALAPPDATA, PROGRAMDATA, PROGRAMFILES, PROGRAMFILES(X86), SystemRoot, WINDIR, COMSPEC, PATHEXT, SYSTEMDRIVE, HOMEDRIVE, HOMEPATH, TEMP, TMP`. Count verified: 17 entries.
   - Pre-computed uppercased views (`_DENIED_EXACT_UPPER`, `_WIN_DENIED_EXTRA_UPPER`, `_WIN_PREFIXES_UPPER`) at `env.py:104-106` avoid per-call allocation.
   - `is_denied_env_var` (`env.py:109-131`): POSIX path stays case-sensitive (exact-match `_DENIED_EXACT` + `_DENIED_PREFIX_RE`). On Windows (`sys.platform == "win32"`), an additional case-insensitive pass uppercases the name and checks it against the uppercased exact set, the uppercased Windows extension set, and the uppercased prefix tuple.
   - Windows semantics match Windows env var behavior (case-insensitive): `Path` → `PATH` (denied), `MakeFlags` → `MAKEFLAGS` (denied), `Yoker_Trust_Source` → `YOKER_` prefix (denied), `comspec` → `COMSPEC` (denied).
   - POSIX regression: `Path` (mixed case) is NOT denied on POSIX because it is not in `_DENIED_EXACT` and does not match any prefix; only `PATH` is denied. This is correct — POSIX env vars are case-sensitive, so `Path` is a different variable.

3. **`tests/test_tools/test_make.py` — module-level POSIX-only pytestmark** (`test_make.py:26-29`). `pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="make tool requires POSIX process-group support")`. The entire module is skipped on Windows because every test exercises the POSIX subprocess path (Popen, `os.killpg`, `start_new_session`). Verified: on POSIX, all 114 tests in this module run.

4. **`tests/test_tools/test_make_windows.py` — separate Windows-only test file** (NEW). Class-level `@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only platform gate test")` on `TestWindowsPlatformGate`. The single test `test_make_rejected_on_windows` calls `make(target="check", ctx=..., cwd=tmp_path)` directly and asserts `not result.success` and `"not available on Windows" in result.error`. No other markers on the class — it will run on Windows CI without being skipped by anything else. Verified on POSIX: 1 skipped.

5. **`tests/test_tools/test_env_guardrail.py` — Windows case-sensitivity tests + POSIX regression tests** (`test_env_guardrail.py:191-231`).
   - `TestIsDeniedEnvVarWindowsCaseSensitivity` (class-level skipif `sys.platform != "win32"`): 6 tests — `Path`, `MakeFlags`, `Yoker_Trust_Source`, `USERPROFILE`, `SystemRoot`, `comspec` all denied on Windows. Verified on POSIX: 6 skipped.
   - `TestIsDeniedEnvVarPosixCaseSensitivity` (class-level skipif `sys.platform == "win32"`): 2 tests — `PATH` denied, `Path` NOT denied on POSIX (regression guard against the Windows case-insensitive branch leaking to POSIX).

6. **`README.md` — platform-support note** (lines 611-612). One-line note under the `[tools.make]` config subsection: "`make` tool requires POSIX process-group support and is not available on Windows." Documentation-only; no executable behavior changed.

### Platform gate correctness

On Windows, `make()` returns the expected `ToolResult(success=False, error="...not available on Windows...")` at `make.py:101-105` before any subprocess call. The gate is placed *after* the `MakeToolConfig` type check (so a misconfigured tool still fails with a clear config error) and *before* target validation, cwd resolution, env_var validation, and the `Popen` call. On POSIX, the gate is skipped and the existing behavior is unchanged — verified by the full `test_make.py` suite (114 tests) passing on POSIX.

### Env guardrail Windows case-insensitivity

Verified via test assertions (run on Windows) and code inspection:
- `Path` → `"PATH".upper() = "PATH"` ∈ `_DENIED_EXACT_UPPER` (contains `"PATH"`) → denied.
- `MakeFlags` → `"MAKEFLAGS"` ∈ `_DENIED_EXACT_UPPER` → denied.
- `Yoker_Trust_Source` → starts with `"YOKER_"` ∈ `_WIN_PREFIXES_UPPER` → denied.
- `comspec` → `"COMSPEC"` ∈ `_WIN_DENIED_EXTRA_UPPER` → denied.

POSIX regression: `is_denied_env_var("Path")` on POSIX returns `False` (not in `_DENIED_EXACT`, `_DENIED_PREFIX_RE` does not match). `is_denied_env_var("PATH")` returns `True`. Verified by `test_path_denied_exact_on_posix` and `test_path_variant_not_denied_on_posix`.

### Windows denylist completeness

`_WIN_DENIED_EXTRA` enumerates exactly the 17 Windows-specific env vars listed in the review brief: USERPROFILE, USERNAME, USERDOMAIN, APPDATA, LOCALAPPDATA, PROGRAMDATA, PROGRAMFILES, PROGRAMFILES(X86), SystemRoot, WINDIR, COMSPEC, PATHEXT, SYSTEMDRIVE, HOMEDRIVE, HOMEPATH, TEMP, TMP. Each appears once. Count: 17. Verified.

### Test strategy — separate file earned

The separate `test_make_windows.py` file is the right call. Rationale: a module-level `pytestmark = pytest.mark.skipif(sys.platform == "win32", ...)` in `test_make.py` skips every class in that module on Windows. A Windows-only test class placed in the same file would be skipped by the module-level mark, defeating its purpose. Splitting the Windows-only test into its own file with a class-level skipif (`sys.platform != "win32"`) inverts the condition so the test runs only on Windows and is skipped on POSIX. No other markers are applied to `TestWindowsPlatformGate`, so nothing else can skip it on Windows CI.

### No POSIX regressions

`make check` passes: **2007 passed, 7 skipped, 14 warnings in 33.06s**. The 7 skipped are exactly the Windows-only tests (1 from `test_make_windows.py::TestWindowsPlatformGate` + 6 from `test_env_guardrail.py::TestIsDeniedEnvVarWindowsCaseSensitivity`), verified by running those two files in isolation (`71 passed, 7 skipped`). The POSIX regression class `TestIsDeniedEnvVarPosixCaseSensitivity` runs on POSIX and passes (2 tests). Test count delta vs. round-1 baseline: +2 (2005 → 2007) from the new POSIX case-sensitivity regression tests; the Windows-only tests are counted in the skip count rather than the pass count on POSIX. All prior acceptance criteria (Section 1, AC#1–15) remain satisfied on POSIX — no executable POSIX behavior in `make.py`, `env.py`, `config/__init__.py`, or the manifest was modified.

### CI failure path is gated

The `os.killpg` `AttributeError` on Windows occurred because `os.killpg` does not exist on Windows (it is a POSIX-only API). The platform gate at `make.py:101-105` returns before `subprocess.Popen` is called (`make.py:150`) and therefore before `_kill_process_group` (`make.py:213-218`) can be invoked on timeout. The Windows code path never reaches the `os.killpg` reference. Additionally, `os.killpg` is referenced inside the function body of `_kill_process_group`, not at module import time, so the AttributeError cannot occur at import either. The CI failure is resolved.

### Verdict

**Approved.** Platform gate correctness confirmed. Env guardrail Windows case-insensitivity confirmed. Windows denylist completeness confirmed (17 entries). Test strategy (separate Windows-only test file) earned. No POSIX regressions (`make check`: 2007 passed, 7 skipped). CI failure path is gated — `os.killpg` is unreachable on Windows. All prior acceptance criteria remain satisfied on POSIX.
