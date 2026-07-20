# Changelog

All notable changes to yoker are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## Unreleased

### Changed

- **Default Tools Behavior (M.2, Option C)**: Agent definitions without a
  `tools:` line now grant ALL config-enabled tools at runtime. Previously,
  a missing `tools:` field raised `ConfigurationError` at load time. To get
  "no tools", explicitly set `tools:` (bare), `tools: null`, `tools: ~`,
  `tools: ""`, or `tools: []` in YAML; or pass `tools=None` / `tools=[]` to
  `AgentDefinition()` / `yoker.agent()`. A visible WARN event
  `agent_tools_default_granted` is emitted whenever all-tools is granted by
  omission, so operators can spot agents that silently broadened on upgrade.
  The `ALL_TOOLS` sentinel is a module-level `[]` (empty list) in
  `yoker.agents.schema`, used as the default value of
  `AgentDefinition.tools`. It distinguishes "no `tools` line" (`ALL_TOOLS` —
  all tools) from "tools explicitly empty" (`[]` — no tools) via identity
  (`is ALL_TOOLS`). The sentinel is resolved in exactly ONE place —
  `Agent._filter_tools_by_definition` — which replaces it with the real list
  of all tool names from the registry; everywhere else, `tools` is just a
  list.
- **Validator on runtime path**: `validate_agent_definition` is now called
  during `Agent` construction (warnings only; never blocks). Unknown bare
  tool names and disabled tools produce warnings instead of raising. The
  runtime `_warn_missing_tools` check stays authoritative for tool
  availability.
- **Thin API tools contract aligned with `AgentDefinition` (M.2)**: The
  `yoker.agent()` / `yoker.process()` / `yoker.do()` / `yoker.session()`
  `tools` kwarg now defaults to the `ALL_TOOLS` sentinel (all tools) and is
  passed through UNCHANGED to `AgentDefinition` — the previous api.py bridge
  that translated `tools=None` → `ALL_TOOLS` (all tools) is removed. This
  eliminates the dual contract: `yoker.agent(tools=None)` now means "no
  tools" (matching `AgentDefinition(tools=None)`), not "all tools". Omit the
  arg (or pass `ALL_TOOLS` explicitly) for all tools; `tools=[]` also
  disables all tools; `tools=["read", ...]` filters as before.

### Upgrade Notes

- **Plugins with a missing `tools:` line gain all tools on upgrade.** Add an
  explicit `tools: []` to agent definition files that should have no tools.
  The bundled `examples/plugins/demo/.../backwards.md` already uses
  `tools: []` as a regression guard.

## 0.8.0 (2026-07-15)

### Added

- **CLI Subcommands (MBI-004)**: Seven subcommands registered with Clevis:
  `chat` (default, interactive REPL), `run`, `init`, `config`, `loop`,
  `inspect`, and `container`.
- **Config-override manifest layer**: `agent.toml` support for agentic
  packages, with deep-merge of nested table overrides and TOML array
  replacement for tuple-typed fields.
- **Two-phase source resolution**: `resolve_source()` then `load_source()`
  supports module, folder, GitHub URL, and zip file sources.
- **Security trust gate**: `check_source_allowed()` is a security invariant
  — `load_source()` is never called before the trust gate returns True.
  Non-interactive mode rejects untrusted sources by default
  (`YOKER_TRUST_SOURCE=1` env var overrides).
- **`yoker run <source>`**: Flagship command for running agentic packages,
  with `--dry-run`, `--persist`, and `--session-id` options.
- **`yoker inspect <source>`**: Read-only source report (no trust gate, no
  code execution).
- **`yoker loop <source>`**: Interval-based execution with graceful shutdown.
- **`yoker container <source>`**: Dockerfile/Containerfile generation with
  security hardening.
- **`yoker init`**: Config generation with bootstrap wizard integration.
- **`yoker config`**: Display effective configuration with API key masking.

### Changed

- **Clevis upgraded from 0.3.3 to 0.7.0**: Replaced `sys.argv` patching with
  native Clevis `default_cmd=True`; replaced private Clevis internals with
  the public 0.7.0 API (`clevis.load`, `build_default_cascade`,
  `get_config(cascade=...)`); removed all `TODO(clevis-feature-request)`
  workarounds and `type: ignore[attr-defined]` comments.
- **`dacite` added as explicit dependency**: Was previously transitive
  through Clevis.

### Fixed

- **Windows-specific test failures**: Path and permission assertions now
  pass on Windows.

