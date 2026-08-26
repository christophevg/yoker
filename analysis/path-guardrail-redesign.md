# Path Guardrail Redesign — Design & Implementation Handoff

## Problem Statement

The current PathGuardrail has two classes of bugs:

### Bug 1: Dotfile extension matching
`allowed_extensions` entries like `.gitignore` never match because Python's
`Path.suffix` returns `''` for dotfiles. The code treated entries starting with
`.` as extensions, but `.gitignore` is a filename, not an extension.

### Bug 2: Inconsistent access control across tools
The guardrail applies different checks per tool based on `tool_name` string
matching:
- `allowed_extensions` only checked for `read` → `search` bypasses it
- `blocked_extensions` only checked for `write`/`update` → `file` delete bypasses
- `protected_files` checked for `write`/`update`/`file` but not `git`
- `blocked_patterns` (regex) checked globally but patterns are overly broad
  (e.g. `\.git` matches `.gitignore` as a substring)

**Real-world exploits observed:**
1. Agent couldn't `read` a `.svg` file → used `search` to read its content
2. Agent couldn't `read` `.gitignore` → used `git diff` to see it, then `file
   delete` to delete it, then `write` to recreate it

## Root Cause

The single `Path` annotation declares "this is a filesystem path" but doesn't
declare the access mode (read vs write). The guardrail then guesses based on
tool name, leading to inconsistent enforcement. Access control settings are
scattered across `ReadToolConfig`, `WriteToolConfig`, and
`PermissionsConfig` with three different pattern-matching mechanisms (regex,
extension strings, fnmatch globs).

## New Design

### Three-layer access control

All filesystem access is governed by three layers, checked in order:

1. **`filesystem_paths`** (HARD) — spatial boundary: which roots are accessible
2. **`blocked_paths`** (HARD) — universal denylist: what's blocked within those roots
3. **`blocked_write_paths`** (SOFT) — write-only denylist: additional blocks for write operations

### Config: `PermissionsConfig`

```python
@dataclass
class PermissionsConfig:
  # Spatial boundary — HARD, no override.
  # Directories grant tree access; individual files grant single-file access.
  # ~ is expanded to the user's home directory.
  filesystem_paths: tuple[str, ...] = (".",)

  # Universal denylist — HARD, no override.
  # Glob patterns matched (case-insensitive) against the relative path from
  # each containing allowed root. Full glob: *, **, ?, [...].
  # Matching a directory blocks it and everything beneath it.
  # Also enforced internally by search/list for every file they traverse.
  blocked_paths: tuple[str, ...] = (
    ".git",
    ".venv",
    "context",
    "local",
  )

  # Write-only denylist — SOFT (user can approve interactively; HARD in batch mode).
  # Same glob semantics as blocked_paths.
  blocked_write_paths: tuple[str, ...] = (
    "Makefile",
    "makefile",
    "GNUmakefile",
    "Justfile",
    "justfile",
    "Taskfile.yml",
    "pyproject.toml",
    "tox.ini",
    "setup.py",
    "setup.cfg",
    "yoker.toml",
    ".git/config",
    ".git/hooks/*",
    ".github/workflows/*.yml",
    "uv.lock",
    "poetry.lock",
  )

  # Network (unchanged from current design)
  network_access: str = "none"
  handlers: dict[str, HandlerConfig] = field(default_factory=dict)
```

### Annotations: `ReadPath` and `WritePath`

Replace the single `Path` annotation with two annotations that declare the
access mode at the parameter level:

```python
@dataclass(frozen=True)
class ReadPath(Text):
  """Marker for filesystem path parameters used in read-only fashion."""
  yoker_type: GuardType = GuardType.PATH_READ

@dataclass(frozen=True)
class WritePath(Text):
  """Marker for filesystem path parameters used in write fashion."""
  yoker_type: GuardType = GuardType.PATH_WRITE
```

`GuardType` enum gains two new members:
```python
class GuardType(str, Enum):
  PATH_READ = "path_read"
  PATH_WRITE = "path_write"
  URL = "url"
  QUERY = "query"
  TEXT = "text"
