# API Analysis: Bootstrap Config Detection (Task 2.1)

**Date**: 2026-06-26
**Task**: MBI-002: Bootstrap, Task 2.1 — Detect Missing Configuration
**Reviewer**: API Architect Agent
**Related Documents**: `analysis/functional.md`, `TODO.md`, `PLAN.md`

## Summary

This analysis designs the API for detecting whether Yoker is configured
sufficiently to run, or whether the bootstrap wizard should be triggered.
The key challenge is that the existing config system (Clevis) always returns
a fully-populated `Config` object with defaults — it cannot distinguish a
conscious user choice from a defaulted value. Therefore, detection must
operate at the **file level** (does the TOML file exist and does it contain
the required keys), not at the `Config` object level.

## Findings

### Existing Config System

- **Config loader**: `yoker/config/__init__.py` exposes `get_yoker_config(cli: bool)`
  which delegates to `clevis.get_config(Config, name="yoker", ...)`.
- **Discovery**: Clevis loads from two locations:
  - User config: `~/.yoker.toml` (lower priority)
  - Project config: `./yoker.toml` (higher priority)
  - Merged with dataclass defaults (lowest priority).
- **Defaults are always present**: `Config()` with no file yields a valid object
  (`backend.ollama.model = "llama3.2:latest"`, `base_url = "http://localhost:11434"`).
  There is no sentinel/`None` marker distinguishing "set by user" from "default".
- **Entry point**: `__main__.py` constructs `Agent(parse_cli_args=True)`, which
  calls `get_yoker_config(cli=True)` internally. There is currently no pre-flight
  check before Agent construction.
- **Exceptions**: `yoker.exceptions` already provides `ConfigurationError`,
  `ValidationError`, and `FileNotFoundError` — these can be reused.

### Why File-Level Detection Is Required

Because every `Config` field has a default, the loaded `Config` object is
indistinguishable whether or not a TOML file existed. To detect "missing" vs
"incomplete" vs "complete" configuration, we must inspect the raw TOML files
directly, before the Clevis merge fills in defaults.

| Scenario | Config file exists? | Required keys present? | State |
|----------|--------------------|------------------------|-------|
| First-time user | No | n/a | `missing` |
| Partial config | Yes | No | `incomplete` |
| Ready to run | Yes | Yes | `complete` |

### Proposed Module Placement

A new `yoker/bootstrap/` package is recommended, because:

1. MBI-002 will grow to include the wizard, model selection, account guidance,
   and config creation — all related but distinct from the config system itself.
2. Keeping detection out of `yoker/config/` preserves the latter as a pure
   "load and validate" module, avoiding coupling Clevis internals with
   bootstrap logic.
3. The bootstrap module is a natural home for `is_bootstrapped()`, the wizard,
   and the config writer (task 2.5).

```
src/yoker/bootstrap/
  __init__.py      # Public API exports
  detect.py        # Config detection logic (this task)
  # Future: wizard.py, writer.py, ...
```

### Proposed API Design

#### 1. `ConfigStatus` dataclass

A frozen, immutable result describing the detection outcome. The wizard
consumes this to decide what to present; `__main__.py` consumes the
`needs_bootstrap` property to decide whether to launch the wizard.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ConfigState = Literal["missing", "incomplete", "complete"]


@dataclass(frozen=True)
class ConfigStatus:
  """Result of bootstrap configuration detection.

  Attributes:
    state: Whether config is 'missing', 'incomplete', or 'complete'.
    config_path: Path to the config file that was inspected, if any.
      When both user and project files exist, this is the higher-priority
      project file. None when no config file exists.
    missing_fields: Dotted paths of required fields absent from the TOML.
      Empty tuple when state is 'missing' or 'complete'.
    user_config_path: Resolved path to ~/.yoker.toml.
    project_config_path: Resolved path to ./yoker.toml.
  """

  state: ConfigState
  config_path: Path | None
  missing_fields: tuple[str, ...]
  user_config_path: Path
  project_config_path: Path

  @property
  def needs_bootstrap(self) -> bool:
    """True when the bootstrap wizard should be triggered."""
    return self.state != "complete"
