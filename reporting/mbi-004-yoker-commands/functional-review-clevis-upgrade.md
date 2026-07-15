# Functional Review: Clevis 0.7.0 Upgrade

**Reviewer**: functional-analyst
**Branch**: `feature/mbi-004-yoker-commands`
**Date**: 2026-07-15
**Verdict**: approved

## Scope

This review covers the Clevis 0.7.0 upgrade changes that replace internal API
workarounds with native Clevis 0.7.0 functionality across six source files and
one test file, plus documentation updates to CLAUDE.md and DEVELOPMENT.md.

## Files Reviewed

- `src/yoker/cli/commands.py` — `default_cmd=True` on ChatConfig
- `src/yoker/__main__.py` — sys.argv patching removed; --with stripping retained
- `src/yoker/config/__init__.py` — `get_yoker_config_with_manifest()` rewrite
- `src/yoker/cli/shared.py` — `load_subcommand_config_with_manifest()` rewrite
- `src/yoker/plugins/file_manifest.py` — `_load_toml` -> `clevis.load`
- `src/yoker/cli/inspect.py` — `_load_toml` -> `clevis.load`
- `tests/test_cli/test_dispatch.py` — test updates
- `src/yoker/cli/run.py` — trust gate verification (unchanged, reviewed for regressions)
- `src/yoker/cli/chat.py` — bootstrap pre-flight verification (unchanged)

## Checklist Results

### 1. MBI-004 Acceptance Criteria Preserved

All user-facing behavior is unchanged. The upgrade swaps internal Clevis APIs
for public ones without altering any control flow, config cascade semantics, or
subcommand dispatch logic. All 1841 tests pass.

### 2. default_cmd=True Replaces sys.argv Patching

**Pass.** `commands.py` line 26 sets `default_cmd=True` on `ChatConfig`. The
`__main__.py` file no longer patches `sys.argv` to insert `chat`. Clevis
natively routes bare `yoker` to the `chat` subcommand. The module docstring
(lines 18-23) documents this behavior with examples.

The `__main__.py` dispatch loop (lines 50-69) calls `get_cmd()` and routes to
the appropriate handler. The fallback guard at line 67-69 catches any
unexpected `get_cmd()` result with `abort()`.

### 3. Cascade Ordering in get_yoker_config_with_manifest()

**Pass.** `config/__init__.py` lines 747-810 implement the cascade:

```
dataclass defaults
  -> user TOML (~/.yoker.toml)          [build_default_cascade]
  -> project TOML (./yoker.toml)       [build_default_cascade]
  -> manifest overrides (agent.toml)   [appended to cascade]
  -> CLI arguments (highest priority)  [get_config cli=True]
```

`build_default_cascade("yoker", security)` returns the user + project TOML
providers. The manifest overrides are appended as a lambda provider
(`cascade = cascade + [lambda: overrides]`). `get_config(Config, name="yoker",
cascade=cascade, cli=cli)` applies CLI args on top. The ordering is correct.

The old `type: ignore[attr-defined]` and `TODO(clevis-feature-request)`
comments are gone — the function uses only public Clevis 0.7.0 APIs.

### 4. Trust Gate Security Invariant

**Pass.** `cli/run.py` preserves the security invariant:
- Line 92: `check_source_allowed(resolved.trust_key, config, resolved)` — fires
  on the user's own config (not manifest-overridden), so sources cannot
  influence their own trust decision.
- Line 97: `load_source(resolved)` — called only AFTER the trust gate passes.
- Lines 106-111: manifest config overrides applied only AFTER trust gate
  passes and source is loaded.

The ordering is: resolve_source (phase 1) -> dry-run check -> trust gate ->
load_source (phase 2) -> manifest config reload -> agent/prompt resolution ->
prompt cap -> session. Correct.

### 5. --with Plugin Stripping and Bootstrap Pre-Flight

**Pass.** `__main__.py` retains `_parse_plugin_args()` (lines 72-95) which
extracts `--with` flags before `get_cmd()` is called. The plugin packages are
passed to `run_chat()` and `run_run()` handlers.