```

### Tool annotation mapping

| Tool | Param | Annotation | Reasoning |
|---|---|---|---|
| `read` | `path` | `ReadPath` | Purely reads file content |
| `search` | `path` | `ReadPath` | Reads file contents to match patterns |
| `list` | `path` | `ReadPath` | Reads directory metadata |
| `existence` | `path` | `ReadPath` | Checks path existence (stat) |
| `make` | `cwd` | `WritePath` | make targets can write/modify/delete files; agent can't control which files make touches (same reasoning as git) |
| `git` | `path` | `WritePath` | Shared across read ops (diff, log, show) and write ops (pull, checkout, rm); write is the dangerous case |
| `make` | `cwd` | `WritePath` | make targets can write/modify/delete files; agent can't control which files make touches (same reasoning as git) |
| `write` | `path` | `WritePath` | Creates/overwrites files |
| `update` | `path` | `WritePath` | Modifies existing files |
| `mkdir` | `path` | `WritePath` | Creates directories |
| `file` | `source` | `WritePath` | Source for copy/move/delete — if you can't access it, you shouldn't be able to copy/move/delete it |
| `file` | `destination` | `WritePath` | Always written to for copy/move |

### Guardrail pipeline

```
ReadPath:
  1. within filesystem_paths?                              HARD
  2. not in blocked_paths?                                 HARD

WritePath:
  1. within filesystem_paths?                              HARD
  2. not in blocked_paths?                                 HARD
  3. not in blocked_write_paths?                           SOFT (interactive), HARD (batch)
