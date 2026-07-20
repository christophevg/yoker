# Yoker Development Guide

This document provides an overview of the project architecture, conventions, and recent changes for development purposes.

## Project Overview

Yoker is a Python agent harness with configurable tools and guardrails. It provides a provider-neutral backend architecture for LLM interactions, supporting Ollama (native SDK), OpenAI, Anthropic, Google Gemini, and 100+ providers via LiteLLM.

## Recent Changes

### M.2: Default Tools Behavior — Option C (2026-07-20)

Implemented the owner-approved Option C `ALL_TOOLS` sentinel so an agent
definition without a `tools:` line grants ALL config-enabled tools at
runtime, while a present-but-empty `tools:` line grants NO tools. The
sentinel replaces the earlier `tools_unspecified: bool` side-channel
flag — the intent now lives in the `tools` field value itself, with no
secondary flag to keep in sync.

- **`agents/schema.py`**: Added a dedicated `AllToolsSentinel` class
  (singleton via `__new__`, non-iterable with a `TypeError`-raising
  `__iter__`, self-documenting `repr` → `ALL_TOOLS`, pickle-safe via
  `__reduce__`, truthy via `__bool__`) and a module-level `ALL_TOOLS`
  singleton. `AgentDefinition.tools` field default changed from `()` to
  `ALL_TOOLS`; field type widened to `tuple[str, ...] | AllToolsSentinel`.
  `__post_init__` preserves the sentinel when set and normalizes
  `None`/`list` → `tuple` otherwise. The old `tools_unspecified: bool`
  field is removed entirely.
- **`agents/loader.py`**: Uses `"tools" not in frontmatter` (not `.get()`)
  to distinguish missing-key (→ `tools=ALL_TOOLS`, all tools) from
  present-but-null/empty (→ `tools=()`, no tools; logs
  `agent_tools_explicit_null_treated_as_empty` warning for the bare-null
  forms `tools:`/`null`/`~`). Non-empty lists parse as before. The
  `_namespace_tools` call is guarded with `isinstance(tools, AllToolsSentinel)`
  — the sentinel is not iterable, so namespacing is skipped when set.
- **`agents/validator.py`**: `validate_agent_definition` skips
  `validate_tools` when `definition.tools` is the `ALL_TOOLS` sentinel
  (guarded with `isinstance(definition.tools, AllToolsSentinel)`) — there
  is no explicit list to validate. The "must specify at least one tool"
  guard was already removed in round 0.
- **`core/__init__.py`**: Wired `validate_agent_definition` into the Agent
  constructor (`_validate_definition` helper logs warnings, never raises).
  `_filter_tools_by_definition` has three explicit Option C branches keyed
  on a local `tools = self.definition.tools` binding:
  `isinstance(tools, AllToolsSentinel)` → keep all (emit WARN
  `agent_tools_default_granted` at visible level); `len(tools) == 0` →
  clear registry; non-empty → filter (with case-insensitive `yoker:`
  prefix handling, unchanged). `_warn_missing_tools` early-returns when
  `isinstance(self.definition.tools, AllToolsSentinel)` (all tools granted
  by default — nothing to warn about). The runtime checks use
  `isinstance(..., AllToolsSentinel)` rather than `is ALL_TOOLS` because
  mypy only narrows `is` checks for `None`; `isinstance` narrows the
  `tuple[str, ...] | AllToolsSentinel` union correctly. The two are
  semantically equivalent because `AllToolsSentinel` is a singleton.
- **`ui/commands/tools.py` and `ui/commands/agents.py`**: Guarded the
  `/tools` and `/agents` command rendering against the sentinel — when
  `isinstance(..._definition.tools, AllToolsSentinel)` the command shows
  "ALL (no `tools:` filter)" instead of trying to iterate / `sorted()`.
- **`api.py`** (contract aligned with `AgentDefinition`): The
  `yoker.agent()` / `yoker.process()` / `yoker.do()` / `yoker.session()`
  `tools` kwarg defaults to `ALL_TOOLS` and is passed through UNCHANGED to
  `AgentDefinition` — the prior `tools=ALL_TOOLS if tools is None else
  tuple(tools)` bridge is removed, eliminating the dual contract flagged by
  the api-architect. `yoker.agent()` (no `tools` arg) and
  `yoker.agent(tools=ALL_TOOLS)` → all tools; `yoker.agent(tools=None)` →
  no tools (matches `AgentDefinition(tools=None)`); `yoker.agent(tools=[])`
  → no tools; `yoker.agent(tools=["yoker:read", ...])` → filter. A
  `typing.cast` reflects the post-`__post_init__` runtime invariant for
  mypy (the field's declared type is the post-normalization
  `tuple[str, ...] | AllToolsSentinel`; `None`/`list` are accepted at
  construction and normalized by `__post_init__`).
- **`CHANGELOG.md`**: Updated the Unreleased entry to describe the
  `ALL_TOOLS` sentinel (replacing the `tools_unspecified` paragraph).
- **Tests**: Updated `tests/core/test_agent_tools.py` (12 acceptance
  criteria, assertions swapped from `tools_unspecified is True/False` to
  `tools is ALL_TOOLS` / `tools == ()`), `tests/agents/test_loader.py`
  (8-case matrix asserts `tools is ALL_TOOLS` vs `tools == ()`),
  `tests/agents/test_validator.py` (uses default `AgentDefinition()` for
  the all-tools case), and `tests/test_agent.py` (one comment update).
  The `TestDocstringAgreement` class now asserts `ALL_TOOLS` appears in
  the `_filter_tools_by_definition` and `AgentDefinition` docstrings.

**Verification**: `make check` green — 1889 tests pass (+32 new), ruff
format/lint clean, mypy typecheck clean (123 source files).

### Clevis 0.7.0 Upgrade (2026-07-15)

Upgraded the Clevis dependency from 0.3.3 to 0.7.0, replacing all Clevis
internal API workarounds with native 0.7.0 functionality.

- **`pyproject.toml`**: bumped `clevis[tomlev]>=0.3.3` to `>=0.7.0`; ran
  `uv lock` + `uv sync` to update the lockfile and venv.
- **Feature #32 (configurable subcommand default)**: added `default_cmd=True`
  to `@configclass(cmd="chat", ...)` in `cli/commands.py`. Removed the
  `_needs_default_chat()` helper, `KNOWN_COMMANDS` set, and `sys.argv`
  patching block from `__main__.py`. Clevis now natively routes bare `yoker`
  to the `chat` subcommand.
- **Feature #33 (public TOML loader + config override cascade)**:
  - `plugins/file_manifest.py`: replaced `from clevis import _load_toml`
    (private) with `from clevis import load` (public). Removed
    `TODO(clevis-feature-request)` comment.
  - `cli/inspect.py`: same `_load_toml` → `load` replacement.
  - `config/__init__.py`: rewrote `get_yoker_config_with_manifest()` to use
    `build_default_cascade("yoker", security) + [manifest_provider]` and
    `get_config(Config, cascade=cascade, cli=cli)`. Removed all Clevis
    internals (`_load_toml_from_fd`, `_check_file_permissions`,
    `_check_directory_permissions`, `apply_to_dict`, `from_dict`, `get_factory`,
    `Config as DaciteConfig`) and the local `_deep_merge` helper. No
    `# type: ignore[attr-defined]` or `TODO(clevis-feature-request)` remain.
  - `cli/shared.py`: rewrote `load_subcommand_config_with_manifest()` to use
    Clevis 0.7.0's public helpers (`check_file_permissions`,
    `check_directory_permissions`, `load_toml_from_fd`, `deep_merge`,
    `get_factory`) and `dacite.from_dict` directly (dacite is a typed
    package). Removed all `# type: ignore[attr-defined]` and
    `TODO(clevis-feature-request)` comments. Behavior preserved: manifest
    overrides are still applied AFTER subcommand section extraction and
    BEFORE CLI args.
- **`cli/commands.py`**: updated `# type: ignore[arg-type]` to
  `# type: ignore[arg-type]` on decorator lines + added
  `# type: ignore[misc]` on class lines (Clevis 0.7.0's updated stubs
  produce a second `[misc]` error on the class definition line).
- **`tests/test_cli/test_dispatch.py`**: removed `TestNeedsDefaultChat`
  class (tested the deleted `_needs_default_chat` helper), removed
  `KNOWN_COMMANDS` import, removed `_needs_default_chat` mock from
  `TestMainDispatch` and `TestWithStrippingFromSubcommands` fixtures.
  `TestMainDefaultChat` now verifies that `get_cmd()` returns `"chat"` when
  no subcommand is given (Clevis native default_cmd behavior).
