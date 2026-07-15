# API Architect Review: Clevis 0.7.0 Upgrade

**Date**: 2026-07-15
**Reviewer**: API Architect Agent
**Task**: Review Clevis 0.7.0 upgrade changes on `feature/mbi-004-yoker-commands`
**Branch**: `feature/mbi-004-yoker-commands`

## Summary

The upgrade replaces Clevis internal API workarounds with native Clevis 0.7.0
public API across four files. The migration is architecturally sound: all
imports come from Clevis's public `__all__`, the cascade API is used
correctly, and the `default_cmd=True` replacement for sys.argv patching is
clean and idiomatic. One redundant abstraction (a local `deep_merge`) should
be cleaned up. The two-function split for manifest config loading is
justified by a real ordering constraint in Clevis's subcommand section
extraction.

## Files Reviewed

- `src/yoker/config/__init__.py` — `get_yoker_config_with_manifest()`
- `src/yoker/cli/shared.py` — `load_subcommand_config_with_manifest()`
- `src/yoker/cli/commands.py` — `default_cmd=True` on `ChatConfig`
- `src/yoker/__main__.py` — cleanup of sys.argv patching
- `src/yoker/plugins/file_manifest.py` — `clevis.load` usage
- `src/yoker/cli/inspect.py` — `clevis.load` usage
- `src/yoker/cli/run.py` — caller of both manifest config functions

## Verification of Clevis 0.7.0 Public API

Confirmed against the installed `clevis==0.7.0` in
`.venv/lib/python3.11/site-packages/clevis/__init__.py` that every imported
symbol is in `__all__`:

| Symbol | Used In | In `__all__` |
|--------|---------|--------------|
| `build_default_cascade` | `config/__init__.py` | Yes |
| `get_config` (with `cascade=`) | `config/__init__.py`, `cli/shared.py` | Yes |
| `load` | `file_manifest.py`, `inspect.py` | Yes |
| `deep_merge` | `cli/shared.py` | Yes |
| `load_toml_from_fd` | `cli/shared.py` | Yes |
| `check_file_permissions` | `cli/shared.py` | Yes |
| `check_directory_permissions` | `cli/shared.py` | Yes |
| `configclass` (`default_cmd=True`) | `cli/commands.py` | Yes |
| `get_factory` | `cli/shared.py` | Yes |
| `apply_to_dict` | `cli/shared.py` | Yes |
| `get_cmd` | `__main__.py` | Yes |
| `SecurityAction`, `SecurityConfig` | `config/__init__.py`, `cli/shared.py` | Yes |

No private Clevis imports (`_load_toml`, `_load_toml_from_fd` as private,
etc.) remain in the source tree. The old `TODO(clevis-feature-request)`
comments and associated `type: ignore[attr-defined]` annotations for Clevis
internals are gone.

## Findings

### Strengths

**S1: `default_cmd=True` cleanly replaces sys.argv patching.**
`commands.py` line 26 uses `@configclass(cmd="chat", default_cmd=True, ...)`
on `ChatConfig`. `__main__.py` no longer patches `sys.argv` to insert
`chat` — it simply calls `get_cmd()` and dispatches. The `default_cmd`
parameter is validated by Clevis (raises `ValueError` if set without `cmd`,
and enforces only one default per parser). This is the idiomatic Clevis 0.7.0
approach.

**S2: `get_yoker_config_with_manifest()` correctly uses the cascade API.**
`config/__init__.py` lines 795-809:
```python
cascade = build_default_cascade("yoker", security)
...
cascade = cascade + [lambda: overrides]
config = get_config(Config, name="yoker", cascade=cascade, cli=cli)
```
This follows the exact pattern from Clevis's `DEFAULT_CASCADE` docstring
(append a zero-arg callable returning a dict). The `security` parameter is
passed to `build_default_cascade` (which bakes it into the user/project
providers) and correctly NOT passed to `get_config` (which would log a
warning since `cascade=` owns security). The lambda closure captures
`overrides` safely — it's consumed immediately within the same call to
`get_config`, no late-binding loop concern.

**S3: `load_subcommand_config_with_manifest()` justifies NOT using the cascade API.**
The developer's justification is verified correct. Clevis's `get_config`
applies the middle cascade (deep-merge) BEFORE subcommand section
extraction (`[run]`/`[loop]` etc.). Section extraction **clears `cfg`** and
replaces it with only the `[run]` section content, which would **lose**
manifest overrides that target root-level Config fields like
`[backend.ollama]`. The manual replication in `shared.py` applies manifest
overrides AFTER section extraction, preserving them. This is a real
Clevis ordering constraint, not a workaround for a missing feature.

**S4: Security invariant preserved.**
`run.py` loads `RunConfig` WITHOUT manifest overrides for the trust gate
(line 67), then reloads WITH manifest overrides only after the source passes
the trust gate (line 108). A source cannot influence its own trust decision.

**S5: `clevis.load` used for raw TOML parsing.**
`file_manifest.py` line 137 and `inspect.py` line 186 use `clevis.load` —
the public raw TOML parser (no security checks, matching `tomllib.load`
signature). This is correct: `file_manifest.py` reads a source's
`agent.toml` (not a user/project config file, so no TOCTOU security check
needed there); `inspect.py` reads `pyproject.toml` for read-only reporting.

### Issues Found

