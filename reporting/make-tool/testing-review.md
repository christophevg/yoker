# Testing Review — `make` tool (PR #48, Stage c)

**Reviewer:** testing-engineer
**Date:** 2026-07-21
**Branch:** `feature/make-tool` (PR #48)
**Files under review:**
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_make.py`
- `/Users/xtof/Workspace/agentic/yoker/tests/test_tools/test_env_guardrail.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/builtin/make.py`
- `/Users/xtof/Workspace/agentic/yoker/src/yoker/tools/guardrails/env.py`

**Test execution:** 114 tests collected, 114 passed (12.6s).
**Focused coverage:** `make.py` 90%, `env.py` 95%.

---

## Section 1 — Coverage assessment (code paths → tested?)

| Code path | Location | Tested? | Test(s) |
|---|---|---|---|
| Target type check (non-string) | `make.py:51-52` | Yes | `test_non_string_target_rejected` |
| Empty/whitespace target | `make.py:54-55` | Yes | `test_empty_target_rejected` (parametrized `["", "   ", "\t"]`) |
| Leading-`-` target | `make.py:56-57` | Yes | `test_leading_dash_rejected`, `test_flag_injection_rejected` (`["-i", "-j", "-C /tmp"]`) |
| Overlong target (>256) | `make.py:58-59` | Yes | `test_overlong_target_rejected` (257 chars) |
| Target regex mismatch | `make.py:60-61` | Yes | `test_target_with_space_rejected`, `test_target_with_semicolon_rejected`, `test_target_with_newline_rejected` |
| Forbidden-chars frozenset loop | `make.py:62-64` | **No** | See §6 — regex catches all forbidden chars first; loop is unreachable in current tests |
| `Path(cwd).resolve()` OSError/ValueError | `make.py:69-70` | No | Defensive; see §6 |
| env_vars not a dict | `make.py:75-76` | Yes | `test_env_vars_not_dict_rejected` |
| Per-target allowlist lookup | `make.py:77` | Yes | `test_env_var_denied_when_target_not_in_allowlist`, `test_env_var_denied_when_name_not_in_per_target_tuple` |
| `validate_env_vars` allowlist check | `env.py:107-108` | Yes | `test_var_not_in_allowlist_rejected`, `test_env_var_denied_when_*` |
| `validate_env_vars` hard-denylist check | `env.py:109-110` | Yes | `test_makeflags_denied_even_if_allowlisted`, `test_denied_var_rejected_even_if_allowlisted`, `test_denied_yoker_prefix_rejected_even_if_allowlisted` |
| `validate_env_vars` value type check | `env.py:111-112` | Yes | `test_non_string_value_rejected` |
| `validate_env_vars` NUL check | `env.py:113-114` | Yes | `test_nul_byte_in_value_rejected` |
| `validate_env_vars` newline/CR check | `env.py:115-116` | Yes | `test_newline_in_value_rejected`, `test_carriage_return_in_value_rejected` |
| `validate_env_vars` UnicodeError | `env.py:119-120` | **No** | See §6 — unreachable on `str` values in practice |
| `validate_env_vars` byte-length check | `env.py:121-122` | Yes | `test_oversize_value_rejected` (4097), `test_value_at_limit_passes` (4096 exact) |
| Timeout clamp (caller > config ceiling) | `make.py:85` | Yes | `test_timeout_clamped_to_config_ceiling` (60s → 1s) |
| Timeout clamp (caller < 1s floor) | `make.py:85` | Yes | `test_timeout_minimum_one_second` (50ms → 1000ms) |
| Timeout expired → killpg + reaped | `make.py:112-124` | Yes | `test_timeout_returns_failure`, `test_process_group_killed_on_timeout` |
| `Popen` FileNotFoundError (make not installed) | `make.py:102-104` | Yes | `test_make_not_installed` (mocked) |
| `Popen` NotADirectoryError | `make.py:105-106` | No | Defensive; see §6 |
| Output truncation (over-limit) | `make.py:127-129, _truncate` | Yes | `test_output_truncated_when_over_limit` (~200KB, cap 100KB) |
| Output truncation (under-limit) | `make.py:127-129` | Yes | `test_small_output_not_truncated` |
| Non-zero exit → structured result | `make.py:131-140` | Yes | `test_nonzero_exit_still_returns_structured_result` (exit 2), `test_missing_makefile_returns_nonzero` |
| Invalid config type | `make.py:46-48` | No | Defensive; see §6 |
| `_kill_process_group` exception handlers | `make.py:160-161` | No | Best-effort; see §6 |

**Verdict on coverage:** All functional paths exercised. The uncovered lines are defensive branches (5 of them) plus the unreachable forbidden-chars loop. None block approval.

---

## Section 2 — Test meaningfulness (behavior vs implementation)

**Strong — behavior-focused:**
- Target rejection tests assert on `result.success` and error substrings (`"invalid"`, `"empty"`, `"flag"`, `"-"`) — verify the user-facing rejection, not the regex internals.
- env_vars tests assert on `result.error.lower()` containing `"allowlist"`, `"hard-denylist"`, `"exceeds"`, `"newline"`, `"nul"` — verify the rejection reason the operator/agent sees, not the internal validation order.
- `test_env_var_allowed_and_propagated` verifies end-to-end behavior: the env var actually reaches `make` (the Makefile echoes `$(TEST)` and the assertion checks the stdout contains the value). This is the strongest kind of test — it proves the whole pipeline works, not just the validator.
- `test_process_group_killed_on_timeout` mocks `os.killpg` and asserts it was called with an int pid and `SIGKILL`. This is the right level of mocking — it verifies R4 (process-group kill) without depending on real subprocess timing.
- `test_command_is_list_not_shell` mocks `subprocess.Popen` and asserts `cmd == ["make", "check"]`, `shell is not True`, `start_new_session is True` — verifies the security invariants (no shell, list argv, new session) directly. Acceptable: these ARE the security invariants, not implementation trivia.
- Truncation test asserts both `truncated is True`, the notice is present, AND a byte-bound upper bound on the output — verifies the cap is enforced, not just that a flag flips.

**Borderline — implementation-leaning but justified:**
- `test_make_in_filesystem_tools` asserts `"make" in _FILESYSTEM_TOOLS`. This is a one-liner implementation check, but it verifies R1 wiring (without it, the PathGuardrail is a silent no-op per the consensus doc). The functional review flagged this as load-bearing. Acceptable.
- `test_schema_has_cwd_path_guard` asserts `spec.guards["cwd"] == GuardType.PATH`. Same justification — verifies the security annotation is wired into the schema. Acceptable.
- `test_name`, `test_description_present`, `test_schema_target_required` — framework-registration tests. Low value per the testing anti-patterns table, but they're three one-liners that confirm the tool is registered correctly. Tolerable; not worth removing.

**No anti-patterns found:** no `assert True`, no empty bodies, no parametrized tests with a single case (each parametrize has 2+ cases), no fixture-for-single-use (the `makefile_dir` fixture is used by multiple tests in each class), no over-mocking (real `make` is invoked for happy paths; mocks only for FileNotFoundError, Popen shape, and killpg verification).

---

## Section 3 — Edge case coverage

| Edge case | Covered? | Notes |
|---|---|---|
| Empty target `""` | Yes | parametrized `["", "   ", "\t"]` |
| Whitespace-only target | Yes | same parametrize |
| Leading-`-` target | Yes | `--eval=...`, `-i`, `-j`, `-C /tmp` |
| Newline in target | Yes | `test_target_with_newline_rejected` |
| Semicolon in target | Yes | `test_target_with_semicolon_rejected` |
| `\|`, `&`, `$`, backtick, NUL in target | Logic covered, not individually tested | Regex rejects them; frozenset loop is unreachable (see §6). The `;` and newline tests exercise the regex path that all five would also take. Behavior is verified. |
| Overlong target (>256) | Yes | 257 chars |
| Non-string target | Yes | `123` |
| MAKEFLAGS in env even when allowlisted | Yes | `test_makeflags_denied_even_if_allowlisted` — explicit hard-denylist-wins test |
| YOKER_* in env even when allowlisted | Yes | `test_denied_yoker_prefix_rejected_even_if_allowlisted` |
| Target not in allowlist dict → deny all | Yes | `test_env_var_denied_when_target_not_in_allowlist` (target `build`, dict has only `test`) |
| Target in dict but var not in tuple | Yes | `test_env_var_denied_when_name_not_in_per_target_tuple` |
| Empty allowlist tuple → deny all | Yes | `test_empty_allowlist_rejects_all` (env_guardrail unit test) |
| Empty env_vars `{}` | Yes | `test_empty_env_vars_ok` |
| env_vars=None | Yes | `test_env_vars_none_ok` |
| env_vars not a dict | Yes | `test_env_vars_not_dict_rejected` (`"TEST=foo"`) |
| Oversize value (>4096) | Yes | 4097 bytes |
| Value at exact limit (4096) | Yes | `test_value_at_limit_passes` |
| NUL in value | Yes | `test_nul_byte_in_value_rejected` |
| Newline in value | Yes | `\n` and `\r` both tested |
| Non-string value | Yes | `123` |
| Returns first failing entry | Yes | `test_returns_first_failure` |
| Missing Makefile | Yes | `test_missing_makefile_returns_nonzero` (no pre-check; make emits stderr) |
| make not installed | Yes | mocked `FileNotFoundError` |
| Timeout | Yes | 1s timeout against `sleep 10` |
| Timeout clamp (caller > ceiling) | Yes | 60s caller, 1s config ceiling → 1s |
| Timeout clamp (caller < floor) | Yes | 50ms caller → 1000ms |
| Process-group kill on timeout | Yes | mocked `os.killpg` — asserts pid is int and signal is `SIGKILL` |
| Output truncation (over) | Yes | ~200KB stdout, cap 100KB — asserts `truncated=True`, notice present, byte-bound |
| Output truncation (under) | Yes | small output — `truncated=False` |
| **Output truncation at exact boundary** | **No** | No test runs output at exactly 100KB. `test_value_at_limit_passes` covers the env-var-value boundary, but not the output boundary. Minor gap — see §6. |
| **Per-stream independent truncation** | **No** | No test verifies stdout-truncated + stderr-not (or vice versa) independently sets the `truncated` flag while preserving the non-truncated stream's full content. The implementation handles it (lines 127-129 truncate each stream independently), and `test_stderr_separate_from_stdout` verifies streams are reported independently, but the combined `truncated` flag is only tested when stdout exceeds. Minor gap — see §6. |
| Non-zero exit still returns structured result | Yes | exit 2 — asserts `exit_code`, `stdout`, `stderr` all present |
| Streams reported independently | Yes | `test_stderr_separate_from_stdout` — OUT in stdout only, ERR in stderr only |

**Verdict on edge cases:** Thorough. Two minor gaps (exact-boundary output truncation, per-stream independent truncation flag) — neither blocks approval; see §6.

---

## Section 4 — Integration / end-to-end

Two end-to-end tests against real Makefiles in `tmp_path`:

1. `test_make_check_end_to_end`: `make(target="check")` against a Makefile with `check:` and `test:` targets. Asserts `success` and `"running-check"` in stdout. Verifies the full pipeline: PathGuardrail → target validation → `Popen(["make", "check"])` → communicate → structured result.

2. `test_make_test_with_env_end_to_end`: `make(target="test", env_vars={"TARGET": "tests/test_foo.py"})` with `MakeToolConfig(allowed_env_vars={"test": ("TARGET",)})`. The Makefile echoes `$(TARGET)`. Asserts the env var value appears in stdout. Verifies the full env-var pipeline: per-target allowlist lookup → `validate_env_vars` → env merge → `make` sees the var → output captured.

Both use real `make` (not mocked) and real Makefiles (written into `tmp_path`). This is the strongest form of integration test — it exercises every layer from the tool entry point through subprocess execution to result structuring.

**Owner's approved design acceptance criterion #7** ("Agent can run `make check`, `make test`, etc."): satisfied by these two tests.

---

## Section 5 — Test isolation / hermeticity

**Hermetic:**
- All Makefiles are written into `tmp_path` (pytest's per-test temporary directory). No cross-test contamination.
- `test_make_not_installed` mocks `subprocess.Popen` to raise `FileNotFoundError` — does not depend on the host having/lacking make.
- `test_process_group_killed_on_timeout` mocks `os.killpg` — does not leave orphaned processes.
- `test_command_is_list_not_shell` mocks `subprocess.Popen` — does not actually run make.
- env_guardrail tests are pure unit tests — no filesystem, no subprocess.

**Not hermetic (project convention):**
- Most make tests invoke the real `make` binary. If `make` is not installed, these tests fail. No `@pytest.mark.skipif(shutil.which("make") is None)` guard.
- Some tests invoke `python3`, `sleep`, `echo` via the Makefile. Standard on CI and dev machines.
- This matches the existing project convention: `tests/test_tools/test_git.py` similarly invokes real `git` without a skip guard. Acceptable for this project.

**Timeout tests are hermetic:** `test_timeout_returns_failure` uses `sleep 10` with a 1s timeout — the test completes in ~1s, not 10s. `test_timeout_clamped_to_config_ceiling` uses `sleep 5` with clamped 1s timeout — completes in ~1s. Good.

**Verdict on isolation:** Acceptable. Follows project convention. The non-hermeticity (real `make`) is a conscious project-wide choice, not a regression introduced by this PR.

---

## Section 6 — Gaps that matter vs gaps that don't

### Gaps that DON'T matter (do not block approval)

1. **`|`, `&`, `$`, backtick, NUL in target — not individually tested.**
   The regex `_TARGET_RE = ^[A-Za-z0-9][A-Za-z0-9._%+\-]*$` rejects all of them (none of these chars are in the allowed set). The `;` and newline tests exercise the same regex-rejection path. The frozenset loop at `make.py:62-64` is a belt-and-suspenders defense that is currently unreachable because the regex catches first — but the *behavior* (these chars are rejected) is verified by the regex-path tests. Adding five more parametrize cases would strengthen the spec but would not catch a regression the existing tests miss. **Non-blocking.**

2. **`env.py:119-120` `UnicodeError` branch — uncovered.**
   `str.encode("utf-8")` on a `str` value cannot raise `UnicodeError` in Python 3 (all `str` are valid Unicode by construction). This branch is defensive against a Python invariant. Adding a test would require constructing a non-`str` value that passes the `isinstance(value, str)` check at line 111 — impossible without mocking. **Non-blocking.**

3. **`make.py:47-48` invalid config type — uncovered.**
   `if not isinstance(make_config, MakeToolConfig)` — defensive against a misconfigured tool registry. The framework guarantees the right config type is passed. **Non-blocking.**

4. **`make.py:69-70` `Path(cwd).resolve()` OSError/ValueError — uncovered.**
   Defensive against filesystem errors during path resolution. Hard to trigger reliably in a test. **Non-blocking.**

5. **`make.py:105-106` `NotADirectoryError` — uncovered.**
   Defensive against `cwd` pointing to a file. Could be tested with a tmp_path file, but low risk. **Non-blocking.**

6. **`make.py:160-161` `_kill_process_group` exception handlers — uncovered.**
   Best-effort cleanup on timeout. The happy path (killpg succeeds) is verified by `test_process_group_killed_on_timeout`. The exception handlers log and continue — testing them would require mocking killpg to raise, which tests a logging side effect, not behavior. **Non-blocking.**

### Gaps that MATTER (minor — would strengthen the suite, but not blocking)

1. **Per-stream independent truncation.** The implementation truncates stdout and stderr independently (`make.py:127-129`) and aggregates the flag (`stdout_truncated or stderr_truncated`). No test verifies the case where only ONE stream exceeds the cap. A test that produces large stderr and small stdout (e.g., `@echo small; @python3 -c "import sys; sys.stderr.write('y' * 200000)"`) would verify: `truncated is True`, stderr has the notice, stdout is the full small content. **Low risk** — the implementation is obviously correct (`or` of two booleans) and `test_stderr_separate_from_stdout` already verifies streams are reported independently. **Recommendation, not a blocker.**

2. **Output truncation at exact boundary.** No test runs output at exactly 100KB to verify the boundary condition (`len(encoded) <= max_bytes` returns `False, text` — i.e., not truncated). `test_value_at_limit_passes` covers this for env-var values; the same boundary logic for output is uncovered. **Very low risk** — the `_truncate` function is 5 lines and the boundary check is `<=`. **Recommendation, not a blocker.**

3. **No skip-if-make-not-installed guard.** Tests fail on hosts without `make`. Matches project convention (git tests do the same), so consistent. A `pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")` would make the suite more portable. **Project-convention call, not a blocker.**

---

## Section 7 — Verdict

**APPROVED.**

All acceptance criteria from `per-target-allowlist-response.md` have corresponding tests. The test suite is behavior-focused, assertions are specific, edge cases are thorough, and two end-to-end integration tests verify the full pipeline against real Makefiles. The 114 tests pass; focused coverage is 90% on `make.py` and 95% on `env.py`. The uncovered lines are defensive branches that are either unreachable in practice (`UnicodeError` on `str.encode`) or guard against framework-invariant violations (invalid config type, `NotADirectoryError`, killpg exception handlers).

The two gaps the functional review noted (`|`, `&`, `$`, backtick, NUL in target; `env.py:119-120` UnicodeError) are correctly classified as non-blocking — the behavior is tested via the regex path, and the UnicodeError branch is unreachable.

Three minor recommendations (non-blocking, would strengthen the suite):
1. Add a per-stream independent truncation test (large stderr + small stdout → `truncated=True`, stderr truncated, stdout preserved).
2. Add an exact-boundary output truncation test (100KB output → `truncated=False`).
3. Consider a `skipif(shutil.which("make") is None)` marker for portability (project-convention call).

None of these justify rejecting an otherwise thorough, behavior-focused, well-isolated test suite.