```

#### 2. `detect_config()` function

The primary entry point. It performs **file-level** inspection (does not
construct a `Config` object, does not invoke Clevis). This keeps it cheap,
side-effect-free, and independent of CLI argument parsing.

```python
def detect_config(
  *,
  user_config_path: Path | None = None,
  project_config_path: Path | None = None,
) -> ConfigStatus:
  """Detect whether Yoker is sufficiently configured.

  Checks for the existence of yoker.toml config files (user and project
  level) and validates that minimal required configuration is present in
  the raw TOML. Does not load or construct a Config object.

  Args:
    user_config_path: Override user config path (default ~/.yoker.toml).
      Used for testing.
    project_config_path: Override project config path (default ./yoker.toml).
      Used for testing.

  Returns:
    ConfigStatus describing the detection result.
  """
```

#### 3. Required-fields constant

The set of fields considered "minimal required" is centralized so the wizard
(task 2.2+) and the detector agree:

```python
# Required dotted TOML paths that must be present for a 'complete' config.
REQUIRED_CONFIG_FIELDS: tuple[str, ...] = (
  "backend.ollama.model",
)
```

Rationale: `backend.ollama.base_url` has a robust default
(`http://localhost:11434`) suitable for local Ollama. The truly decisive
user choice is the **model**. The wizard (task 2.3) will set both, but
detection only requires the model key to be present — its presence implies
the user has engaged with the config at least once. This constant can be
extended later without changing the API.

#### 4. Helper functions (private or exported for testing)

```python
def _default_config_paths() -> tuple[Path, Path]:
  """Return (user_config_path, project_config_path) using Clevis conventions.

  User: ~/.yoker.toml  (Path.home() / ".yoker.toml")
  Project: ./yoker.toml (Path.cwd() / "yoker.toml")
  """


def _check_required_fields(
  toml_data: dict, required: tuple[str, ...]
) -> tuple[str, ...]:
  """Return dotted paths from `required` that are absent in `toml_data`.

  Traverses nested dicts by splitting on '.'. A field is 'present' if the
  full path resolves to a non-None value in the parsed TOML.
  """
```

### Integration with Existing Config Discovery

```
                         __main__.py (modified)
                              |
                              v
                +--> detect_config() --> ConfigStatus
                |                  |
                |     needs_bootstrap? |
                |          |           |
                |         yes          no
                |          |           |
                |          v           v
                |    BootstrapWizard   Agent(get_yoker_config(cli=True))
                |    (tasks 2.2-2.5)         |
                |          |                v
                |    writes yoker.toml   normal session
                |          |
                +----------+ (restart or re-detect)
```

**Call site**: In `__main__.py::main()`, before constructing `Agent`, call
`detect_config()`. If `status.needs_bootstrap`, run the wizard (not yet
implemented — for task 2.1, this branch logs and exits, or proceeds with
defaults). After the wizard writes `yoker.toml`, detection can be re-run or
the Agent constructed directly.

The detection does **not** replace or wrap `get_yoker_config()`. It is a
purely additive pre-flight check. The Agent's existing config-loading path
remains untouched, preserving library-mode usage where callers construct
`Agent(config=...)` directly and bypass bootstrap entirely.

### Edge Cases and Error Handling

| Case | Handling |
|------|----------|
| No config file exists | `state="missing"`, `config_path=None`, `missing_fields=()` |
| User config exists, project does not | Inspect user config path |
| Both exist | Inspect project config (higher priority per Clevis) |
| Config file exists but is empty TOML | `state="incomplete"`, `missing_fields` lists all required |
| Config file has `[backend]` but no `model` | `state="incomplete"`, `missing_fields=("backend.ollama.model",)` |
| Malformed TOML (syntax error) | Raise `ConfigurationError` with path and parse error detail. The wizard can catch this and offer to recreate. |
| Permission denied reading config file | Raise `ConfigurationError`. Do not silently treat as missing — the user may have intentionally restricted access. |
| Symlink to nonexistent target | Treat as missing (file does not resolve). |
| `~` in path | Expand via `Path.expanduser()`. |
| Environment variable for config dir | Out of scope for 2.1; Clevis paths are fixed. Could be added later via override args. |

Malformed TOML is intentionally an **error**, not silently "incomplete",
because the wizard cannot safely merge into a corrupt file. The user should
be informed and offered a fresh-config path.

### Security Considerations

1. **Path traversal**: Config paths are derived from `Path.home()` and
   `Path.cwd()`, never from user input in the detector. Override args are for
   tests only and are not exposed via CLI.