The bootstrap pre-flight check lives in `cli/chat.py` `run_chat()` (lines
45-71), not `__main__.py`. This is the correct location — bootstrap is
chat-specific. The CLAUDE.md text saying it "stays in `__main__.py`" is
slightly inaccurate, but the behavior is correct and unchanged.

### 6. No Regressions in CLI Dispatch

**Pass.** All 1841 tests pass, including the dispatch tests in
`tests/test_cli/test_dispatch.py`. The test file was updated to:
- Remove references to the deleted `_needs_default_chat()` helper
- Remove `KNOWN_COMMANDS` import
- Update `TestMainDefaultChat` to verify Clevis's `default_cmd=True` behavior
  (mocking `get_cmd` to return `"chat"` for bare `yoker`)
- Keep `--with` stripping tests intact

### 7. Edge Cases

- **No subcommand given**: Clevis `default_cmd=True` routes to `chat`.
  Verified by `test_routes_to_chat_when_no_subcommand`.
- **--help**: Handled by Clevis/argparse natively (not affected by upgrade).
- **Unknown commands**: argparse rejects unknown subcommands via
  `choices` validation before `get_cmd()` returns. The guard at
  `__main__.py` line 67-69 provides defense-in-depth.
- **No manifest / manifest_path is None**: `get_yoker_config_with_manifest`
  falls back to the default cascade (user + project TOML only) with empty
  run/plugin configs. Correct.
- **Manifest file does not exist**: `load_file_manifest` returns `None`,
  cascade stays at default. Correct.

## Observations (Non-Blocking)

### O1: Dual deep_merge Functions

There are two `deep_merge` functions with different semantics:
- `clevis.deep_merge(base, overlay) -> dict` — returns a new merged dict
- `yoker.cli.shared.deep_merge(target, overrides) -> None` — modifies in place

Inside `load_subcommand_config_with_manifest()`, the local import
(`from clevis import deep_merge` at line 88) shadows the module-level function.
Line 135 (`cfg = deep_merge(cfg, manifest_overrides)`) correctly uses clevis's
version, which returns a new dict. No bug, but the naming collision is a
potential source of confusion for future maintainers. Consider renaming the
module-level utility (e.g., `merge_in_place`) or removing it if tests can use
`clevis.deep_merge` directly.

### O2: load_subcommand_config_with_manifest Manual Cascade

`load_subcommand_config_with_manifest()` still manually reimplements the
cascade logic (TOML loading, security checks, subcommand section extraction,
manifest merge, CLI application) rather than using `build_default_cascade` +
`get_config(cascade=...)` like `get_yoker_config_with_manifest()` does. This
is intentional: the manifest overrides must be applied AFTER subcommand section
extraction (e.g., `[run]`) but BEFORE CLI args, and the manual approach makes
this ordering explicit. A future simplification could explore whether
`get_config(cascade=...)` handles section extraction at the right point in the
cascade, but the current approach is correct and well-documented.

### O3: CLAUDE.md Bootstrap Location Text

CLAUDE.md line 212 states "the bootstrap pre-flight check stay in
`__main__.py`" but the bootstrap code is in `cli/chat.py`. This is a
documentation inaccuracy, not a code issue. The bootstrap is chat-specific and
belongs in the chat handler.

## Test Results

```
1841 passed, 15 warnings in 23.31s
```

All tests pass, including:
- `tests/test_cli/test_dispatch.py` — dispatch and default-subcommand tests
- `tests/test_cli/test_run.py` — run handler and deep_merge utility tests
- Full test suite across all modules

## Conclusion

The Clevis 0.7.0 upgrade is clean and correct. All internal API workarounds
have been replaced with public Clevis 0.7.0 APIs. The `default_cmd=True`
approach is simpler and more maintainable than the previous `sys.argv`
patching. The config cascade ordering is preserved. The trust gate security
invariant is intact. No regressions detected.

**Verdict: approved**