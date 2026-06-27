# API Analysis: Bootstrap Config Detection (Task 2.1)

**Date**: 2026-06-26 (revised 2026-06-27 per PR #34 owner feedback)
**Task**: MBI-002: Bootstrap, Task 2.1 — Detect Missing Configuration
**Reviewer**: API Architect Agent
**Related Documents**: `analysis/functional.md`, `TODO.md`, `PLAN.md`,
`analysis/bootstrap-wizard-design.md`

## Summary

This analysis designs the API for detecting whether Yoker is configured,
so the bootstrap wizard can be triggered when it is not. Per the repository
owner's feedback on PR #34, detection is intentionally **minimal**: a single
boolean function, `config_provided() -> bool`, that returns `True` when the
user has supplied configuration via any user-induced source, and `False`
otherwise. There is no `ConfigStatus` dataclass, no `missing/incomplete/
complete` state machine, no `REQUIRED_CONFIG_FIELDS` constant, and no
`needs_bootstrap` property. The trigger is simply:

```python
if not config_provided():
    run_wizard()  # interactive mode
```

The earlier, more elaborate design (ConfigStatus + detect_config() + state
machine) was over-engineering. It is fully superseded by this document.

## Findings

### Existing Config System

- **Config loader**: `yoker/config/__init__.py` exposes `get_yoker_config(cli: bool)`
  which delegates to `clevis.get_config(Config, name="yoker", ...)`.
- **Discovery**: Clevis loads from two locations:
  - User config: `~/.yoker.toml` (lower priority)
  - Project config: `./yoker.toml` (higher priority)
  - Merged with dataclass defaults (lowest priority).
- **Defaults are always present**: `Config()` with no file yields a valid object
  (`backend.ollama.model`, `base_url = "http://localhost:11434"`, etc.). There
  is no sentinel/`None` marker distinguishing "set by user" from "default".
- **Entry point**: `__main__.py` constructs `Agent(parse_cli_args=True)`, which
  calls `get_yoker_config(cli=True)` internally. There is currently no pre-flight
  check before Agent construction.
- **Exceptions**: `yoker.exceptions` already provides `ConfigurationError`,
  `ValidationError`, and `FileNotFoundError` — reusable if needed.

### What "Provided" Means

A configuration is **provided** when the user has induced any configuration
source. The boolean check is true if **any** of the following hold:

1. A **user-level config file** exists at `~/.yoker.toml` (i.e.
   `Path.home() / ".yoker.toml"` resolves to an existing file), OR
2. A **project-level config file** exists at `./yoker.toml` (i.e.
   `Path.cwd() / "yoker.toml"` resolves to an existing file), OR
3. The user has supplied **CLI arguments** that override defaults (i.e. Clevis
   was invoked with `cli=True` and the parse produced at least one non-default
   value).

We do **not** inspect the *contents* of the files for required keys, and we do
**not** distinguish "complete" from "incomplete". If the user has authored a
yoker.toml — even a sparse one — that is a conscious configuration act and the
wizard is not triggered. If the user has passed CLI args, that too is a
conscious configuration act. Clevis's default-filling behavior is ignored for
the boolean decision: we are not checking whether the loaded `Config` differs
from defaults (that path is what the old design tried and is exactly what we are
avoiding); we are checking whether the user *did* something config-related.

**Rationale (owner, PR #34)**: the previous state-machine design distinguished
"missing" / "incomplete" / "complete" by parsing raw TOML and checking for
required fields. This was over-engineering. Any user-induced configuration
source implies the user has engaged with config; the wizard's job is only to
catch the *no-config-at-all* first-run case. A user with a sparse but
hand-authored file does not need the wizard; they need the docs.

### File-Level Inspection (Boolean Only)

Because every `Config` field has a default, the loaded `Config` object is
indistinguishable whether or not a TOML file existed. Detection therefore
inspects the **file system** (does the TOML file exist?) and the **CLI parse**
(were any overrides supplied?), not the `Config` object. This is the minimum
file-level inspection needed to answer the boolean — no field-presence
traversal, no `REQUIRED_CONFIG_FIELDS`.

### CLI Argument Detection — Note

Detecting "did the user pass CLI overrides?" requires care: Clevis fills
defaults for every field, so we cannot simply compare the parsed `Config` to a
default `Config` (frozen dataclasses with mutable nested defaults make
field-wise equality fragile). The implementation should instead inspect the
raw CLI parse, before Clevis merges defaults — e.g. by checking whether
`sys.argv` contains any `--backend-*`, `--tools-*`, `--ui-*`, etc. flags, or by
asking Clevis for the set of explicitly-set keys if its API exposes one. This
detail is left to the implementation; the contract here is only the boolean
return. If CLI-override detection proves brittle in practice, the minimum
viable behavior is to treat `cli=True` with any yoker-related flag as
"provided".

## Proposed Module Placement

A new `yoker/bootstrap/` package holds the wizard-side code. The detection
function lives here too, because it exists to serve the bootstrap decision:

```
src/yoker/bootstrap/
  __init__.py      # Public API exports
  detect.py        # config_provided() (this task)
  # Future: wizard.py, steps.py, modellist.py (tasks 2.2-2.5)
```

The **ConfigWriter** does **not** live here — it moves to the config module
(see `analysis/bootstrap-wizard-design.md` task 2.5). The bootstrap package
calls it; it does not own it.

## Proposed API Design

### `config_provided()` — the entire public API

```python
def config_provided(
  *,
  user_config_path: Path | None = None,
  project_config_path: Path | None = None,
  cli_args: Sequence[str] | None = None,
) -> bool:
  """Return True if the user has supplied any yoker configuration.

  "Provided" means the user has induced configuration via at least one of:
    - a user-level ~/.yoker.toml file,
    - a project-level ./yoker.toml file,
    - CLI arguments overriding defaults.

  Returns False when none of these are present — i.e. the first-run,
  no-config case that should trigger the bootstrap wizard.

  Args:
    user_config_path: Override user config path (default ~/.yoker.toml).
      Used for testing.
    project_config_path: Override project config path (default ./yoker.toml).
      Used for testing.
    cli_args: Override the CLI argument list (default sys.argv[1:]).
      Used for testing.

  Returns:
    True if any user-induced configuration source is present; False otherwise.
  """
```

That is the whole API. No dataclass, no enum, no constant, no helper exports.

### Private helpers (not exported)

```python
def _default_config_paths() -> tuple[Path, Path]:
  """Return (user_config_path, project_config_path) using Clevis conventions.

  User: ~/.yoker.toml  (Path.home() / ".yoker.toml")
  Project: ./yoker.toml (Path.cwd() / "yoker.toml")
  """

  def _cli_overrides_present(cli_args: Sequence[str]) -> bool:
  """Return True if any yoker-related CLI flag is present in cli_args.

  A yoker-related flag is any argument starting with a yoker-config prefix
  (e.g. '--backend-', '--tools-', '--ui-', '--context-', '--permissions-',
  '--agents-', '--skills-', '--plugins-', '--logging-', '--agent'). The
  exact prefix set should match the Config dataclass's CLI surface as
  generated by Clevis. Returns False for an empty or help-only argv.
  """
```

### What is NOT in the API

| Removed concept | Reason |
|-----------------|--------|
| `ConfigStatus` dataclass | Single boolean replaces it |
| `ConfigState` literal (`missing/incomplete/complete`) | No state machine |
| `detect_config() -> ConfigStatus` | Replaced by `config_provided() -> bool` |
| `REQUIRED_CONFIG_FIELDS` constant | No field-presence check |
| `needs_bootstrap` property | The boolean *is* the trigger |
| `missing_fields` tuple | No field-level reporting |
| `_check_required_fields()` helper | No field traversal |

## Integration with Existing Config Discovery

```
                         __main__.py (modified)
                              |
                              v
                +--> config_provided() --> bool
                |                       |
                |        provided?      |
                |          |            |
                |         no           yes
                |          |            |
                |          v            v
                |    BootstrapWizard   Agent(get_yoker_config(cli=True))
                |    (tasks 2.2-2.5)         |
                |          |                v
                |    writes yoker.toml   normal session
                |          |
                +----------+ (wizard returns; __main__ proceeds to Agent)
```

**Call site**: In `__main__.py::main()`, before constructing `Agent`, call
`config_provided()`. If `False`, run the wizard (interactive mode) or warn-and-
exit (non-interactive mode). After the wizard writes `~/.yoker.toml` and
returns, `__main__.py` proceeds straight into normal Agent startup using the
freshly-written config — the wizard does not exit the process.

The detection does **not** replace or wrap `get_yoker_config()`. It is a
purely additive pre-flight check. The Agent's existing config-loading path
remains untouched, preserving library-mode usage where callers construct
`Agent(config=...)` directly and bypass bootstrap entirely.

### Trigger wording

- Interactive mode: `if not config_provided(): await BootstrapWizard.run(ui)`
- Non-interactive mode: `if not config_provided(): warn_and_exit()`

There is no `ConfigStatus` object passed to the wizard. The wizard knows only
that it was invoked, which implies "no config was provided". It does not need
to know *why*.

## Edge Cases and Error Handling

| Case | Handling |
|------|----------|
| No config file exists, no CLI overrides | Returns `False` (wizard triggers) |
| `~/.yoker.toml` exists | Returns `True` (wizard does not trigger) |
| `./yoker.toml` exists | Returns `True` (wizard does not trigger) |
| Both files exist | Returns `True` |
| Empty TOML file exists (e.g. `touch ~/.yoker.toml`) | Returns `True` — the user created the file consciously; sparse is still "provided" |
| Malformed TOML (syntax error) | Raise `ConfigurationError` with path and parse error detail. The wizard can catch this and offer to recreate. Not silently treated as "not provided". |
| Permission denied reading config file | Raise `ConfigurationError`. Do not silently treat as missing — the user may have intentionally restricted access. |
| Symlink to nonexistent target | Treat as not existing (file does not resolve). |
| `~` in path | Expand via `Path.expanduser()`. |
| CLI args present with at least one yoker flag | Returns `True` |
| CLI args present but only `--help` / no yoker flags | Returns `False` (help is not configuration) |
| Environment variable for config dir | Out of scope; Clevis paths are fixed. Could be added later via override args. |

Malformed TOML is intentionally an **error**, not silently "not provided",
because the wizard cannot safely write into a corrupt file. The user should be
informed and offered a fresh-config path.

## Security Considerations

1. **Path traversal**: Config paths are derived from `Path.home()` and
   `Path.cwd()`, never from user input in the detector. Override args are for
   tests only and are not exposed via CLI.
2. **Home directory access**: `Path.home()` respects `$HOME` on Unix and
   `%USERPROFILE%` on Windows. No credential reading occurs — only the config
   TOML's *existence* is checked (and, in the error case, whether it parses).
3. **Symlink following**: `Path.exists()` follows symlinks by default. A
   symlink pointing outside the home directory is acceptable here since the
   user created it deliberately; the file content (not its location) is what
   matters.
4. **No secret exposure**: The detector checks for file existence and CLI
   flag presence only; it does not log file contents or flag values.
5. **File permissions**: The detector opens files in read mode only (and only
   to test parseability on the error path). It does not create or modify files
   (that is task 2.5). Clevis's `SecurityConfig` is not invoked here because we
   bypass Clevis entirely.

## Unit Test Plan Outline

Tests live in `tests/test_bootstrap/test_config_provided.py`. This is **logic**
(not IO), so unit tests are warranted per the owner's PR #34 guidance ("test
logic, don't test IO/interaction").

1. **No config file, no CLI args** → returns `False`.
2. **User config file exists** → returns `True`.
3. **Project config file exists** → returns `True`.
4. **Both files exist** → returns `True`.
5. **Empty TOML file exists** → returns `True` (sparse is still provided).
6. **CLI args with a yoker flag** → returns `True`.
7. **CLI args with only `--help`** → returns `False`.
8. **Malformed TOML** → raises `ConfigurationError` (not silent `False`).
9. **Permission-denied** → raises `ConfigurationError`.
10. **Override paths respected** — custom `user_config_path` / `project_config_path`.
11. **`~` expansion** — `user_config_path=Path("~/x.toml")` is expanded correctly.
12. **Dangling symlink** → treated as not existing → `False` (unless the other
    source is present).

## Exports

```python
# src/yoker/bootstrap/__init__.py
from yoker.bootstrap.detect import config_provided

__all__ = ["config_provided"]
```

`config_provided` is the only function the entry point needs. The wizard (task
2.2+) does not receive a status object; it is simply invoked when the boolean
is `False`.

## Action Items

- [ ] Create `src/yoker/bootstrap/` package with `__init__.py` and `detect.py`.
- [ ] Implement `config_provided() -> bool` and private `_default_config_paths()`,
      `_cli_overrides_present()`.
- [ ] Wire `config_provided()` into `__main__.py::main()` as a pre-flight check:
      `if not config_provided(): <wizard or warn-and-exit>`.
- [ ] Write unit tests in `tests/test_bootstrap/test_config_provided.py` (logic
      only — this is not IO).
- [ ] Update `TODO.md` task 2.1 to reflect the boolean API (no `ConfigStatus`).
- [ ] Future (task 2.2+): implement `BootstrapWizard` invoked when
      `config_provided()` is `False`; future (task 2.5): ConfigWriter lives in
      the config module, not in `yoker/bootstrap/`.

## Open Questions for the User

1. **CLI override detection mechanism**: Should we detect CLI overrides by
   inspecting `sys.argv` for yoker-config prefixes, or by asking Clevis for the
   set of explicitly-set keys (if its API exposes one)? Recommendation: start
   with `sys.argv` prefix matching; it is simple and robust for the boolean
   purpose. Refine if Clevis exposes a cleaner hook.

2. **Library mode**: Should `Agent(config=...)` (explicit config) skip
   bootstrap detection entirely? Recommendation: yes — detection is a CLI/
   entry-point concern, not a library concern. Callers providing explicit config
   have opted out of bootstrap. (This matches the previous design and the
   existing library-mode contract.)

## Revision History

- 2026-06-27: Replaced `ConfigStatus` / `detect_config()` / state-machine
  design with `config_provided() -> bool` per PR #34 owner feedback point 2.
  Removed `REQUIRED_CONFIG_FIELDS`, `ConfigState`, `missing_fields`,
  `needs_bootstrap`. Reduced unit-test plan to the boolean's logic.