## 0.7.0 (2026-07-07)

### Added

- **Python API Facade (MBI-003)**: New thin single-module public API in
  `yoker.api` exposing `process`, `do`, `agent`, `session`, `run_sync`, and
  `ThinkingLiteral`. `yoker.agent(**kwargs)` is the reusable factory
  (builder → customised `Config` → `Agent`); `yoker.process` / `yoker.do`
  are one-shot helpers built on it; `yoker.session(...)` is an async context
  manager yielding the real `yoker.session.Session`.
- **Session.send accepts Agent instances**: `Session.send(*, to, from_,
  content)` resolves `Agent` instances back to ids via `_id_of()`; the
  `agent` tool and `send_message` tool fold spawn/process/release inline.
- **Session.create_primary_agent**: Single end-to-end path for creating the
  primary agent, used by both `__main__.py` and `yoker.session()`.
- **Python API examples**: New `examples/python_api/` covering builder,
  one-shot, sync usage, sessions, event handling, skill invocation, and a
  full workflow.
- **Context Manager Factory**: `yoker.context.factory` constructs the
  context manager agent-scoped from `Config`; `Session` owns the lifecycle
  and passes the context manager into `Agent`.
- **Structured Logging at CLI Startup**: CLI wires `structlog` configuration
  at startup.

### Changed

- **Agent package relocated**: `yoker.agent` → `yoker.core` (unified `Agent`
  class backed by `_setup.py` / `_processing.py`).
- **Plugin loader merged**: `yoker.plugins.loader` consolidated;
  registries (`ToolRegistry`, `SkillRegistry`, `AgentRegistry`) now own
  their own plugin registration. `register_tools` / `register_skills` free
  functions removed.
- **API collapsed to a module**: `yoker.api` is now a single module
  (`api.py`), not a package; `_internal`/`one_shot`/`session` submodules
  removed.
- **Config dataclasses unfrozen**: `Config` and provider configs are now
  mutable, eliminating `replace()` workarounds.
- **session() signature explicit**: `yoker.session(id=..., *, persist=True,
  fresh=False, **kwargs)` uses explicit kwargs instead of a kwargs-pop block.
- **Plugins-enabled sanity check**: Moved into `Config` validation;
  `check_plugins_enabled` removed. The plugins-disabled warning is now
  visible and covers CLI `--with` packages too.
- **Clearer session error**: `Session` emits a clear error when a configured
  agent cannot be resolved.

### Removed

- **Public API removals**: `ApiSession`, `make_config`, `Message`,
  `SpawnResult`, `EventReplayAgent`, `ThinkingMode` (public re-export),
  `add_event_handler` / `remove_event_handler` / `get_event_handlers`
  (use `Agent.on_event(handler)`), `max_recursion_depth` config field,
  `load_configured_plugins`, `check_plugins_enabled`,
  `register_tools` / `register_skills` free functions,
  `yoker.plugins.registration` module, `yoker.api` submodules
  (`_internal` / `one_shot` / `session`), `yoker.events.replay`,
  `yoker.session.message`, `yoker.session.spawn_result`.

### Fixed

- **5 code regressions from MBI-003 cleanup**:
  - `Agent.__init__` coerces `plugins=None` to `()` so `load_plugins` never
    receives a non-iterable `None`.
  - `context/factory` sanitizes `agent_id` colons before filename
    interpolation so namespaced ids like `file:researcher` pass
    `validate_session_id`.
  - `Session._derive_config` deep-copies `parent_config` before applying
    model override, leaving the caller's sub-config untouched.
  - `render_config_toml` deep-copies config before applying overrides so
    `_set_dotted` no longer mutates the caller's `Config`.
  - `agents/registry` drops a stray `raise` in `register_config_agents` so
    invalid/malformed agent dirs are warned-and-skipped, not fatal.
- **CLI logging wiring**: Structured logging configured at startup.
- **Stale test mocks**: Fixed 6 stale `yoker.core.Agent` mock targets.

### Documentation

- Refreshed `CLAUDE.md` module structure to match the current tree.
- Refreshed user-facing docs: `README.md`, `docs/quickstart.md`,
  `docs/api/index.md`, `docs/rationale.md`.
- Cleaned up `PLAN.md` and `TODO.md`; added `DEVELOPMENT.md`.
- Updated `MBI-003 Python API` design doc.

## 0.6.0 (2026-07-03)

### Added