- **`CLAUDE.md`**: updated "Current State" to reflect `default_cmd=True`
  replacing `sys.argv` patching, and public cascade API replacing Clevis
  internals.

**Verification**: `make check` green — 1841 tests pass, ruff format/lint
clean, mypy typecheck clean (123 source files), 81% coverage.

### Clevis 0.7.0 Review Fixes (2026-07-15)

Addressed review feedback on the Clevis 0.7.0 upgrade.

- **Fix 1 (test coverage)**: Added 6 direct tests for
  `load_subcommand_config_with_manifest()` in
  `tests/test_cli/test_shared_manifest.py` — manifest overrides base TOML,
  CLI wins over manifest, subcommand section extraction, empty overrides
  no-op, validation runs, manifest overrides user TOML. Tests use
  `reload(yoker.cli.commands)` to re-register subcommand configs after
  `_reset_factories()` (reload creates new class objects, so tests
  reference `yoker.cli.commands.RunConfig` rather than a stale top-level
  import).
- **Fix 2 (integration test)**: Added `TestDefaultCmdIntegration` class in
  `tests/test_cli/test_dispatch.py` with 3 tests exercising Clevis's real
  `default_cmd=True` routing (no `get_cmd` mock): bare `yoker` routes to
  chat, `yoker --help` shows top-level help (SystemExit 0, no chat), `yoker
  run` routes to run.
- **Fix 3 (dead code)**: Removed the module-level `deep_merge` from
  `cli/shared.py` (in-place mutation variant, dead in production — the
  function imports `clevis.deep_merge` which returns a new dict). Updated
  `cli/__init__.py` exports and `cli/shared.py` `__all__`. Updated
  `TestDeepMerge` in `test_run.py` to use `clevis.deep_merge` (returns new
  dict, no mutation) and added a non-mutation test.
- **Fix 4 (explicit dependency)**: Added `dacite>=1.8.0` to `pyproject.toml`
  dependencies (was transitive via Clevis). Ran `uv lock` + `uv sync`.
- **Fix 5 (line length)**: Broke a 101-char f-string in
  `plugins/file_manifest.py` line 203 across two lines.

**Verification**: `make check` green — 1851 tests pass (10 new), ruff
format/lint clean, mypy typecheck clean (123 source files), 81% coverage.

### MBI-004: yoker Commands — Tasks 4.8, 4.9, 4.12 (2026-07-13)

Implemented the remaining Phase 3 CLI subcommands: `yoker loop` (interval
execution), `yoker container` (container setup generation), and `yoker inspect`
(read-only source report). All three are wired into `__main__.py` (replacing
the `STUB_COMMANDS` stubs).

- **`cli/loop.py`** (new): `run_loop()` — interval execution reusing `yoker run`'s
  source resolution and execution. Resolves the source ONCE, checks trust ONCE,
  loads ONCE, then runs the agent at intervals. `--interval` (default 300s),
  `--max-iterations` (default 100, finite per M1), `--max-duration` (wall-clock
  timeout). Stops after 3 consecutive failures with exponential backoff
  (`2**failures` seconds). Per-iteration timeout from
  `config.tools.agent.timeout_seconds`. Graceful SIGINT shutdown via an
  `asyncio.Event` stop flag + `_interruptible_sleep` that wakes early on stop.
  Prints iteration number + timestamp before each run and a summary on exit.
- **`cli/container.py`** (new): `run_container()` — generates Dockerfile (or
  Containerfile for `--engine podman`) for running a yoker agentic package in a
  container. Resolves the source via `resolve_source()` (phase 1) to determine
  type and (for GitHub) the commit SHA for pinning. Security (H3): JSON-array
  form exclusively for `RUN`/`ENTRYPOINT` (no shell-form injection), source
  string validated against shell metacharacters, non-root `USER 1000`,
  `~/.yoker.toml` NOT copied (secret management documented instead), yoker
  version pinned (`yoker==<version>` from `yoker.__version__`), GitHub sources
  pinned to resolved commit SHA via `git checkout`. Generates
  `.dockerignore`/`.containerignore` excluding `.git`, `__pycache__`, `*.pyc`,
  `.env`, `.yoker.toml`, `.ssh`, credentials, etc. Optional `--compose` flag
  generates `docker-compose.yml`.
