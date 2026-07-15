# Testing Review: Clevis 0.7.0 Upgrade

## Summary

The Clevis 0.7.0 upgrade replaces manual workarounds (the `_needs_default_chat`
function and Clevis internal API bypasses) with native Clevis public APIs
(`default_cmd=True`, `build_default_cascade`, `clevis.load`). The test suite
passes (343 tests in the relevant modules, 1841 overall) and several areas have
strong coverage. However, two significant coverage gaps remain:
`load_subcommand_config_with_manifest()` has zero direct tests, and the
`default_cmd=True` routing behavior is never verified end-to-end (all dispatch
tests mock `get_cmd`).

## Coverage Data

| Module                      | Coverage | Uncovered Lines           |
|-----------------------------|----------|---------------------------|
| `yoker/cli/shared.py`       | 61%      | 82-141 (entire `load_subcommand_config_with_manifest`) |
| `yoker/cli/run.py`          | 65%      | 107-111 (manifest reload), 158-188 (`_run_source`) |
| `yoker/cli/inspect.py`       | 86%      | 185-196 (`_read_dependencies` with pyproject.toml) |
| `yoker/config/__init__.py`  | 95%      | Good coverage              |
| `yoker/plugins/file_manifest.py` | 91% | Good coverage              |
| `yoker/__main__.py`          | 61%      | 74-95 (`_parse_plugin_args` body) |

## Critical Gaps (Risk 8-10)

### 1. `load_subcommand_config_with_manifest()` has ZERO tests (Risk 9)

**Location:** `src/yoker/cli/shared.py` lines 82-141

**Problem:** This function is a complex 5-step cascade that directly uses Clevis
internals (`apply_to_dict`, `get_factory`, `load_toml_from_fd`,
`check_directory_permissions`, `check_file_permissions`, `deep_merge`,
`ConfigError`, dacite `from_dict`). It is called by `run_run()` (line 108) and
`run_loop()` (line 110) to apply manifest config overrides from a source AFTER
the trust gate passes. No test in the entire suite exercises this function.

**Why it matters:** This is security-relevant code. It applies config overrides
from an external source (agent.toml) into the user's configuration. The function
must correctly implement the cascade: `dataclass defaults -> user TOML -> project
TOML -> subcommand section extraction -> manifest overrides -> CLI args`. If any
step is wrong, a source could override security-relevant config fields (e.g.,
disabling tools, changing backend) in unintended ways. The function also runs
`__post_init__` validation on the final merged dict — if this is bypassed,
invalid configurations could pass through.

**What should be tested:**
- Manifest overrides are applied (e.g., `[backend.ollama] model = "X"` changes
  the config)
- CLI args take precedence over manifest overrides
- Subcommand section extraction works (e.g., `[run]` section is used for
  RunConfig, not mixed into the base config)
- Empty manifest overrides dict is a no-op (function behaves like
  `load_subcommand_config`)
- `__post_init__` validation runs on the final merged config (invalid values
  raise errors)
- User TOML + project TOML + manifest + CLI all layer correctly in order

**Why the existing tests miss this:** In `test_run.py`, all tests that reach the
trust gate either (a) set `resolved.manifest = None` (default in
`_make_resolved()`), or (b) use `dry_run=True` which exits before line 108. The
`config_overrides` dict is never set to a non-empty value in any test, so the
`if resolved.manifest is not None and resolved.manifest.config_overrides:`
guard at line 106 is never truthy. The function is never called.

### 2. No integration test for `default_cmd=True` routing (Risk 7)

**Location:** `src/yoker/cli/commands.py` line 26, `src/yoker/__main__.py`

**Problem:** The `TestMainDefaultChat` class in `test_dispatch.py` (lines 83-102)
mocks `get_cmd` to return `"chat"` or `"run"`. This tests that `main()` dispatches
correctly based on the return value of `get_cmd()`, but it does NOT verify that
Clevis's `default_cmd=True` on `ChatConfig` actually causes `get_cmd()` to return
`"chat"` when no subcommand is given. The entire Clevis 0.7.0 upgrade hinges on
this behavior working, but no test verifies it end-to-end.

**Why it matters:** If `default_cmd=True` is misconfigured, doesn't work with
yoker's specific `@configclass(cmd="chat", default_cmd=True, ...)` setup, or
breaks in a future Clevis version, users running bare `yoker` would get an error
or wrong behavior. The old `TestNeedsDefaultChat` class (removed in this upgrade)
had 9 tests verifying the manual workaround logic. The replacement has 2 tests
that both mock the function being tested.

**What should be tested:**
- Bare `yoker` (sys.argv = `["yoker"]`) routes to `run_chat` WITHOUT mocking
  `get_cmd`
- `yoker --help` shows help (does NOT route to chat) — edge case that the old
  tests explicitly covered
- `yoker --backend-ollama-model X` routes to `run_chat` (backward compat — flags
  without subcommand default to chat)
- Unknown subcommand (e.g., `yoker bogus`) produces an argparse error, not
  silent routing to chat

**Note:** An integration test would need to handle the full Clevis parser setup
and potentially mock only the handler (e.g., `run_chat`), not `get_cmd` itself.
This is harder to write but necessary to verify the actual behavior.