```

For WritePath, the effective blocklist is `blocked_paths + blocked_write_paths`.
`blocked_paths` is always hard. `blocked_write_paths` is soft (user can approve
interactively via `skip_blocks` flag, same mechanism as current `skip_protected`).
In batch mode (no interactive handler), soft blocks become hard — fail-safe.

### Tool-internal enforcement

`search` and `list` operate on directories and traverse files internally.
The guardrail only checks the path parameter (the directory), not each file
inside it. To prevent bypass (agent uses `search` to read content of files
that would be blocked by `blocked_paths`), these tools must internally filter
every file they touch against `blocked_paths`.

**Implementation approach:** The `ToolContext` (which tools already receive)
carries the compiled `blocked_paths` patterns. `search` and `list` use these
to skip blocked files during traversal, similar to how they already use
`IgnoreMatcher` for `.gitignore` patterns.

`git` and `make` operate on files internally behind a single directory
parameter. The guardrail can't intercept individual file accesses. This is
acceptable because:
- The agent can't control which files git/make touch internally
- `git` has its own `auto_permission` model (read-only ops auto-approved,
  write ops require interactive approval)
- `make` has its own env guardrail and target validation

### Glob matching semantics

- Patterns are matched against the **relative path** from the containing
  allowed root (POSIX-style, forward slashes)
- **Always case-insensitive** — safe direction for a security guardrail
  (over-restriction is harmless, under-restriction is a security hole)
- Full glob support: `*` (one segment), `**` (zero or more segments), `?`
  (single char), `[...]` (character classes)
- Matching a directory blocks it and everything beneath it
- Use `pathlib.PurePath.full_match()` (Python 3.13+) or a compatible glob
  library for `**` support. `fnmatch` does NOT handle `**` correctly.

**Pattern examples:**
- `.git` → blocks `./.git` (root-level directory and everything under it)
- `**/.git` → blocks `.git` at any depth in the tree
- `*.sh` → blocks `./script.sh` but not `./subdir/script.sh`
- `**/*.sh` → blocks any `.sh` file anywhere
- `Makefile` → blocks `./Makefile` only
- `**/Makefile` → blocks `Makefile` at any depth

### Symlink resolution

Paths are resolved with `os.path.realpath()` **before** any checks, collapsing
symlinks and `..` components. This prevents:
- Path traversal via `..`
- Symlink escape (symlink inside allowed root pointing outside)
- Must be preserved from the current implementation

### What is removed (clean break)

These are removed from the config and code. A clean error message should be
raised when unknown config keys are encountered (e.g. user has old
`allowed_extensions` under `[tools.read]`):

| Removed | Was in | Replaced by |
|---|---|---|
| `allowed_extensions` | `ReadToolConfig` | (no replacement — denylist-only) |
| `blocked_extensions` | `WriteToolConfig` | `blocked_write_paths` with glob patterns like `*.exe` |
| `blocked_patterns` (regex) | `ReadToolConfig` | `blocked_paths` (glob, in `PermissionsConfig`) |
| `protected_files` | `PermissionsConfig` | `blocked_write_paths` (in `PermissionsConfig`) |
| `Path` annotation | `yoker.tools.annotations` | `ReadPath` / `WritePath` |
| `max_file_size_kb` | `PermissionsConfig` | Stays as tool-specific config on `ReadToolConfig` |

### What stays as tool-specific config

These are operational parameters, not access control — they stay on their
respective tool config classes:

| Setting | Stays in | Reason |
|---|---|---|
| `allow_overwrite` | `WriteToolConfig` | Write tool behavior, not access control |
| `max_size_kb` | `WriteToolConfig` | Content size limit, not access control |
| `require_exact_match` | `UpdateToolConfig` | Update tool behavior |
| `max_diff_size_kb` | `UpdateToolConfig` | Diff size limit |
| `max_depth` | `ListToolConfig` | List tool behavior |
| `max_entries` | `ListToolConfig` | List tool behavior |
| `max_file_size_kb` | `ReadToolConfig` (move from PermissionsConfig) | Read size limit |
| `max_regex_complexity` | `SearchToolConfig` | Search tool behavior |
| `max_results` | `SearchToolConfig` | Search tool behavior |
| `timeout_ms` | `SearchToolConfig` | Search tool behavior |
| `allowed_commands` / `auto_permission` | `GitToolConfig` | Git operation gating |
| `allowed_env_vars` | `MakeToolConfig` | Make env gating |
| `max_depth` (mkdir) | `MkdirToolConfig` | Mkdir behavior |

### Deferred (not implementing now)

1. **File-type allowlist** — the old `allowed_extensions` served as a default-
   deny for file types. We're removing it in favor of denylist-only. Revisit
   if the need arises.

2. **Allow-exceptions on top of blocked paths** — e.g. block `.git` but allow
   `.git/description`. Not needed yet. If it becomes needed, the user can add
   individual files to `filesystem_paths` as a deliberate action.

## Implementation Plan

### Files to modify

#### 1. `src/yoker/tools/annotations.py`
- Add `ReadPath` and `WritePath` dataclasses (subclasses of `Text`)
- Add `PATH_READ` and `PATH_WRITE` to `GuardType` enum
- Keep `Path` as a backward-compat alias for `ReadPath` (or remove it — clean break)
- Update `__all__`

#### 2. `src/yoker/config/__init__.py`
- `PermissionsConfig`:
  - Add `blocked_paths` and `blocked_write_paths` (glob tuples)
  - Remove `protected_files` (moved to `blocked_write_paths`)
  - Remove `max_file_size_kb` (moves to `ReadToolConfig`)
- `ReadToolConfig`:
  - Remove `allowed_extensions` and `blocked_patterns`
  - Add `max_file_size_kb` (moved from `PermissionsConfig`)
- `WriteToolConfig`:
  - Remove `blocked_extensions`
- Update `_DEFAULT_PROTECTED_FILES` → becomes default `blocked_write_paths`
- Update `__post_init__` validators (remove regex pattern validation for
  `blocked_patterns`; add glob pattern validation if needed)
- Remove `_DEFAULT_PROTECTED_FILES` constant (absorbed into
  `blocked_write_paths` default)

#### 3. `src/yoker/tools/guardrails/path.py`
- Rewrite `PathGuardrail.validate()`:
  - Remove all `tool_name == "read"`, `tool_name == "write"`, etc. branches
  - Dispatch based on `GuardType` (PATH_READ vs PATH_WRITE) from the
    `ToolSpec.guards` mapping, not tool name
  - Unified pipeline: filesystem_paths → blocked_paths → [blocked_write_paths
    if WritePath]
  - Soft vs hard: `blocked_write_paths` check respects `skip_blocks` flag
    (renamed from `skip_protected`)
- Remove methods: `_check_read_extension`, `_check_write_extension`,
  `_check_protected_files`, `_check_blocked_patterns` (regex-based)
- Add methods: `_check_glob_match(resolved, patterns)` — case-insensitive glob
  matching against relative path
- Update `_resolve_path` — keep `os.path.realpath()` before checks
- Update `is_protected()` → `is_write_blocked()` (used by interactive approval
  hook)
- Pre-compile glob patterns in `__init__` (using `pathlib.PurePath.full_match`
  or equivalent)

#### 4. `src/yoker/tools/schema.py`
- `build_tool_spec()`: map `ReadPath`/`WritePath` annotations to
  `GuardType.PATH_READ`/`PATH_WRITE` in the `guards` dict
- `_build_parameter_schema()`: detect `ReadPath`/`WritePath` markers and
  return the correct `GuardType`

#### 5. `src/yoker/core/_processing.py`
- `_validate_tool_args()`: the guardrail lookup by `guard_type.value` already
  works — just needs to handle the new `PATH_READ`/`PATH_WRITE` types mapping
  to the same `PathGuardrail`
- Rename `skip_protected` parameter to `skip_blocks` (or keep as
  `skip_protected` for minimal diff — but `skip_blocks` is clearer)

#### 6. All builtin tools — update annotations
- `src/yoker/builtin/read.py` — `Path` → `ReadPath`
- `src/yoker/builtin/search.py` — `Path` → `ReadPath`
- `src/yoker/builtin/list.py` — `Path` → `ReadPath`
- `src/yoker/builtin/existence.py` — `Path` → `ReadPath`
- `src/yoker/builtin/make.py` — `Path` → `ReadPath`
- `src/yoker/builtin/git.py` — `Path` → `WritePath`
- `src/yoker/builtin/write.py` — `Path` → `WritePath`
- `src/yoker/builtin/update.py` — `Path` → `WritePath`
- `src/yoker/builtin/mkdir.py` — `Path` → `WritePath`
- `src/yoker/builtin/file.py` — `source`: `Path` → `WritePath`,
  `destination`: `Path` → `WritePath`

#### 7. `src/yoker/builtin/search.py` and `src/yoker/builtin/list.py`
- Add internal enforcement of `blocked_paths` during file traversal
- Access compiled `blocked_paths` patterns from `ToolContext`
- Skip files whose relative path matches any `blocked_paths` pattern
- Integrate with existing `IgnoreMatcher` or create a similar matcher

#### 8. `src/yoker/tools/context.py`
- `ToolContext`: add `blocked_paths` patterns (compiled glob patterns) so
  tools like `search` and `list` can access them for internal enforcement

#### 9. `src/yoker/config/validators.py`
- Remove `validate_regex_patterns` usage for `blocked_patterns` (no longer
  regex)
- Add glob pattern validation if needed (check for invalid glob syntax)
- Add validation for unknown config keys with helpful error messages

#### 10. `src/yoker/tools/guardrails/__init__.py`
- Update if `GuardType` references change

#### 11. Tests — rewrite/update
- `tests/tools/test_path_guardrail.py` — rewrite for new pipeline
- `tests/tools/test_read_guardrail.py` — update config setup
- `tests/tools/test_path_guardrail_protected.py` — update for
  `blocked_write_paths`
- `tests/tools/test_read.py` — update if config references changed
- `tests/tools/test_write.py` — update if config references changed
- `tests/tools/test_update.py` — update if config references changed
- Add new tests:
  - `ReadPath` blocks `search` from reading blocked files
  - `WritePath` checks `blocked_write_paths`
  - Case-insensitive matching (`Makefile` vs `MAKEFILE`)
  - Glob `**` patterns
  - `blocked_write_paths` soft block (interactive approval)
  - `blocked_write_paths` hard block (batch mode)
  - Tool-internal enforcement in `search`/`list`
  - Symlink escape still blocked
  - Unknown config keys raise errors

### Implementation order

1. **Annotations** (`annotations.py`) — add `ReadPath`/`WritePath`, update
   `GuardType`
2. **Config** (`config/__init__.py`) — new `PermissionsConfig` fields, remove
   old ones, move `max_file_size_kb` to `ReadToolConfig`
3. **Schema** (`schema.py`) — map new annotations to new guard types
4. **Guardrail** (`guardrails/path.py`) — rewrite with unified pipeline
5. **Tool context** (`context.py`) — add `blocked_paths` patterns
6. **Builtin tools** — update all annotations (`ReadPath`/`WritePath`)
7. **Search/list** — add internal `blocked_paths` enforcement
8. **Processing** (`_processing.py`) — update `skip_protected` → `skip_blocks`
9. **Validators** — remove regex validation, add unknown-key errors
10. **Tests** — rewrite and add new test cases
11. **Run `make check`** — format, lint, typecheck, test

### Glob matching implementation note

`fnmatch` does NOT handle `**` correctly — it treats `*` as matching
everything including `/`. Options:

1. **`pathlib.PurePath.full_match()`** — Python 3.13+, supports `**` and
   `case_sensitive` parameter. If we require 3.13+, use this.
2. **`wcmatch` library** — third-party, full glob support. Adds a dependency.
3. **Custom implementation** — translate glob to regex, handle `**` as
   `.*` and `*` as `[^/]*`. More work but no dependencies and works on 3.10+.

Check `pyproject.toml` for minimum Python version. If 3.13+, use
`full_match()`. Otherwise, a custom glob-to-regex translator is the safest
option.

### Config migration

Since this is a clean break, old config keys under `[tools.read]` and
`[tools.write]` that no longer exist should produce a clear error:

```
Configuration error: unknown key 'allowed_extensions' in [tools.read].
This setting has moved to [permissions] as 'blocked_paths' (glob patterns).
See the migration guide for details.
```

The config loading code (`config/__init__.py` or Clevis) should validate
that only known keys are present in each section.

### Current state of code (before this redesign)

Two bugs were already fixed in this session (dotfile matching and `\.git`
pattern over-broadness). Those fixes are in the working tree but will be
superseded by this redesign. The current git diff shows:

```
M src/yoker/config/__init__.py
M src/yoker/tools/guardrails/path.py
M tests/tools/test_path_guardrail.py
```

These changes should be discarded (or committed as a separate fix) before
starting the redesign implementation, since the redesign replaces all of
this code.