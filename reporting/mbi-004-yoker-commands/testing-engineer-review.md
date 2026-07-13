# Testing Engineer Review — MBI-004 Yoker Commands (Stage c)

**Reviewer:** testing-engineer
**Branch:** `feature/mbi-004-yoker-commands`
**Date:** 2026-07-13
**Scope:** Test quality review of all MBI-004 CLI subcommand tests.

## Summary

The MBI-004 test suite is **strong overall**: 209 tests pass (in the CLI/manifest
scope), security invariants are explicitly tested, and the two-phase resolve/load
design is well-covered. The tests follow the project's two-space indentation and
class-based grouping conventions. Mocks are used appropriately to isolate the
subcommand handlers without over-mocking to the point of testing only wiring.

A small number of quality issues and coverage gaps exist, none of which block
merge. They are listed below by severity.

**Verdict: approved** (with non-blocking recommendations).

## Test Files Reviewed

| File | Tests | Focus |
|------|-------|-------|
| `tests/test_cli/test_dispatch.py` | 21 | `_needs_default_chat`, `main()` routing, `--with` stripping |
| `tests/test_cli/test_chat.py` | 2 | Module importability only |
| `tests/test_cli/test_init.py` | 13 | Path resolution, write/overwrite, masking, confirmation |
| `tests/test_cli/test_config_cmd.py` | 13 | Masking, TOML/JSON output, `--show-path`, `--reveal` |
| `tests/test_cli/test_sources.py` | 28 | Detect kind, module/folder/github/zip resolve+load, security |
| `tests/test_cli/test_run.py` | 28 | Trust gate ordering, dry-run, prompt cap, overrides, cleanup |
| `tests/test_cli/test_loop.py` | 12 | Trust gate, max-iterations, backoff, max-duration, cleanup |
| `tests/test_cli/test_container.py` | 34 | Shell metachar rejection, JSON-array form, USER, SHA pinning |
| `tests/test_cli/test_inspect.py` | 9 | Read-only invariant, no trust gate, cleanup resilience |
| `tests/test_plugins/test_file_manifest.py` | 17 | Manifest parsing, type validation, no-import invariant |
| `tests/test_config/test_config_with_manifest.py` | 9 | Override cascade, CLI precedence, malformed handling |

## Coverage Snapshot (CLI scope)

| Module | Coverage | Notes |
|--------|----------|-------|
| `cli/__init__.py` | 100% | |
| `cli/commands.py` | 100% | |
| `cli/config_cmd.py` | 98% | Excellent |
| `cli/container.py` | 91% | Good |
| `cli/sources.py` | 88% | Good — SSRF private/metadata/localhost covered |
| `cli/inspect.py` | 87% | Good |
| `cli/run.py` | 74% | `_run_source`/`_register_source_agents` untested |
| `cli/loop.py` | 68% | `_run_iteration` body untested |
| `cli/shared.py` | 65% | `get_security_config` branch partially covered |
| `cli/init.py` | 52% | Interactive wizard path untested |
| `cli/chat.py` | 22% (76% via test_main.py) | REPL covered by test_main.py |

## Strengths

### Security invariants are explicitly tested
The most important quality signal: the security-critical invariants are tested
as invariants, not as side effects.

- `test_sources.py::TestTwoPhaseInvariant` patches `builtins.__import__` to
  *fail the test* if phase 1 imports `tools_module`. This is exactly the right
  way to test a "must not do X" security property.
- `test_run.py::TestTrustGateOrdering::test_load_source_not_called_when_untrusted`
  asserts `m_load.assert_not_called()` when the trust gate returns False — the
  security invariant is the assertion.
- `test_inspect.py::TestInspectNoTrustGate` verifies `check_source_allowed` is
  never called (read-only command must not gate on trust).
- `test_container.py` covers shell metacharacter rejection (`;`, `|`, `$`,
  backtick), JSON-array RUN/ENTRYPOINT form, non-root `USER 1000`, and SHA
  pinning for GitHub sources.

### Source security defenses are comprehensive
`test_sources.py` covers all the documented defenses:
- Zip bomb (high compression ratio rejected)
- Path traversal (`../` entries rejected)
- Absolute path entries rejected
- Symlink entries rejected (via `S_IFLNK` external_attr)
- Too-many-entries cap
- SSRF (private IP, metadata IP `169.254.169.254`, localhost)
- Non-HTTPS rejection
- Embedded credentials rejection
- Folder subpath containment (`skills_dir`/`agents_dir`/`tools_module`)

### Trust gate decision cascade is fully covered
`test_run.py::TestCheckSourceAllowed` and `TestNonInteractiveRejection` cover
all four branches of the cascade: pre-trusted in config, session-trusted
short-circuit, interactive accept, interactive reject, env-var override, and
non-interactive rejection. `reset_session_trusted()` is called in setup to
avoid cross-test leakage.