## Important Gaps (Risk 5-7)

### 3. Removed `TestNeedsDefaultChat` coverage not fully replaced (Risk 6)

The removed class had 9 tests covering specific routing decisions:

| Old Test                                    | Replacement Coverage |
|---------------------------------------------|---------------------|
| Bare `yoker` → chat                         | Mocked — NOT verified end-to-end |
| Empty argv → chat                            | NOT covered |
| `--help` → no chat (let parser show help)   | NOT covered — edge case lost |
| `-h` → no chat                               | NOT covered — edge case lost |
| `--flag X` → chat (backward compat)          | NOT covered end-to-end |
| Known subcommand → direct routing            | Covered via `TestMainDispatch` (mocked) |
| Unknown positional → no insert (argparse error) | NOT covered |
| Flag after subcommand → no insert            | NOT covered |
| Dash flag after unknown → no insert          | NOT covered |

The `--help` and unknown-subcommand edge cases were explicitly tested in the old
suite because they were known gotchas of the default-subcommand logic. With
`default_cmd=True`, these behaviors are now Clevis's responsibility, but a
regression test would catch if Clevis changes behavior.

### 4. `_read_dependencies` in inspect.py not explicitly tested (Risk 4)

**Location:** `src/yoker/cli/inspect.py` lines 176-196

The `_read_dependencies` function uses `clevis.load` to parse `pyproject.toml`
and extract dependencies. The inspect tests run through `_print_report` which
calls `_read_dependencies`, but:
- No test creates a `pyproject.toml` in the test fixture
- No test asserts on the "Dependencies:" output line
- The `clevis.load` usage (chosen for env-var interpolation consistency) is
  never verified

**What should be tested:** A folder inspect test with a `pyproject.toml`
containing `[project] dependencies = ["foo>=1.0"]` should assert that "foo"
appears in the output.

## Test Quality Assessment

### Positive Observations

- `get_yoker_config_with_manifest()` has excellent coverage (8 tests, 95% line
  coverage) — the cascade, CLI precedence, malformed TOML, and all section types
  are tested through the public API (behavior, not implementation).
- `load_file_manifest()` has strong coverage (15 tests, 91%) — parsing, partial
  sections, type validation, unknown keys, and the security-relevant "does not
  import tools_module" invariant are all tested.
- Trust gate ordering is well tested — the security invariant (load_source not
  called before check_source_allowed) is explicitly verified in both directions.
- `deep_merge` has 4 focused tests covering nested dicts, non-dict replacement,
  deep nesting, and list replacement.
- `parse_run_overrides` has 5 tests covering all extraction scenarios.
- `check_source_allowed` has 5 tests covering trusted config, session trust,
  interactive accept/reject, and env override.
- Test isolation is well handled — the `_isolate_clevis` fixture in
  `test_config_with_manifest.py` properly resets Clevis global state and
  restores subcommand configs.

### Quality Issues

- `TestMainDefaultChat.test_routes_to_chat_when_no_subcommand` — This test
  mocks `get_cmd` to return `"chat"` and then asserts `get_cmd` was called. It
  verifies that `main()` calls `get_cmd()` and dispatches, but NOT that
  `default_cmd=True` causes `get_cmd()` to return `"chat"`. The test name and
  docstring suggest it tests the default routing, but it actually tests the
  dispatch logic. This is misleading.

- The `TestMainDispatch` tests all mock `get_cmd` with `return_value=cmd_name`,
  which means they test that `main()` dispatches to the right handler for a given
  `get_cmd()` return value — useful but incomplete. They never verify that
  `get_cmd()` returns the expected value for a given `sys.argv`.

## Recommendations

### Must Fix (before approval)

1. **Add direct tests for `load_subcommand_config_with_manifest()`** — At
   minimum 4-5 tests covering: manifest override applied, CLI wins over
   manifest, subcommand section extraction, empty overrides no-op, and
   validation runs on merged config. These can use the same isolation pattern
   as `test_config_with_manifest.py` (reset Clevis, set HOME/cwd to tmp_path).

2. **Add at least one integration test for `default_cmd=True`** — Run `main()`
   with `sys.argv = ["yoker"]` and mock only `run_chat` (not `get_cmd`). Assert
   `run_chat` is called. This verifies the actual Clevis behavior end-to-end.

### Should Fix (recommended)

3. **Add edge case tests for `default_cmd`** — `--help` flag and unknown
   subcommand, matching the old `TestNeedsDefaultChat` coverage. These protect
   against regressions if Clevis changes `default_cmd` behavior.

4. **Add a `_read_dependencies` test** — Create a folder with a
   `pyproject.toml`, run inspect, and assert dependency names appear in output.

## Files Reviewed

- `tests/test_cli/test_dispatch.py`
- `tests/test_cli/test_run.py`
- `tests/test_config/test_config_with_manifest.py`
- `tests/test_plugins/test_file_manifest.py`
- `tests/test_cli/test_inspect.py`
- `src/yoker/cli/commands.py`
- `src/yoker/config/__init__.py`
- `src/yoker/cli/shared.py`
- `src/yoker/__main__.py`
- `src/yoker/plugins/file_manifest.py`
- `src/yoker/cli/inspect.py`
- `src/yoker/cli/run.py`