- **`cli/inspect.py`** (new): `run_inspect()` — read-only source report. Uses
  `resolve_source()` (phase 1 only — no trust gate, no code execution).
  Displays: source type, trust key, what it contains (skills/agents names read
  from disk via Markdown+YAML parsing, tools_module name NOT imported), what it
  uses (dependencies from `pyproject.toml`, tools_module declaration), what it
  does (agent + prompt from manifest), config overrides. For module sources,
  notes "requires trust to inspect Python manifest" (can't import without trust).
  `load_source` is NEVER called; `check_source_allowed` is NEVER called.
- **`cli/commands.py`**: added `base_image` (default `python:3.12-slim`) and
  `compose` (default `False`) fields to `ContainerConfig`.
- **`__main__.py`**: `loop`, `container`, `inspect` subcommands now route to
  `run_loop()`, `run_container()`, `run_inspect()` respectively. Removed
  `STUB_COMMANDS` set entirely.
- **Tests**: `tests/test_cli/test_loop.py` (12 tests), `test_container.py` (34
  tests), `test_inspect.py` (9 tests) — 55 new tests covering: trust gate
  ordering (loop), missing source/agent/prompt errors, max-iterations, max-duration,
  3-failure stop with backoff, cleanup; shell metacharacter rejection, JSON-array
  form, non-root USER, version pinning, SHA pinning, podman Containerfile, compose;
  inspect read-only (no trust gate, no load_source), module trust notice, folder
  skills/agents listing, config overrides display, cleanup.

### MBI-004: yoker Commands — Task 4.7: `yoker run` (2026-07-13)

Implemented the flagship `yoker run <source>` subcommand — loads an agentic
package from a source (module, GitHub URL, folder, zip) and runs it
non-interactively. The source's `agent.toml` manifest specifies which agent
to use and what initial prompt to send; CLI `--agent` and `--prompt` override
the manifest.

- **`cli/run.py`** (new): `run_run()` — the run handler. Flow: resolve source
  (phase 1) → `--dry-run` prints and exits → trust gate
  (`check_source_allowed`) → load source (phase 2, AFTER trust) → apply
  manifest config overrides → resolve agent + prompt (CLI > manifest) →
  prompt length cap (10 KB) → Session + Agent + process prompt → cleanup.
  `--persist`/`--session-id` control session persistence (stateless by
  default). `--agent`/`--prompt` parsed via local argparse (stripped from
  sys.argv before Clevis parses RunConfig).
- **`plugins/security.py`**: added `check_source_allowed()` — the trust gate
  for `yoker run`. Mirrors `check_plugin_allowed()` but operates on a
  `trust_key` string (e.g. `"github:owner/repo@sha"`) BEFORE any code is
  loaded. Decision cascade: pre-trusted via `[plugins.trusted]` →
  `YOKER_TRUST_SOURCE=1` env var → interactive confirmation dialog (TTY) →
  non-interactive rejection. Uses the user's config (NOT manifest-overridden)
  so a source cannot influence its own trust decision.
- **`__main__.py`**: `run` subcommand now routes to `run_run()` (replaced the
  stub). Removed `run` from `STUB_COMMANDS`.
- **Tests**: `tests/test_cli/test_run.py` (new) — 28 tests covering:
  `--agent`/`--prompt` parsing, `--dry-run`, trust gate ordering (load_source
  not called when untrusted), non-interactive rejection, env-var override,
  pre-trusted, interactive accept/reject, prompt length cap, missing
  agent/prompt errors, CLI overrides, cleanup on success/error, config
  override deep-merge.
- Security: trust gate is a SECURITY INVARIANT — `load_source()` is never
  called before `check_source_allowed()` returns True. Non-interactive mode
  rejects untrusted sources by default. `--dry-run` prints manifest + prompt
  without executing. Prompt capped at 10 KB.

### MBI-004: yoker Commands — Tasks 4.2, 4.3, 4.4 (2026-07-08)

Implemented the `chat`, `init`, and `config` subcommand handlers under
`src/yoker/cli/`. The chat handler was extracted from `__main__.py` into
`cli/chat.py`; the init handler generates default config (interactive wizard
or non-interactive defaults); the config handler displays the effective merged
config as TOML or JSON with API key masking.

- **`cli/chat.py`** (new): `run_chat()`, `create_ui()`, `_run_with_session()`,
  `_run_repl()` — extracted from `__main__.py`. `__main__.py` now dispatches to
  `run_chat()` for the `chat` subcommand.
- **`cli/init.py`** (new): `run_init()` — interactive mode runs the
  `BootstrapWizard`; `--no-interactive` writes default config via
  `write_config(Config(), path)`. `--path` validates against forbidden system
  prefixes via `validate_storage_path`. `--force` overwrites with interactive
  confirmation when TTY.
- **`cli/config_cmd.py`** (new): `run_config_cmd()` — displays effective config
  as TOML (default) or JSON (`--json`). `--show-path` prints config file paths.
  `--reveal` shows API keys unmasked; default masks them (`***...last4`).
  Display flags (`json`, `show_path`, `reveal`) are projected out via
  `_to_base_config()` before rendering.
- **`cli/shared.py`**: added `abort()` helper (shared by `__main__.py` and
  subcommand handlers).
- **`__main__.py`**: refactored to dispatch `chat` → `run_chat()`, `init` →
  `run_init()`, `config` → `run_config_cmd()`. Removed moved functions
  (`_run_chat`, `_run_with_session`, `_run_repl`, `_create_ui`, `_abort`).
- **Tests**: `tests/test_cli/test_chat.py`, `test_init.py`, `test_config_cmd.py`
  (new). `tests/test_main.py` and `test_main_error_handling.py` updated to
  import from `yoker.cli.chat` instead of `yoker.__main__`.

### MBI-003: API Refactor — owner review round 3 (2026-07-07)

Follow-up to the 3rd CHANGES_REQUESTED review on PR #45. Removed the
unapproved `Session.primary_agent` / `Session._agent_id_for` /
`Session._spawn_and_run` additions introduced in the prior reduction
commit, and aligned the Python API with the owner's direction: the Python
API accepts `Agent` instances (not id strings); `agent_id`s are
string-references for the LLM only and are mapped to instances inside the
tool layer before calling the Python API.

- **`Session.spawn` split**: body extracted into
  `_spawn_internal(name, *, requester) -> tuple[Agent, str]` (returns
  `(child, agent_id)`); public `spawn(name, *, requester=None) -> Agent`
  is now a thin wrapper that returns only the Agent. The `agent` tool
  calls `_spawn_internal` directly and runs `child.process(prompt)` +
  `session.release(child)` inline (with `asyncio.wait_for` timeout) — the
  `_spawn_and_run` method was deleted.
- **`primary_agent` → `agent`**: the read-only property is now `Session.agent`
  (backed by `_agent`, set in `register_primary_agent`). `Session.primary_agent`
  was removed.
- **`_agent_id_for` removed**: `Session.release(agent)` now removes the agent
  by identity via a dict comprehension (single cleanup path; the private
  `_release(agent_id)` was also deleted).
- **`Session.send` accepts `Agent` instances**: new signature
  `send(*, to, from_, content) -> str`. The session-assigned id is stamped
  on the Agent as `agent._session_id` (Session-managed metadata, declared
  on `Agent` as `_session_id: str | None = None`) in both `_spawn_internal`
  and `register_primary_agent` — the bridge `send` uses to resolve ids
  for the `AgentMessageEvent` payload.
- **`send_message` tool**: resolves the LLM-facing `to`/`from_id` string
  references to `Agent` instances via the active map, then calls
  `session.send(to=, from_=, content=)`. No longer builds a `Message`.
- **`register_primary_agent`**: now also overrides the agent's backend with
  the session-shared one (`agent._backend = self.get_backend(agent.config)`)
  so the primary agent shares the same backend as spawned sub-agents
  without the caller passing `backend=` explicitly.
- **`make_config()` no-arg calls inlined**: `yoker/api/__init__.py` now
  uses `Config()` directly in `agent()` and `_session_config()`.
  `make_config` is still defined/exported from `yoker.config` (tested,
  may be used by external callers) but has zero production callers in
  `yoker.api` — flagged for a later keep/delete decision.
- **`examples/session_demo.py`**: drops `backend=session.get_backend(...)`
  from the primary `Agent(...)` construction; uses
  `session.send(to=researcher, from_=agent, content=...)` with `Agent`
  instances; removes the `_agent_id_for` lookup.
- **`examples/python_api/run_skill.py`**: now uses `yoker.do("commit", ...)`
  (one-shot) instead of `yoker.agent()` + `agent.do(...)`.
- **`examples/python_api/one_shot.py`**: env-var phrasing fixed (drops the
  non-existent `YOKER_BACKEND_PROVIDER` reference).
- **`examples/python_api/session.py`**: `session.primary_agent.process(...)`
  → `session.agent.process(...)`.
- **Tests updated** to match: `test_spawn.py`, `test_edge_cases.py`,
  `test_events.py`, `test_messaging.py`, `test_lifecycle.py`,
  `test_api/test_session.py`, `test_tools/test_agent.py`.

### MBI-003: API Reduction (2026-07-07)

Reduced the MBI-003 Python API to a minimal surface per the owner-approved
plan (PR #45, commit 4902976419). The three-module `yoker/api/` package
collapsed to a single thin module; the `ApiSession` facade class and the
`SpawnResult` dataclass were removed entirely; `Agent` no longer carries a
session-assigned id.

- **Public API surface** (`yoker/__init__.py` `__all__`): `Agent`, `Session`,
  `Config`, `process`, `do`, `agent`, `session`, `run_sync`. Removed:
  `ApiSession`, `SpawnResult`, `build_agent`, and the per-function `*_sync`
  wrappers.
- **`yoker/api/__init__.py`** is now the only module in the package:
  `agent(**kwargs) -> Agent` is the builder; `process(prompt, **kwargs)` and
  `do(skill_name, prompt, args="", **kwargs)` are one-shot helpers built on
  `agent()`; `session(id=..., *, persist=True, fresh=False, **kwargs)` is an
  async context manager that yields the **real** `yoker.session.Session`
  (no facade). Private helpers: `_thinking_mode`, `_apply_model_provider`,
  `_build_agent_definition`, `_filter_tools`, `_filter_skills`,
  `_session_config`, `_resolve_primary_definition`. Deleted:
  `_internal.py`, `one_shot.py`, `session.py`.
- **`SpawnResult` removed**: `Session._spawn_and_run` now returns a
  `(agent_id: str, response: str)` tuple. The `agent` tool renders
  `agent_id: <id>\n\n<response>` inline at the call site; the
  `_render_spawn_result` helper was deleted. `src/yoker/session/spawn_result.py`
  was deleted.
- **`Agent._agent_id` removed**: the Session owns the registry key. New
  `Session._agent_id_for(agent) -> str` does the registry lookup (used by
  `_spawn_and_run`); new `Session.release(agent) -> None` is the public
  cleanup wrapper over `_release(agent_id)`; new `Session.primary_agent`
  read-only property (backed by `register_primary_agent()`). The three
  `agent._agent_id = agent_id` assignments in `spawn()`,
  `register_primary_agent()`, and `_spawn_and_run()` were deleted.
- **`do` added to the public API**: `yoker.do(skill_name, prompt, args="")`
  one-shot skill invocation, mirroring `yoker.process`. Tests in
  `tests/test_api/test_do.py`.
- `examples/session_demo.py` and `examples/python_api/session.py` updated
  to the new API (`session._agent_id_for(...)`, `session.release(...)`,
  `session.primary_agent.process(...)`).

### MBI-003: Python API Redesign (2026-07-06)

Redesigned the Pythonic utility API into a three-layer facade
(`process` / `agent` / `session`) and made `Agent` fully Session-agnostic
per the owner-approved design decisions. This is a breaking redesign of
the MBI-003 v1 surface; the prior `ask` / `complete` / `run_skill` /
`build_agent` exports were removed.

**Renamed `src/yoker/agent/` -> `src/yoker/core/`** (Decision 1) so the
`yoker.agent` name is free for the factory function in `yoker.api`.
`Agent` is now a Session-agnostic primitive (Decision 4): no `session`
constructor param, no `self._session` attribute, no `Agent.spawn()`.
Backend/definition/plugin-loading moves to the Session layer.
`Agent.on_event()` is retained; `Agent.process()` is retained
(Decision 6); new `Agent.do(skill_name, prompt, args="")` invokes skills
(Decisions 7, 9 — no `process(prompt, skill=...)` parameter).

**New public API surface (`src/yoker/__init__.py`)**: `process`, `run_sync`,
`agent`, `session`, `Agent`, `Session`, `ThinkingLiteral`.
Removed: `ask`, `ask_sync`, `complete`, `complete_sync`, `run_skill`,
`run_skill_sync`, `build_agent`, `ApiSession`, `make_config`, `Message`,
`EventReplayAgent`.

**Three layers (`src/yoker/api/`)**:
- `_internal.py` — shared helpers: `build_agent()` (now accepts
  `backend: ModelBackend | None`), `run_sync()`, `thinking_mode()` mapping,
  tool/skill filters, model/provider override. Dead `if TYPE_CHECKING:
  pass` removed.
- `one_shot.py` — Layer 1: `process(prompt, **kwargs)` (Decision 2; no
  tools -> `tools=[]`, no system prompt -> `system_prompt=""`). Dropped
  `ask`, `complete`, `run_skill`, and all `*_sync` variants.
- `__init__.py` — inlined the `agent()` factory (Decision 5;
  `builder.py` deleted). Signature:
  `agent(*, model=None, provider=None, system_prompt=None, tools=None,
  skills=None, plugins=None, agent_path=None, agent_definition=None,
  thinking="on", event_handler=None, config=None,
  context_manager=None) -> Agent`.
- `session.py` — Layer 3 facade: `session(id=...) -> ApiSession`. Uses
  `session.agent` explicitly (Decision 3 — no tuple unpacking). Removed
  `ask()`, `run_skill()`, and spawn-with-prompt; `Session.spawn(name)`
  returns an Agent (no prompt, no response, no tuple, no SpawnResult —
  Decision 8).

**Single sync helper (Decision 5)**: `yoker.run_sync(coro)` wraps
`asyncio.run` and raises a clear error if called inside a running loop.
Dropped per-function `ask_sync` / `run_skill_sync` / `complete_sync`.

**Session changes (`src/yoker/session/`)**:
- `Session.spawn(name, *, requester=None) -> Agent` — public, returns a
  reusable Agent (no prompt, no SpawnResult in the public API; Decision 8).
  Sets `child._agent_id` before returning.
- `Session._spawn_and_run(name, prompt, *, requester=None,
  timeout_seconds=300) -> SpawnResult` — internal, used by the `agent`
  tool for run-to-completion semantics.
- `Session._release(agent_id)` — emits `AGENT_FINISHED` and cleans up the
  active map / recursion depth entries.
- `Session.__init__` accepts `extra_plugins: tuple[str, ...] = ()` and
  calls `register_configured_plugin_agents(self.agents, config,
  extra_plugins)` to populate the registry.
- `register_primary_agent` now sets `agent._agent_id = agent_id`.
- `Session.get_backend(config)` is used by `__main__.py` and
  `examples/session_demo.py` to share the backend with the primary Agent.
- `SpawnResult` is no longer in `yoker.session`'s `__all__`; tests import
  it from `yoker.session.spawn_result`.

**Plugin agent-definition loading split (Decision 4)**:
- Standalone `Agent` calls `load_configured_plugins(self, self.config,
  self._cli_plugins, session=None)` — skips agent-definition registration
  with a warning.
- `Session` calls the new `register_configured_plugin_agents(registry,
  config, extra_plugins)` in `yoker.plugins.loader` (exported via
  `yoker.plugins`) to populate the registry.

**Config factory (`src/yoker/config/__init__.py`)** — unchanged from the
prior MBI-003 v1: `make_config(...)` builds a `Config` programmatically
without TOML discovery / CLI args.

**`__main__.py`**: `_run_with_session` now constructs
`async with Session(config=config, extra_plugins=tuple(plugin_packages))
as session:`, resolves `agent_definition` via
`session.agents.resolve(reference)` or `load_agent_definition(reference)`,
and constructs `Agent(config=config, plugins=..., agent_definition=...,
backend=session.get_backend(config), console_logging=...)` (no
`session=` kwarg).

**Examples updated** (`examples/python_api/*.py` and
`examples/session_demo.py`):
- `one_shot.py` uses `yoker.process` / `yoker.run_sync`.
- `agent_builder.py`, `event_handling.py` use `yoker.agent`.
- `session.py` uses `session.agent.process(...)`.
- `sync_usage.py` uses `yoker.run_sync`.
- `run_skill.py` uses `agent.do(...)`.
- `workflow.py` uses robust JSON parsing with `cast(list[Any], ...)`
  typing and one retry.
- `session_demo.py` uses `session.spawn(name)` -> Agent, then
  `agent.process(...)`, then `session._release(agent_id)`.

**Tests**: `tests/test_api/{test_one_shot,test_builder,test_session}.py`,
`tests/test_session/{test_spawn,test_events,test_edge_cases,
test_backward_compat}.py`, `tests/test_tools/test_agent.py`,
`tests/test_config/test_discover_config.py`, `tests/test_main.py`,
`tests/test_agent.py`, `tests/test_agent_loading.py` — all updated to the
new API: `yoker.build_agent` -> `yoker.agent`; `yoker.ask` ->
`yoker.process`; `sess.ask()` -> `sess.agent.process()`; rejection-path
tests use `session.spawn(name, requester=...)` (no prompt);
run-to-completion tests use `session._spawn_and_run(...)`; `_session`
assertions removed; `session=` removed from `Agent(...)` calls and the
agent definition resolved via `session.agents.resolve()` +
`agent_definition=...`. `SpawnResult` imports moved to
`yoker.session.spawn_result`.

**Verification**: `make check` green — 1672 tests pass, ruff format/lint
clean, mypy typecheck clean (118 source files), 81% coverage.

### MBI-003 v1: Python API (2026-07-06, superseded by the redesign above)

Implemented the three-layer Pythonic utility API from
`analysis/mbi-003-python-api-design.md` as a facade over the existing
`Agent` / `Session` classes. This v1 surface (`ask` / `complete` /
`run_skill` / `build_agent` / `Agent.spawn` / `Agent.session`) was
replaced by the MBI-003 redesign above. See the redesign entry for the
current public API.

**v1 surface (removed in the redesign)**:
- New module `src/yoker/api/` with `_internal.py`, `one_shot.py`,
  `builder.py`, `session.py`, `__init__.py`.
- `make_config(...)` builds a `Config` programmatically (retained).
- `Agent.on_event(handler)` (retained) and `Agent.spawn(name, prompt, *)`
  (removed — Session-agnostic Agent).
- Top-level exports: `ask`, `ask_sync`, `complete`, `complete_sync`,
  `run_skill`, `run_skill_sync`, `build_agent`, `session`, `ApiSession`
  (replaced by `process`, `run_sync`, `agent`, `session`, `ApiSession`).
- 63 tests in `tests/test_api/` (rewritten for the redesign).

### PR #43 Review Fixes (2026-07-04)

Addressed four inline CHANGES_REQUESTED review comments on commit 7bf95a7.

1. **Deleted `src/yoker/builtin/agent.py`** (Comment 4): removed the
   empty placeholder module entirely. The `agent` tool now lives only in
   `src/yoker/session/tools.py`. Updated `src/yoker/builtin/__init__.py`
   docstring/comments, and replaced
   `tests/test_session/test_backward_compat.py::test_make_agent_tool_removed_from_builtin`
   with `test_builtin_agent_module_removed` asserting the module is gone.

2. **Renamed `SpawnAgent` tool back to `agent`** (Comment 5):
   `__yoker_name__ = "agent"`, registered as `name="agent"` (namespaced
   `yoker:agent`). Updated docstrings and tests in
   `tests/test_tools/test_agent.py` (renamed test classes to
   `TestAgentTool*` and updated name assertions to `yoker:agent` /
   `yoker__agent`).

3. **Renamed `SendMessage` tool to `send_message`** (Comment 6):
   `__yoker_name__ = "send_message"`, registered as
   `name="send_message"` (namespaced `yoker:send_message`). Updated
   docstrings and tests (`yoker:send_message` / `yoker__send_message`).

4. **Per-Agent message queue** (Comment 7, architectural): the Agent now
   serializes concurrent `process()` calls via an internal
   `asyncio.Queue` and a lazily-started background consumer task. The
   public `process()` API is unchanged — callers still
   `await agent.process(msg)`. When `Session.send` injects a message
   while the agent is mid-turn, the new request waits in the queue
   instead of starting a parallel `chat_stream`. New tests in
   `tests/test_agent/test_process_queue.py` (8 tests) verify
   serialization, FIFO order, single-call transparency, exception
   propagation to the correct caller, and consumer lifecycle.

Comments referencing the old tool names were updated across
`src/yoker/__main__.py`, `src/yoker/agent/__init__.py`,
`src/yoker/agent/_processing.py`, `src/yoker/tools/context.py`,
`src/yoker/session/{session,spawn_result,tools}.py`,
`src/yoker/builtin/__init__.py`, `examples/session_demo.py`, and the
test files.

### MBI-007 Phase 5: Session Quality — Tests, Docs, Final Verification (2026-07-04)

**Task**: Closed out MBI-007 with comprehensive coverage, a multi-agent
demo example, and documentation updates. All acceptance criteria from
PLAN.md verified.

1. **7.9.1 — Coverage gap tests**: new
   `tests/test_session/test_edge_cases.py` (14 tests) covers the
   previously uncovered branches in `src/yoker/session/`:
   - `Session.spawn` resolution failure paths (`ValueError` re-raise and
     non-`ValueError` wrapping — session.py lines 286-289).
   - `Session._derive_config` model-override branch (lines 511-520),
     including provider preservation, parent-config immutability, and
     end-to-end spawn with a fresh backend.
   - `_render_spawn_result` with empty `agent_id` (tools.py line 64).
   - `_clamp` bounds and the SpawnAgent tool's timeout clamping
     integration (lines 52, 96).
   Session module is now at 100% coverage; overall project coverage
   rose from 80% to 81%.

2. **7.9.2 — Lifecycle & backward-compat tests**: kept and verified the
   interrupted-attempt files `tests/test_session/test_lifecycle.py`
   (197 lines, 9 tests covering `__aexit__` on exception, handler
   exception isolation, registry population edge cases, and
   `register_primary_agent` behaviour) and
   `tests/test_session/test_backward_compat.py` (152 lines, 11 tests
   covering single-agent `Agent` without session, removed
   `_recursion_depth`/`agents`/`recursion_depth`/`max_recursion_depth`
   surfaces, `run_session` → `run_repl` rename, `make_agent_tool`
   removal, and existing-examples import cleanly).

3. **7.10.1 — `examples/session_demo.py`**: new runnable demo showing
   `Session` construction, primary-agent registration, session-scoped
   event handlers, programmatic `session.spawn(...)` (canonical API,
   Decision 8), and inter-agent messaging via `session.send(Message)`.
   Loads the existing `examples/agents/researcher.md` definition.
   Imports cleanly; gracefully reports `NetworkError` when no backend
   is running (mirroring `library_usage.py`).

4. **7.11.1 — `docs/rationale.md` updated**: the "Recursive Composition:
   True Sub-Agents" section now reflects the real `Session` construct —
   the async context manager that owns the team of agents, lifecycle,
   registry, recursion depth, event aggregation, and inter-agent
   messaging. The differentiators summary table now reads "Full
   instances, coordinated by a Session" rather than just "Full
   instances".

5. **7.11.4 — `analysis/mbi-003-python-api-design.md` updated**: the
   MBI-003 Python API design (which was on hold pending MBI-007) is now
   updated to note that `yoker.session()` will be a **facade over the
   real Session construct**. The "No session primitive" problem
   statement is marked resolved; the integration diagram and "What
   changes" section now point to `Session.spawn` as the canonical
   sub-agent API (no more `_create_subagent`/`_run_with_timeout` —
   those were removed in Phase 2).

6. **Bug fix in `Session._derive_config`**: the model-override branch
   used `setattr(new_backend, provider, new_sub)` on a frozen
   `BackendConfig`, which raised `FrozenInstanceError` whenever an agent
   definition had a `model` override. Replaced with
   `dataclasses.replace(parent_config.backend, **{provider: new_sub})`
   (provider-agnostic, single-key dict). The new test
   `test_derive_config_applies_model_override` reproduces the bug and
   verifies the fix. Without the fix, any agent definition with
   `model: <name>` in its frontmatter would have crashed on spawn.

7. **7.12.1 — `make check` green**: 1574 tests pass (+36 new Phase 5
   tests), ruff format/lint clean, mypy typecheck clean (106 source
   files), 81% coverage. Session module at 100% coverage.

8. **7.12.2 — Acceptance criteria verified**: all 15 PLAN.md criteria
   for MBI-007 are met (see reporting/mbi-007-session/development-summary.md
   for the per-criterion breakdown).

**Files Created**: `examples/session_demo.py`,
`tests/test_session/test_edge_cases.py`,
`reporting/mbi-007-session/development-summary.md`.
**Files Modified**: `src/yoker/session/session.py` (bug fix),
`docs/rationale.md`, `analysis/mbi-003-python-api-design.md`,
`tests/test_session/test_backward_compat.py` (lint fix).
**Files Kept (interrupted-attempt)**:
`tests/test_session/test_lifecycle.py`,
`tests/test_session/test_backward_compat.py`.

### MBI-007 Phase 4: Session Integration — SpawnAgent, SendMessage, run_repl (2026-07-04)

**Task**: Integrated the `Session` primitive into the application flow:
Session-injected tools (`SpawnAgent`, `SendMessage`), `ToolContext.session`
reference, `run_session` → `run_repl` rename, and `main()` wiring
(Decision 5/6/8, PR #43 Clarifications 2, 4, 5, 6).

1. **7.8.1 — `ToolContext.session`**: added `session: Session | None =
   None` field to `ToolContext` in `src/yoker/tools/context.py`.
   `_build_tool_context` in `agent/_processing.py` threads
   `agent._session` through so session-aware tools can reach the owning
   Session. `None` on the single-agent path (Decision 8).

2. **7.8.2 — `Session.spawn()` returns `SpawnResult`**: new
   `src/yoker/session/spawn_result.py` defines
   `SpawnResult(agent_id: str, response: str)` (frozen). `Session.spawn()`
   now returns `SpawnResult` instead of a bare string (PR #43
   Clarification 5 — the caller learns the spawned agent's unique id).
   `SpawnAgent` renders both fields into its `ToolResult` so the model can
   read the spawned id and address it later via `SendMessage`. Exported
   via `yoker.session`.

3. **7.8.3 — `SpawnAgent` tool (Session-injected)**: new
   `src/yoker/session/tools.py` provides `make_spawn_agent_tool(session,
   requester)` — the Session captures itself in the closure
   (back-reference, PR #43 Clarification 2) and the tool delegates to
   `session.spawn(...)` with `requester` set (allowlist enforcement). The
   tool name is `SpawnAgent` (replaces the old `agent` tool); available
   agent names are baked into the `agent_name` parameter description from
   `requester.definition.agents` intersected with `session.agents.names`.
   The old `make_agent_tool` / `_create_subagent` / `_run_with_timeout` /
   `_clamp` are removed from `src/yoker/builtin/agent.py` (now an empty
   placeholder). `src/yoker/builtin/__init__.py` no longer exports
   `make_agent_tool`.

4. **7.8.6 — `SendMessage` tool (Session-injected)**: new
   `make_send_message_tool(session, from_id)` in
   `src/yoker/session/tools.py`. Builds a `Message(from_id=<caller
   runtime name>, to_id=to, content=message)` and calls
   `session.send(...)`. Returns the target's response string, or an error
   result when the target is no longer active (PR #43 Clarification 7 —
   finished agents are removed from the active map). `ListAgents` is
   deferred (PR #43 Clarification 6) and is NOT injected.

5. **7.8.4 — `Session.inject_tools` / `register_primary_agent`**: new
   methods on `Session`. `inject_tools(agent, agent_id)` registers
   `SpawnAgent` (gated by `config.tools.agent.enabled`) and `SendMessage`
   on the agent's tool registry. `register_primary_agent(agent)` assigns
   a session-scoped id, adds the agent to the active map at recursion
   depth 0, and injects the Session tools. `Session.spawn()` calls
   `inject_tools` on each spawned child so every agent in a session can
   spawn sub-agents and send inter-agent messages.

6. **7.8.4 — `run_session` → `run_repl`**: renamed in
   `src/yoker/__main__.py` (Decision 6, PR #43 Clarification 1 — no
   alias). All test references updated.

7. **7.8.5 — `main()` constructs Session + UIBridge on Session**:
   `_run_with_session` in `__main__.py` now calls
   `session.register_primary_agent(agent)` (injects SpawnAgent and
   SendMessage on the primary agent) and `session.add_event_handler(bridge)`
   (Decision 5 — UIBridge registered on Session, not Agent, so
   aggregated sub-agent events reach the UI). The user-visible behaviour
   of `python -m yoker` is unchanged.

8. **Pre-existing fix — `Annotated` metadata extraction**: `_build_parameter_schema`
   in `src/yoker/tools/schema.py` used `getattr(annotation, "__args__", ())`
   which returns only the first type argument for `Annotated[T, marker]`
   forms, leaving the marker unreachable. Switched to `typing.get_args()`
   so `Annotated[str, Text(...)]` markers are correctly extracted. This
   also required `_validate_tool_args` in `agent/_processing.py` to use
   `.get()` instead of `[]` for the guardrail lookup (the `Text` guard
   type is now correctly detected, and the Agent's `_guardrails` dict
   does not contain a `"text"` entry — `None` is the correct skip path).

### MBI-007 Phase 3: Session Communication & Event Aggregation (2026-07-04)

**Task**: Implemented inter-agent messaging (7.4) and event aggregation
(7.7) for the `Session` primitive. Agents can now address each other
through `Session.send(Message)` and the Session fans out sub-agent
events to session-level handlers wrapped in a `SessionEvent` envelope
(agent_id tagging without modifying frozen event dataclasses — PR #43
Clarification 9).

1. **7.4.1 — Message dataclass finalized**: `Message(from_id, to_id,
   content, metadata)` in `src/yoker/session/message.py` is frozen with
   a per-instance `metadata` default. Exported via `yoker.session`.

2. **7.4.2 — `Session.send(message: Message) -> str`**: routing method
   on `Session`. Looks up the target by `message.to_id` in
   `self._agents_map` (raises `ValueError` if absent), emits
   `AgentMessageEvent`, calls `await target.process(message.content)`,
   and returns the response string. Target exceptions are caught and
   returned as an error string (no propagation — preserves the
   `agent` tool's behaviour).

3. **7.4.3 — `_generate_agent_name` verified**: the name disambiguation
   helper from Phase 1 already produces `researcher`, `researcher-2`,
   `researcher-3`, ... per Decision 2. No changes needed.

4. **7.7.1 — Session event types verified**: `SessionStartEvent`,
   `SessionEndEvent`, `AgentSpawnedEvent`, `AgentFinishedEvent`,
   `AgentMessageEvent` already exist from Phase 1 and are exported from
   `yoker.events`.

5. **7.7.2 — `SessionEvent` envelope + aggregator**: new
   `src/yoker/events/session_event.py` defines
   `SessionEvent(agent_id: str, event: Event)` (frozen). `Session.spawn`
   now registers an async forwarding handler on each child agent that
   wraps every emitted `Event` in `SessionEvent(agent_id=<runtime
   name>, event=<original>)` and forwards it to `session._event_handlers`.
   The original event dataclasses and their construction sites in
   `agent/_processing.py` are untouched. `AGENT_SPAWNED` is emitted
   after the child is registered; `AGENT_FINISHED` is emitted in the
   `finally` block before the agent is removed from `_agents_map`
   (Clarification 7 — visible states `{idle, running}` only). When
   `config.session.event_aggregation` is False, no forwarding handler
   is registered (sub-agent events suppressed).

6. **7.7.3 — `UIBridge` handles `SessionEvent` + lifecycle events**:
   `UIBridge.__call__` accepts `Event | SessionEvent`. For envelopes it
   unpacks the inner event, records `agent_id` on `self._current_agent_id`
   for tagging, and dispatches the inner event unchanged. Bare events
   (single-agent path) dispatch as before. New dispatch cases:
   `AGENT_SPAWNED` → `ui.agent_spawned(name)` (guarded),
   `AGENT_FINISHED` → `ui.agent_finished(name)` (guarded),
   `SESSION_START` / `SESSION_END` / `AGENT_MESSAGE` → no-op.

7. **7.7.4 — Optional `UIHandler` methods (no `BaseUIHandler`)**: per
   PR #43 Clarification 8, `agent_spawned(name: str)` and
   `agent_finished(name: str)` are documented on the `UIHandler` protocol
   as optional methods (in a comment block, not as Protocol members —
   this keeps mypy structural typing from requiring them on every
   handler). `InteractiveUIHandler` implements them (Rich-styled
   "Agent spawned" / "Agent finished" lines); `BatchUIHandler` does not
   and is not broken. The bridge guards calls with
   `getattr(handler, method, None)`. No `src/yoker/ui/base.py` is created.

8. **7.7.5 — `EventRecorder` / `serialize_event` / `deserialize_event`
   support `SessionEvent`**: serialization produces an envelope form
   `{"session_event": True, "agent_id": ..., "event": <inner>}`;
   deserialization reconstructs the `SessionEvent` when the marker is
   present, and bare events roundtrip unchanged (backward compatible).
   `EventReplayAgent` accepts `Event | SessionEvent` traces.

**Type system**: `EventCallback` in `yoker.events.types` is now
`Callable[[Event | SessionEvent], ...]` (referenced via a forward
reference to avoid a circular import with `session_event.py`).
`EventReplayAgent._emit` and `EventReplayAgent.events` accept the
union. The `library_usage.py` example handler was updated to accept the
union and unwrap envelopes for display.

**Decisions applied**: D3 (inter-agent messaging is request-response
through `Session.send`, plain-string content, no streaming), D5 (event
aggregation with `SessionEvent` envelope), PR #43 Clarifications 7
(`finished` state dropped — agents removed from active list on
completion), 8 (no `BaseUIHandler` — optional protocol methods guarded
by `getattr`), and 9 (`SessionEvent` envelope wrapper — no changes to
existing frozen event dataclasses).

**Files Created**: `src/yoker/events/session_event.py`,
`tests/test_session/test_messaging.py`,
`tests/test_session/test_events.py`,
`tests/test_ui/test_bridge_session.py`.

**Files Modified**: `src/yoker/events/__init__.py`,
`src/yoker/events/recorder.py`, `src/yoker/events/replay.py`,
`src/yoker/events/types.py`, `src/yoker/session/session.py`,
`src/yoker/ui/bridge.py`, `src/yoker/ui/handler.py`,
`src/yoker/ui/interactive.py`, `examples/library_usage.py`.

**Verification**: `make check` green — 1534 tests pass (+33 new Phase 3
tests), ruff format/lint clean, mypy typecheck clean, 80% coverage.

### MBI-007 Phase 2: Session Migration (2026-07-04)

**Task**: Migrated orchestration responsibilities from `Agent` to `Session`
(10 sub-tasks across 7.3, 7.2, 7.5). The `AgentRegistry`, recursion depth
tracking, and backend factory now live on `Session`; `Agent` is a thin
single-agent primitive that optionally belongs to a `Session`.

**Changes**:

1. **7.3.1 / 7.3.2 / 7.3.4 — Registry migration**: `Session.agents` is a
   public `AgentRegistry` populated from `config.agents.directories` and
   plugin manifests (`_load_agents()` relocated from `Agent`). Plugin agent
   registration in `plugins/loader.py` now targets `session.agents` when a
   session is provided (warning + skip when session is `None`).
   `Agent.agents` removed entirely (no shim — PR #43 Clarification 1).
2. **7.3.3 — Agent allowlist**: added `agents: tuple[str, ...] = ()` field
   to `AgentDefinition` (`agents/schema.py`) and parsing in
   `agents/loader.py`. `Session.spawn(name, prompt, *, requester=None)`
   enforces the allowlist: when `requester` is set and
   `requester.definition.agents` is non-empty, `name` must be in it;
   `requester=None` (top-level) bypasses the check.
3. **7.2.1 / 7.2.2 — Agent field removal**: removed `agents`,
   `recursion_depth`, `max_recursion_depth` from `Agent`; removed
   `_recursion_depth` constructor arg; removed `validate_recursion_depth`
   from `agent/_setup.py`. Callers passing `_recursion_depth=` now get
   `TypeError`; accessing `agent.agents` now gets `AttributeError`.
4. **7.2.3 — Session reference**: `Agent.__init__` accepts
   `session: Session | None = None`, stored as `self._session`. Without a
   session the Agent is a standalone single-agent primitive (first-class
   path, not a compat shim — Clarification 1). `_resolve_agent_definition`
   uses `session.agents.resolve()` when a session is set; without one it
   raises a clear `ValueError("... cannot be resolved without a Session")`
   for name-based references (file-path resolution still works).
5. **7.2.4 — Plugin loading split**: `load_configured_plugins` takes a
   `*, session: Session | None = None` keyword. Plugin agents →
   `session.agents`; tools/skills remain per-agent.
6. **7.5.1 — Backend factory**: `Session.get_backend(config) -> ModelBackend`
   with a per-provider cache keyed by `provider|model|base_url|api_key`
   (`_backend_key` static method). Same-config calls share one backend;
   model overrides produce a fresh backend.
7. **7.5.2 — Agent backend sharing**: `Agent.__init__` uses
   `session.get_backend(self.config)` when a session is provided; falls
   back to `create_backend(self.config)` for the standalone path.
8. **`Session.spawn`**: full spawn orchestration — allowlist check →
   registry resolution → recursion depth check (`parent_depth + 1 >
   max_recursion_depth`) → max_agents cap → `_derive_config` (model
   override via `dataclasses.replace`) → `session.get_backend` → unique
   agent name (`_generate_agent_name`) → `Agent(session=self,
   backend=backend)` → `asyncio.wait_for(child.process(prompt), timeout)`
   → `finally` removes the agent from `_agents_map`/`_recursion_depths`
   (Clarification 7: finished agents leave the active list).
9. **`builtin/agent.py`**: `make_agent_tool` rewritten to delegate to
   `session.spawn()` via `parent_agent._session`. Returns a clear
   `ToolResult(success=False)` when no session is available; wraps
   `ValueError` (allowlist/depth/capacity), `TimeoutError`, and generic
   exceptions as `ToolResult(success=False, ...)`. `_create_subagent` /
   `_run_with_timeout` removed (logic moved to `Session.spawn`). The full
   `SpawnAgent` rewrite lands in Phase 4 (7.8.3).
10. **`__main__.py`**: `main()` now loads config via `get_yoker_config(cli=True)`
    first, then calls `asyncio.run(_run_with_session(...))` which constructs
    `Session(config=config)`, then `Agent(config=config, session=session,
    plugins=..., console_logging=...)`, wires the `UIBridge`, and runs
    `run_session`. Errors from `_run_with_session` (ValueError,
    SecurityError) are caught and printed cleanly with exit code 1.
11. **`ui/commands/agents.py`**: reads `agent._session.agents` instead of
    `agent.agents.agents`.

**Tests**:
- `tests/test_session/test_spawn.py` — new, 15 tests covering allowlist (5),
  recursion depth (2), max_agents (1), agent map (2), backend factory (3),
  registry population (2).
- `tests/test_tools/test_agent.py` — rewritten to verify delegation to
  `session.spawn` (no-session error, success, ValueError/TimeoutError/generic
  wrapping, default timeout forwarding) plus retained `_clamp` and schema
  tests.
- `tests/test_agent.py` — removed 4 recursion_depth tests; added
  `test_agent_recursion_depth_arg_removed` (expects `TypeError`),
  `test_agent_agents_attribute_removed` (expects `AttributeError`),
  `test_agent_session_reference_defaults_none`.
- `tests/test_commands/test_agents.py` — `_make_agent` builds a real
  `AgentRegistry` and mocks `agent._session.agents`.
- `tests/test_agent_loading.py` — `TestRegistryAgentResolution` now
  constructs a `Session` for name-based resolution; added
  `test_resolution_without_session_raises`. File-path resolution tests
  updated to wrap in a Session where the registry's "Agent not found" error
  is expected.
- `tests/test_config/test_discover_config.py` —
  `test_agent_definition_config_missing_file` wraps in a `Session`.
- `tests/test_main.py` — `test_main_creates_batch_ui_and_runs_session`
  asserts the new Agent constructor kwargs (`config`, `session`,
  `plugins`, `console_logging`).

**Decisions applied**: D9 (Session owns backend factory, shares across
same-provider agents), D10 (AgentRegistry moves to Session), Clarification 1
(no backward-compat shims — removals are outright), Clarification 3
(`AgentDefinition.agents` allowlist enforced before spawn), Clarification 7
(finished agents leave the active list, visible states `{idle, running}`).

**Files Modified**: `src/yoker/agents/schema.py`,
`src/yoker/agents/loader.py`, `src/yoker/session/session.py`,
`src/yoker/agent/__init__.py`, `src/yoker/agent/_setup.py`,
`src/yoker/plugins/loader.py`, `src/yoker/builtin/agent.py`,
`src/yoker/ui/commands/agents.py`, `src/yoker/__main__.py`,
`tests/test_agent.py`, `tests/test_agent_loading.py`,
`tests/test_commands/test_agents.py`, `tests/test_tools/test_agent.py`,
`tests/test_config/test_discover_config.py`, `tests/test_main.py`.
**Files Created**: `tests/test_session/test_spawn.py`.

**Verification**: `make check` green — 1501 tests pass, ruff format/lint
clean, mypy typecheck clean, 80% coverage.

### MBI-007 Phase 1: Session Foundation (2026-07-04)

**Task**: Introduced the `Session` construct foundation — a team-of-agents
coordinator that will take over spawning, lifecycle, registry, recursion
depth, event aggregation, and inter-agent messaging (see
`analysis/session-concept-analysis.md`). Phase 1 lands the config section,
the module skeleton, and the lifecycle primitives.

**Changes**:

1. `src/yoker/config/__init__.py` — added `SessionConfig` frozen dataclass
   (`max_agents=10`, `default_isolation_policy="fresh"`,
   `event_aggregation=True`) with `validate_positive_int` and
   `validate_choice` validation; added `session: SessionConfig` field to
   `Config` (Clevis auto-generates `--session-*` CLI args; old TOML files
   without `[session]` load unchanged — strict superset). Exported from
   `__all__`.
2. `src/yoker/events/types.py` — added session lifecycle event types
   (`SESSION_START`, `SESSION_END`, `AGENT_SPAWNED`, `AGENT_FINISHED`,
   `AGENT_MESSAGE`) and matching frozen dataclasses
   (`SessionStartEvent`, `SessionEndEvent`, `AgentSpawnedEvent`,
   `AgentFinishedEvent`, `AgentMessageEvent`). Updated
   `events/__init__.py` exports and `events/recorder.py`
   serialize/deserialize for the new types.
3. `src/yoker/session/` — new package:
   - `message.py`: `Message` frozen dataclass
     (`from_`, `to`, `content`, `metadata`) — plain-string content (D3).
     Note: the design spec uses `from` which is a Python keyword, so the
     field is named `from_` (standard Python convention).
   - `session.py`: `Session` class — async context manager (`__aenter__`/
     `__aexit__`) emitting `SESSION_START`/`SESSION_END`; UUID-based
     session id (overridable via `session_id=`); `add_event_handler` /
     `remove_event_handler`; `get_agent(name)` lookup;
     `_generate_agent_name(definition_name)` disambiguates duplicate
     spawns as `researcher`, `researcher-2`, ... (D2); outstanding spawned
     tasks cancelled on `__aexit__`; `max_recursion_depth` property reads
     `config.tools.agent.max_recursion_depth` (task 7.6.3 — field location
     unchanged, only the consumer moves from Agent to Session). Internal
     state (`_agents_map`, `_agent_registry`, `_recursion_depths`,
     `_backends`, `_tasks`) is in place for Phases 2-5.
     **Update (Batch 2.3):** `max_recursion_depth` was removed from both
     `AgentToolConfig` and `PermissionsConfig` — the field had no production
     reader (Session enforces only `session.max_agents`); the
     `max_recursion_depth` property no longer exists.
   - `__init__.py`: exports `Session`, `Message`.
4. `tests/test_session/` — new test package: `test_config.py` (10 tests),
   `test_message.py` (7 tests), `test_session.py` (18 tests).
5. `tests/test_events.py` — updated `test_event_type_count` to include
   the 5 new session event types.

**Decisions applied**: D1 (container+coordinator), D2 (name disambiguation),
D3 (Message plain-string), D4 (async context manager), D7 (`[session]`
config), D10 (registry will move to Session — field reserved). No
backward-compat shims (Clarification 1) — Phase 1 only adds; removals
land in Phase 2.

**Files Modified**: `src/yoker/config/__init__.py`,
`src/yoker/events/types.py`, `src/yoker/events/__init__.py`,
`src/yoker/events/recorder.py`, `tests/test_events.py`.
**Files Created**: `src/yoker/session/__init__.py`,
`src/yoker/session/message.py`, `src/yoker/session/session.py`,
`tests/test_session/__init__.py`, `tests/test_session/test_config.py`,
`tests/test_session/test_message.py`, `tests/test_session/test_session.py`.

**Verification**: `make check` green — 1498 tests pass, ruff lint clean,
mypy typecheck clean.

### CI Discrepancy Fix (2026-06-30)

**Issue**: Local `make check` passed but CI type checking failed.

**Root Cause**: The `Makefile` used `mypy --strict` while CI used plain `mypy`. Due to a mypy quirk, the `--strict` flag doesn't properly detect certain unused type ignore comments, even though it's supposed to enable `--warn-unused-ignores`.

**Solution**: 
1. Removed `--strict` flag from `Makefile` typecheck target
2. Fixed unnecessary `type: ignore[attr-defined]` comment in `litellm.py`
3. Both local and CI now use plain `mypy` with strict settings from `pyproject.toml`

**Why this matters**: The `pyproject.toml` already configures comprehensive strict type checking (`warn_unused_ignores = true`, `disallow_untyped_defs`, etc.). Using plain `mypy` with this config:
- Aligns local and CI behavior
- Avoids the mypy quirk with `--strict` flag
- Keeps configuration centralized in `pyproject.toml`

**Files Modified**:
- `Makefile` - Removed `--strict` from typecheck target
- `src/yoker/backends/litellm.py` - Removed unnecessary type ignore comment

### Tool Call Arguments Format Fix (2026-06-30)

**Issue**: Different LLM providers expect different formats for tool call `arguments`:
- **Ollama SDK**: expects `arguments` as `dict`
- **LiteLLM (OpenAI/Gemini)**: expects `arguments` as JSON `string`

**Problem**: The conversion was happening in `ContextManager.add_tool_calls()`, which meant all backends received the same format. This broke Ollama which expects `dict` format.

**Solution**: Separation of concerns:
- **Context layer**: Stores tool calls with `arguments` as `dict` (provider-agnostic)
- **Backend layer**: Converts to provider-specific format before sending to provider

**Changes**:

1. `src/yoker/context/manager.py`:
   - Removed argument conversion logic from `add_tool_calls()`
   - Tool calls are now stored exactly as received (with `arguments` as `dict`)

2. `src/yoker/backends/litellm.py`:
   - Added conversion logic at start of `chat_stream()` method
   - Converts `arguments` from `dict` to JSON string before passing to `litellm.acompletion()`

**Architecture**:

```
┌─────────────────────┐
│   Context Layer     │
│  (provider-agnostic)│
│  arguments: dict    │
└─────────────────────┘
          │
          ├──────────────────┐
          │                  │
          ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│  OllamaBackend  │  │ LitellmBackend  │
│   (no change)   │  │   (converts)    │
│ arguments: dict │  │ arguments: str  │
└─────────────────┘  └─────────────────┘
          │                  │
          ▼                  ▼
    Ollama SDK          LiteLLM/OpenAI
```

**Files Modified**:
- `src/yoker/context/manager.py` - Reverted conversion logic
- `src/yoker/backends/litellm.py` - Added conversion logic
- `tests/test_context.py` - Updated test expectations
- `tests/backends/test_litellm.py` - Added conversion test

### Phase 2: Simplified LitellmBackend Architecture (2026-06-29)

**Task**: Rewrote LitellmBackend with simplified design.

#### Design Changes

1. **Provider configs are plain dataclasses** - No `params` property on `OpenAIConfig`, `AnthropicConfig`, or `OllamaConfig`
2. **`BackendConfig.params` property** - Single place that flattens provider config using `dataclasses.asdict()`
3. **LitellmBackend simplification** - Uses `config.backend.params` directly, applies litellm-specific transforms
4. **OllamaBackend unchanged** - Continues to read config directly, not via params

#### Key Implementation

```python
# BackendConfig.params - the ONLY place that flattens
@property
def params(self) -> dict[str, Any]:
    """Flatten provider-specific config to dict."""
    sub_config: OllamaConfig | OpenAIConfig | AnthropicConfig | None = None

    if self.provider == "ollama" and self.ollama is not None:
        sub_config = self.ollama
    elif self.provider == "openai" and self.openai is not None:
        sub_config = self.openai
    elif self.provider == "anthropic" and self.anthropic is not None:
        sub_config = self.anthropic

    if sub_config is None:
        return {}

    d = asdict(sub_config)
    return {k: v for k, v in d.items() if v is not None}

# LitellmBackend - simplified implementation
async def chat_stream(...):
    params = self.config.backend.params.copy()

    # litellm-specific transforms
    litellm_model = f"{self._provider}/{model}"
    if "base_url" in params:
        params["api_base"] = params.pop("base_url")

    response = await litellm.acompletion(
        model=litellm_model,
        messages=messages,
        **params,
    )
```

#### Files Modified

- `src/yoker/config/__init__.py` - Added `params` property to `BackendConfig`
- `src/yoker/backends/litellm.py` - Simplified to use `config.backend.params`
- `tests/test_config/test_multi_provider.py` - Added `BackendConfig.params` tests
- `tests/backends/test_litellm.py` - Updated for simplified design

### Phase 1: Multi-Provider Backend Architecture (2026-06-29)

**Task 6.1**: Created `backends/` package with foundational types and Protocol.

#### Package Structure

```
src/yoker/backends/
├── __init__.py          # Public exports: ModelBackend, ChatChunk, ChatChunkEvent, ToolCallDelta, UsageStats
└── protocol.py          # ModelBackend Protocol + ChatChunk + supporting types
```

#### Key Components

1. **ModelBackend Protocol**: Provider-neutral streaming chat backend interface
   - Async `chat_stream()` method yields `ChatChunk` instances
   - `provider` property returns backend identifier
   - Designed for delta-style (Ollama/OpenAI) and block-style (Anthropic) streaming

2. **ChatChunk**: Frozen dataclass representing streaming events
   - One-of semantics: each chunk is primarily one kind (text, tool_call, or usage)
   - `event` field (ChatChunkEvent) determines chunk type
   - Optional fields: `index`, `text`, `tool_call`, `usage`

3. **ChatChunkEvent**: Enum of all event types
   - Content events: `CONTENT_START`, `CONTENT_DELTA`, `CONTENT_STOP`
   - Thinking events: `THINKING_START`, `THINKING_DELTA`, `THINKING_STOP`
   - Tool events: `TOOL_CALL_START`, `TOOL_CALL_DELTA`, `TOOL_CALL_STOP`
   - Stats events: `USAGE`, `DONE`

4. **ToolCallDelta**: Incremental tool-call fragment
   - `index`, `id`, `name`, `arguments_delta` fields
   - Supports both delta-style (OpenAI/Ollama) and block-style (Anthropic) streaming

5. **UsageStats**: Token/duration statistics
   - Ollama-native fields: `prompt_eval_count`, `eval_count`, `total_duration_ms`
   - Generic fields: `input_tokens`, `output_tokens`
   - All fields optional with `None` defaults

#### Design Decisions

- **Frozen dataclasses**: Immutable types prevent accidental mutation
- **Protocol-based interface**: Structural subtyping for backends
- **Provider-agnostic types**: Single `ChatChunk` type serves all providers
- **Backward compatibility**: Ollama-native stats preserved as first-class fields

#### Tests

- `tests/test_backends/test_protocol.py`: 14 tests covering all types
- Tests verify frozen behavior, imports, defaults, and Protocol structure

## Architecture

### Backend Layer

The `backends/` package provides a clean abstraction layer between the agent and LLM providers:

```
Agent → ModelBackend Protocol → Backend Implementation → Provider SDK
                                                    ├─ OllamaBackend (native SDK)
                                                    └─ LitellmBackend (OpenAI, Anthropic, Gemini, 100+)
```

### Event Flow

```
Backend.chat_stream() → ChatChunk → Agent._consume_stream() → Event → UIBridge
```

The Agent consumes provider-neutral `ChatChunk` instances and translates them into existing `Event` types (`ThinkingStartEvent`, `ContentChunkEvent`, `ToolCallEvent`, `TurnEndEvent`, etc.).

## Conventions

### Code Style

- **Two-space indentation** in all file types
- **Fully qualified imports**: `from yoker.backends.protocol import ChatChunk`
- **Type annotations**: Full type hints with strict mypy checking
- **Docstrings**: Comprehensive docstrings for all public types

### Testing

- **pytest** with descriptive test names
- **Frozen dataclasses**: Verify immutability with `pytest.raises(AttributeError)`
- **Protocol compliance**: Verify interface structure with minimal mock implementations

### Module Organization

- `__init__.py`: Public API exports with `__all__`
- `protocol.py`: Core types and Protocol definitions
- `factory.py`: Backend factory (Phase 1 task 6.4)
- `<provider>.py`: Backend implementations (Phase 1 task 6.5, Phase 2, Phase 3)

## Current State

The multi-provider backend architecture is complete:

- **Phase 1** (Protocol & OllamaBackend): `ModelBackend` Protocol, `ChatChunk`,
  `UsageStats`, `create_backend()` factory, and `OllamaBackend` (native SDK
  adapter) are all implemented.
- **Phase 2** (LiteLLM backend): `LitellmBackend` unifies OpenAI, Anthropic,
  Gemini, and 100+ providers. Provider configs (`OllamaConfig`, `OpenAIConfig`,
  `AnthropicConfig`, `GeminiConfig`, `GenericConfig`) are plain dataclasses.
  `BackendConfig.params` flattens the active provider config. Tool call argument
  format conversion (dict vs JSON string) is handled per-backend.
- **Bootstrap wizard**: Interactive first-run setup with provider selection,
  curated model lists, masked API key input, and `chmod 600` config files.

### Planned

- **Keyring integration** (TODO S.1): Store API keys in the OS keychain instead
  of config files, with fallback to config.
- **MBI-003 (Python API)** — now unblocked: builds a `yoker.session()`
  facade over the real `Session` construct (see
  `analysis/mbi-003-python-api-design.md`).
- Tool timing metrics, token usage tracking, tool result caching, and
  parallel tool execution.