### Behavior-focused, not implementation-focused
Tests assert on observable outcomes (exit codes, stdout content, mock call
counts for security invariants) rather than internal state. The
`_parse_run_overrides` tests verify the cleaned argv and extracted values, not
the internal loop structure.

### Good test isolation
- `test_config_with_manifest.py` uses an autouse fixture to reset Clevis global
  state (`_reset_factories`) and re-register subcommand configs in teardown.
  The comment explains *why* (Config has no `cmd`, so its args leak to the root
  parser). This is well-documented isolation.
- `tmp_path` is used consistently for filesystem tests.
- `monkeypatch` is used for env/TTY mocking rather than mutating global state
  directly.

## Quality Issues (Non-Blocking)

### 1. `test_chat.py` is minimal — LOW value (risk: 2/10)
`test_chat.py` has only two tests, both asserting `callable(run_chat)` and
`callable(create_ui)`. These are "tests that never fail" — they verify the
module is importable, not that chat behavior works. The actual REPL/UI logic is
tested in `tests/test_main.py` (18 tests covering `create_ui`, `_run_repl`,
`_parse_plugin_args`, and one integration test), which brings `chat.py` to 76%
coverage.

**Why it's a minor issue:** The two callable-tests are low-value per the
testing guidelines ("Testing file existence / framework setup"). They don't
hurt, but they don't add confidence either.

**Recommendation:** Add a docstring note that `test_chat.py` is intentionally
thin because the REPL logic lives in `test_main.py` (this note already exists —
good). Optionally delete the two callable tests; the import is exercised by
`test_main.py`'s `from yoker.cli.chat import ...`.

### 2. `cli/init.py` interactive path untested — MEDIUM (risk: 5/10)
`_run_interactive` (lines 100-128) has 52% coverage. The interactive wizard
path (BootstrapWizard invocation, KeyboardInterrupt handling,
`result != WRITTEN` exit) is not tested. The non-interactive path is well
tested.

**Why it matters:** The interactive path includes a `KeyboardInterrupt` →
`abort(0)` branch and a `result != BootstrapResult.WRITTEN` → `sys.exit(0)`
branch. These are user-facing behaviors that could regress.

**Recommendation:** Add 2-3 tests for `_run_interactive`:
- Existing file without `--force` → abort(1)
- Non-TTY → abort(1) with the "requires a TTY" message
- Mocked wizard returning `WRITTEN` → no exit
- Mocked wizard raising `KeyboardInterrupt` → abort(0)

These can mock `BootstrapWizard` and `sys.stdin.isatty`.

### 3. `cli/run.py` `_run_source` and `_register_source_agents` untested — MEDIUM (risk: 5/10)
Lines 171-201 (`_run_source`: Session construction, component registration, UI
bridge wiring, `agent.process`, error handling) and 210-217
(`_register_source_agents`: source-wins-on-conflict) are not covered. The run
handler tests mock `asyncio.run` and `_run_source`, so the actual Session
integration is never exercised.

**Why it matters:** `_register_source_agents` implements the
"source wins on conflict" policy (owner-confirmed). If this logic breaks, a
source's agent definition could silently fail to override the built-in. This is
a behavioral contract worth testing.

**Recommendation:** Add a unit test for `_register_source_agents` directly:
- Empty `loaded.components.agents` → no-op
- Source agent with a name colliding with a builtin → builtin deleted, source
  registered
- Source agent with a unique name → registered without deletion

These can use a mock `Session` with a `agents.data` dict and `agents.register`
method.

### 4. `cli/loop.py` `_run_iteration` body untested — MEDIUM (risk: 5/10)
The loop tests mock `_run_iteration` entirely (`patch("yoker.cli.loop._run_iteration",
side_effect=fake_iteration)`). The actual iteration body — Session construction,
component registration, `agent.process`, UI shutdown — is never executed. This
mirrors the run.py gap.

**Why it matters:** `_run_iteration` is the per-iteration execution path. If
component registration or error handling breaks, the loop tests still pass
because `_run_iteration` is mocked.

**Recommendation:** This is acceptable given that `_run_iteration` mirrors
`_run_source` (same Session+register+process pattern). If `_run_source` gets
integration coverage, the duplication risk is low. Alternatively, add one test
that runs `_run_iteration` with a mock Session to verify the component
registration calls.

### 5. `cli/shared.py` `get_security_config` partial coverage — LOW (risk: 3/10)
Lines 24-29 (the `YOKER_DEV_MODE` / `PYTEST_CURRENT_TEST` branch returning
`SecurityConfig`) are partially covered. The `None` return path (production) is
not tested.

**Why it's minor:** This is a thin config helper. The behavior is trivial.

**Recommendation:** Optional — add one test asserting `get_security_config()`
returns `None` when neither env var is set.

## Test Gaps (Could Miss Regressions)