**I1: Redundant local `deep_merge` in `shared.py` (Medium-Low).**
`shared.py` lines 144-156 define a module-level `deep_merge(target, overrides)`
with **in-place mutation** semantics (returns `None`, mutates `target`).
However, `load_subcommand_config_with_manifest` (the only production caller
in this module) imports `deep_merge` from `clevis` at line 87, which
**shadows** the local definition within that function's scope. The local
`deep_merge` is therefore **dead in production** — not called by any
production code path.

The two functions have **different semantics**, which is a confusion risk:
- `clevis.deep_merge(base, overlay)` → returns a new dict, does not mutate
  inputs (used in `load_subcommand_config_with_manifest` line 135:
  `cfg = deep_merge(cfg, manifest_overrides)`)
- `yoker.cli.shared.deep_merge(target, overrides)` → mutates `target`
  in place, returns `None` (tested in `tests/test_cli/test_run.py`
  `TestDeepMerge`, still exported from `yoker.cli.__init__`)

**Recommendation**: Remove the local `deep_merge` from `shared.py`, drop it
from `shared.py`'s `__all__` and `yoker.cli.__init__`'s imports/`__all__`,
and update or remove the `TestDeepMerge` test class in `tests/test_cli/test_run.py`.
If the merge behavior needs testing, test `clevis.deep_merge` directly.
**Location**: `src/yoker/cli/shared.py:144-156`, `src/yoker/cli/__init__.py:20,40`,
`tests/test_cli/test_run.py:388-424`.

**I2: `apply_to_dict` vs `_merge_list_args` — known list-merge limitation (Low).**
`load_subcommand_config_with_manifest` uses `apply_to_dict(factory.get_args(), cfg)`
(line 138) for CLI arg merging, while Clevis's `get_config` uses the private
`_merge_list_args` which handles list fields specially (append to TOML base,
`--no-field` clears). Since `_merge_list_args` is private (not in `__all__`),
using `apply_to_dict` (public) is the correct choice to stay on public API.
This means list-typed fields like `agents.directories` or
`permissions.filesystem_paths` get replace semantics instead of append
semantics when set via CLI under `yoker run`/`yoker loop`.

This is not a regression (the pre-upgrade code also used `apply_to_dict`),
and these fields are rarely set via CLI for `run`/`loop` subcommands. But it
should be documented as a known limitation.

**Recommendation**: Add a one-line note to the `load_subcommand_config_with_manifest`
docstring mentioning that list fields use replace (not append) semantics,
unlike `get_config`'s append behavior. No code change needed.
**Location**: `src/yoker/cli/shared.py:138`.

**I3: Two manifest-config functions could confuse maintainers (Low).**
`get_yoker_config_with_manifest` (cascade API, for base `Config`) and
`load_subcommand_config_with_manifest` (manual replication, for subcommand
configs) use different approaches for the same conceptual task. The
justification is sound (section extraction ordering), but a future maintainer
might wonder why two patterns exist. `load_subcommand_config_with_manifest`
already has a thorough docstring explaining the ordering issue.
`get_yoker_config_with_manifest` could briefly note why the cascade API is
sufficient for its case (base `Config` has no `cmd`, so no section extraction
occurs).

**Recommendation**: Add a brief note to `get_yoker_config_with_manifest`'s
docstring explaining that it uses the cascade API because `Config` has no
`cmd` attribute (no subcommand section extraction), unlike
`load_subcommand_config_with_manifest` which handles subcommand configs.
**Location**: `src/yoker/config/__init__.py:747-810`.

### Compliance Check

- **Public API usage**: All Clevis imports are from `__all__`. No private
  internals used. PASS.
- **No unnecessary abstractions**: The manual replication in
  `load_subcommand_config_with_manifest` is necessary (not gratuitous) due
  to Clevis's section-extraction ordering. The one exception is the redundant
  local `deep_merge` (I1). PARTIAL.
- **Backward compatibility**: `get_yoker_config()` unchanged.
  `get_yoker_config_with_manifest()` uses cascade API but produces the same
  cascade order (user → project → manifest → CLI). Deep-merge behavior is
  Clevis 0.7.0's default (a Clevis change, not a Yoker change).
  `load_subcommand_config_with_manifest` preserves pre-upgrade behavior
  (including the `apply_to_dict` list-replace semantics). PASS.
- **Cleanup completeness**: `__main__.py` no longer patches sys.argv. No
  `TODO(clevis-feature-request)` comments remain. No Clevis-internal
  `type: ignore[attr-defined]` annotations remain. PASS.

## Recommendations (Prioritized)

1. **Remove redundant local `deep_merge`** from `shared.py` and its exports
   (I1). Update `TestDeepMerge` tests accordingly.
2. **Add docstring note** to `get_yoker_config_with_manifest` explaining why
   the cascade API is sufficient for base `Config` (I3).
3. **Add docstring note** to `load_subcommand_config_with_manifest` about
   list-field replace semantics (I2).

## Conclusion

**Approved.** The architecture is sound. The Clevis 0.7.0 public API is used
correctly and idiomatically. The two-function split for manifest config
loading is justified by a real ordering constraint. The one cleanup item
(redundant `deep_merge`) is non-blocking and can be addressed in a follow-up
commit.

## Next Steps

1. Address I1 (remove redundant `deep_merge`) — small, self-contained change.
2. Address I2 and I3 (docstring notes) — trivial, can be bundled with I1.
3. No further architectural changes needed.