- **Multi-Provider Backend System (MBI-006)**: Introduced a `ModelBackend`
  Protocol with `ChatChunk` abstraction, plus `OllamaBackend` and
  `LitellmBackend` adapters. Yoker now supports OpenAI, Anthropic, Gemini,
  and Ollama through a unified backend layer.
- **BackendConfig Tagged Union**: New `BackendConfig` schema with
  provider-specific config classes (`OllamaConfig`, `GenericConfig`,
  `GeminiConfig`, etc.), eliminating provider-specific if-then-else chains
  in config validation.
- **API Key CLI Exclusion**: API keys are now excluded from CLI argument
  rendering to prevent accidental exposure.
- **Token Accounting**: `TurnEndEvent` now carries `input_tokens` and
  `output_tokens` for usage tracking.
- **Bootstrap Wizard (MBI-002)**: Interactive onboarding wizard with
  multi-provider support, curated model selection, ASCII art banner,
  provider display in welcome message, and step-by-step configuration flow.
- **Provider-aware Subagent Spawning**: `Agent.subagent()` now uses the
  parent's backend, keeping spawned agents provider-agnostic.
- **End-user Documentation**: New getting-started guides for Yoker, Ollama,
  and Gemini (with screenshots), plus a comprehensive models reference page.

### Fixed

- **User-Friendly LiteLLM Errors**: LiteLLM exceptions are now caught and
  surfaced as clean messages instead of stack traces.
- **Tool Calling in LitellmBackend**: Corrected tool-calling implementation
  to properly forward tool invocations across providers.
- **Litellm Logging Noise**: Suppressed INFO-level logging from LiteLLM
  across all logger names.
- **Bootstrap Security**: Bootstrap inputs are no longer logged to command
  history (prevents API key leakage in shell history).
- **GeminiConfig Initialization**: Ensured `GeminiConfig` is initialized
  when the Gemini provider is selected during bootstrap.
- **Ollama Web Tools**: Populated `Agent._tool_backends` so Ollama web tools
  work correctly.
- **Windows CI**: Skipped Unix-only assertions (chmod 600, tilde expansion,
  history security tests) on Windows CI runners.
- **Provider Error Display**: Improved error rendering for provider errors
  in the interactive UI.

### Changed

- **Provider Configs Module**: Split provider configs into a dedicated
  `providers` module; added `GenericConfig` for unknown providers.
- **Centralized DEFAULT_BASE_URLS**: Moved default base URLs from
  `LitellmBackend` into the provider config classes.
- **Skills Loading Warning**: Centralized the `skills_dir` not-found warning
  in `load_skills_from_package`.
- **Documentation Refactoring (PR #39)**: Comprehensive documentation review
  with 33 fixes, reorganized screenshots, corrected version references, and
  a new models reference page.

## 0.5.0 (2026-06-26)

### Added

- **UI Separation Migration Complete**: Agent layer is now purely
  event-driven; UI layer owns all presentation.
- **UIHandler Protocol**: Added `UIHandler` protocol with built-in
  `InteractiveUIHandler` and `BatchUIHandler`.
- **UIBridge**: Dispatches agent events to UI handlers without terminal
  logic in the agent.
- **Plugin System**: Load tools, skills, and agents from Python packages
  via `--with <package>`.
- **Plugin Manifest**: Added `__YOKER_MANIFEST__` plugin declaration format.
- **Content Type Detection**: Added content type detection utility
  (`yoker.content_type`).
- **Tool Content Events**: Tools now emit `ToolContentEvent` with
  appropriate MIME types.
- **Slash Commands**: Added `/skills`, `/context`, `/tools`, `/agents`
  commands.
- **Clevis Integration**: Migrated configuration system to Clevis with
  auto-generated CLI arguments.

### Changed

- **Agent Lifecycle**: Removed `Agent.begin_session()` and
  `Agent.end_session()`; agent lifecycle is now create → use → discard.
- **ConsoleEventHandler Removed**: All terminal output is handled by
  `UIHandler` implementations.
- **Agent Refactoring**: Refactored `Agent` into `yoker.agent` package with
  modular components.
- **ContextManager**: Now list-like and extends `UserList`.

### Fixed

- **NetworkError Handling**: Graceful handling of non-recoverable
  `NetworkError` in the CLI session loop.
- **Content Type Detection**: Fixed content type detection fallbacks for
  unknown file types.
- **Tool Parsing**: Tools are now parsed into `ToolSpec` during plugin load
  for consistent architecture.
- **SecurityError Handling**: `clevis.SecurityError` is now caught and
  displays a clean error message.