### G1. No end-to-end `run_run` test with a real source — MEDIUM (risk: 6/10)
`test_run.py` mocks `resolve_source`, `load_source`, `check_source_allowed`, and
`asyncio.run`. No test exercises the full flow: resolve a folder source on disk
→ trust gate → load → apply overrides → run. The `--dry-run` test is the closest
to end-to-end but stops before execution.

**Impact:** A regression in the wiring between resolve → trust → load →
overrides → run would not be caught. The individual pieces are tested, but the
integration is not.

**Recommendation:** Add one integration test in `test_run.py` that:
- Creates a folder with `agent.toml` + a skill on `tmp_path`
- Patches `check_source_allowed` to return True
- Patches `asyncio.run` (to avoid needing a real backend)
- Calls `run_run([])`
- Asserts `resolve_source` and `load_source` were called with the right args
  and that `asyncio.run` was called (not `_run_source` directly, since that's
  mocked)

This would verify the end-to-end ordering without needing a live LLM.

### G2. No test for config override application in `run_run` end-to-end — LOW (risk: 3/10)
`TestApplyConfigOverrides` tests `_apply_config_overrides` in isolation (good),
but no test verifies that `run_run` actually calls it when
`resolved.manifest.config_overrides` is non-empty. The dry-run test has a
manifest with empty overrides.

**Recommendation:** Add a test where `resolved.manifest.config_overrides` has a
`backend.ollama.model` override and verify the config passed to `asyncio.run`
has the overridden value.

### G3. `test_loop.py` backoff test is slightly fragile — LOW (risk: 3/10)
`TestRunLoopBackoff::test_backoff_increases_with_failures` asserts:
```python
backoff_sleeps = [s for s in sleep_calls if s in (2, 4, 8)]
assert len(backoff_sleeps) >= 1
assert 2 in backoff_sleeps
```
This only checks that at least one backoff sleep of 2s occurred. It doesn't
verify the exponential sequence (2, 4, 8). The test would pass even if the
backoff were constant at 2s.

**Recommendation:** Tighten the assertion to verify the sequence:
```python
assert 2 in sleep_calls
assert 4 in sleep_calls
```
This confirms the exponential growth without being overly exact about ordering
(the interval sleep at 0s interleaves).

### G4. No test for `--max-iterations 0` or negative values — LOW (risk: 2/10)
`test_loop.py` doesn't test edge cases of `max_iterations`. A value of 0 would
skip the loop entirely (range(1, 1) is empty). Negative values would also
produce an empty range. These are edge cases that could surface as
"loop ran zero iterations" confusion.

**Recommendation:** Add one test with `max_iterations=0` asserting the loop
completes with 0 iterations and prints a summary.

## Positive Observations

- **Test naming is clear and behavior-focused**: `test_load_source_not_called_when_untrusted`,
  `test_dockerfile_has_non_root_user`, `test_symlink_entry_rejected`. Names
  describe the behavior, not the implementation.
- **Gherkin-style docstrings** would be nice but aren't required; the test names
  and class groupings are self-documenting.
- **Mock usage is appropriate**: mocks isolate I/O (git, tempdirs, asyncio) and
  security gates, not internal logic. The `builtins.__import__` guard in
  `TestTwoPhaseInvariant` is a particularly elegant way to test a
  "must not import" invariant.
- **Error message assertions are flexible**: tests use `pytest.raises(PluginError,
  match="SSRF|private IP")` with alternation, not exact strings. This follows
  the testing guidelines.
- **No flaky tests observed**: the suite runs in ~3.6s and is deterministic.
  No real timers, no real network, no real git clones.
- **Cleanup is tested**: `TestCleanup` in run/loop/inspect verifies
  `cleanup.assert_called_once()` on both success and error paths. The
  `test_cleanup_failure_does_not_raise` test in `test_inspect.py` verifies
  cleanup errors are swallowed (good defensive coverage).

## Recommendations Summary

| Priority | Item | Effort |
|----------|------|--------|
| Non-blocking | Add tests for `_run_interactive` (init.py) | Small |
| Non-blocking | Add unit test for `_register_source_agents` (run.py) | Small |
| Non-blocking | Add one end-to-end `run_run` integration test | Medium |
| Non-blocking | Tighten backoff sequence assertion (loop) | Trivial |
| Optional | Delete the two callable-tests in test_chat.py | Trivial |
| Optional | Add `max_iterations=0` edge case (loop) | Trivial |
| Optional | Test `get_security_config` None-return path | Trivial |

## Verdict

**approved**

The test suite is of high quality. Security invariants are tested as
invariants, the two-phase resolve/load design is well-covered, error paths are
tested, and test isolation is solid. The identified gaps are in integration
coverage (the wiring between already-tested pieces) and a couple of untested
helper functions, none of which represent a regression risk significant enough
to block merge. The recommendations above are improvements that can be made
in a follow-up.