2. **Home directory access**: `Path.home()` respects `$HOME` on Unix and
   `%USERPROFILE%` on Windows. No credential reading occurs — only the
   config TOML is opened with default permissions.
3. **Symlink following**: `Path.exists()` follows symlinks by default. A
   symlink pointing outside the home directory is acceptable here since the
   user created it deliberately; the file content (not its location) is what
   matters.
4. **No secret exposure**: The detector reads the TOML but only checks for
   key presence; it does not log values. Missing-field lists contain field
   **names** only, never values.
5. **File permissions**: The detector opens files in read mode only. It does
   not create or modify files (that is task 2.5). Clevis's `SecurityConfig`
   is not invoked here because we bypass Clevis entirely.

### Unit Test Plan Outline

Tests live in `tests/test_bootstrap/test_detect_config.py`.

1. **No config file present**
   - `detect_config(user_config_path=tmp/A, project_config_path=tmp/B)`
     returns `state="missing"`, `config_path=None`.
2. **User config present, complete**
   - Write `~/.yoker.toml` with `[backend.ollama]` + `model = "x"`.
   - Assert `state="complete"`, `needs_bootstrap=False`.
3. **Project config takes precedence**
   - Both files present, project has model, user does not.
   - Assert `config_path == project path`, `state="complete"`.
4. **Incomplete: empty TOML file**
   - Write empty `yoker.toml`.
   - Assert `state="incomplete"`, `missing_fields` non-empty.
5. **Incomplete: `[backend]` present, no model**
   - Assert `missing_fields == ("backend.ollama.model",)`.
6. **Malformed TOML raises `ConfigurationError`**
   - Write `yoker.toml` with `= invalid`.
   - Assert `ConfigurationError` raised, message includes path.
7. **Permission-denied raises `ConfigurationError`**
   - Create unreadable file (chmod 000).
   - Assert error raised (not silent missing).
8. **Override paths respected**
   - Pass custom `user_config_path` / `project_config_path`.
9. **`~` expansion**
   - `user_config_path=Path("~/x.toml")` is expanded correctly.
10. **Symlink to nonexistent target treated as missing**
    - Create dangling symlink; assert `state="missing"`.

### Exports

```python
# src/yoker/bootstrap/__init__.py
from yoker.bootstrap.detect import ConfigStatus, ConfigState, detect_config

__all__ = ["ConfigStatus", "ConfigState", "detect_config"]
```

`detect_config` is the only function the entry point needs. `ConfigStatus`
is exported for type annotations in the wizard (task 2.2).

## Action Items

- [ ] Create `src/yoker/bootstrap/` package with `__init__.py` and `detect.py`.
- [ ] Implement `ConfigStatus` dataclass and `detect_config()` function.
- [ ] Implement private `_default_config_paths()` and `_check_required_fields()`.
- [ ] Add `REQUIRED_CONFIG_FIELDS` constant (start with `backend.ollama.model`).
- [ ] Wire `detect_config()` into `__main__.py::main()` as a pre-flight check
      (initially log-only when `needs_bootstrap`; full wizard wiring in 2.2).
- [ ] Write unit tests in `tests/test_bootstrap/test_detect_config.py`.
- [ ] Update `TODO.md` task 2.1 noting the file-level detection approach and
      the new `yoker/bootstrap/` module.
- [ ] Future (task 2.2+): implement `BootstrapWizard` consuming `ConfigStatus`;
      future (task 2.5): implement config writer in `yoker/bootstrap/writer.py`.

## Open Questions for the User

1. **Required fields**: Is `backend.ollama.model` alone sufficient as the
   "minimal required" check, or should `backend.ollama.base_url` also be
   required? My recommendation is model-only (base_url has a good default),
   but the acceptance criteria mention "(backend, model)" which could imply
   both the `[backend]` section and the model field.

2. **Behavior on detection in CLI mode**: When `detect_config()` returns
   `needs_bootstrap=True` in task 2.1 (before the wizard exists in 2.2),
   should `__main__.py` (a) exit with a message, (b) proceed with defaults,
   or (c) print a warning and proceed? I recommend (c) for now, switching to
   wizard-launch in 2.2.

3. **Library mode**: Should `Agent(config=...)` (explicit config) skip
   bootstrap detection entirely? My recommendation is yes — detection is a
   CLI/entry-point concern, not a library concern. Callers providing explicit
   config have opted out of bootstrap.