# Yoker Project Guide

This document captures project conventions and the current architecture after the UI separation migration (Phases 1-8 complete).

Also read:
- [NOTES.md](NOTES.md) — Project-level context and strategic information (positioning, USP, decisions)

## Conventions

- **Indentation**: Two spaces in all file types.
- **Package manager**: `uv` (see `Makefile` for standard targets).
- **Code quality**: `make check` runs format, lint, typecheck, and test.
- **Entry point**: `python -m yoker` is the application entry point.
- **Version source of truth**: `src/yoker/__init__.py` must match `pyproject.toml`.

## Module Structure

```text
src/yoker/
├── __init__.py              # Public API exports: process, run_sync, agent, session,
│                           #   Agent, Session, Config, do, ThinkingLiteral
├── __main__.py              # CLI entry point and run_session()
├── api.py                   # Thin Pythonic API (MBI-003, single-module facade):
│                           #   process(), do(), agent(), session(), run_sync(),
│                           #   ThinkingLiteral (no private helpers)
├── exceptions.py            # Exception hierarchy (incl. NetworkError, ValidationError)
├── logging.py               # Structured logging (structlog)
├── resources.py             # Resource location and reading for definition files
│                           #   (skills, agents) across filesystem and package dirs
├── schema.py                # NameSpaced base class for namespaced dataclasses
├── py.typed                 # PEP 561 typed-package marker
├── cli/                     # CLI subcommand config classes + shared helpers (MBI-004)
├── logging.py               # Structured logging (structlog)
├── resources.py             # Resource location and reading for definition files
│                           #   (skills, agents) across filesystem and package dirs
├── schema.py                # NameSpaced base class for namespaced dataclasses
├── py.typed                 # PEP 561 typed-package marker
├── cli/                     # CLI subcommand config classes + handlers (MBI-004)
│   ├── __init__.py          # Exports: ChatConfig, RunConfig, LoopConfig, InspectConfig,
│   │                        #   InitConfig, ConfigCmdConfig, ContainerConfig, load_subcommand_config
│   ├── commands.py          # @configclass(cmd=...) subcommand configs registered with Clevis;
│   │                        #   config-backed (chat/run/loop/config extend Config) vs standalone
│   │                        #   (inspect/init/container)
│   ├── shared.py            # load_subcommand_config() + load_subcommand_config_with_manifest()
│   │                        #   + dev/test SecurityConfig bypass
│   ├── chat.py              # yoker chat: run_chat() — interactive REPL (default subcommand)
│   ├── run.py               # yoker run: run_run() — load source + trust gate + non-interactive
│   ├── config_cmd.py        # yoker config: run_config_cmd() — display effective config
│   ├── init.py              # yoker init: run_init() — generate default config
│   └── sources.py           # resolve_source() + load_source() — two-phase source resolution
├── core/                    # Agent layer (no UI, no Session coupling)
│   ├── __init__.py          # Unified Agent class (Session-agnostic; on_event, do())
│   ├── _processing.py       # Message processing, streaming, tool loop
│   ├── _setup.py            # Client, guardrail, registry setup
│   └── thinking.py          # Thinking mode enum
├── agents/                  # Agent definition parsing (schema, loader, registry)
│   ├── __init__.py          # Exports: AgentDefinition, AgentRegistry, loaders, validators
│   ├── schema.py            # AgentDefinition frozen dataclasses (from Markdown+frontmatter)
│   ├── loader.py            # Parse Markdown+YAML frontmatter; load from dirs/packages
│   ├── registry.py          # AgentRegistry (UserDict keyed by namespaced name)
│   └── validator.py         # validate_agent_definition against config constraints
├── backends/                # Provider-neutral backend layer
│   ├── __init__.py          # Backend exports + create_backend() dispatch
│   ├── protocol.py          # ModelBackend Protocol, ChatChunk, UsageStats
│   ├── factory.py           # create_backend() dispatch from Config
│   ├── ollama.py            # OllamaBackend (native SDK)
│   ├── litellm.py           # LitellmBackend (OpenAI, Anthropic, Gemini, 100+)
│   └── trust.py             # Custom base URL trust validation
├── bootstrap/               # First-run bootstrap wizard
│   ├── __init__.py          # Wizard package exports
│   ├── wizard.py            # Wizard orchestration
│   ├── steps.py             # Provider-specific setup steps
│   ├── providers.py         # Curated model lists and provider metadata
│   ├── detect.py            # Existing-config detection
│   └── modellist.py         # Model list rendering
├── builtin/                 # Built-in tools registered via the yoker plugin manifest
│   ├── __init__.py          # __YOKER_MANIFEST__ declaring read, write, git, websearch, ...
│   ├── read.py              # read: file contents
│   ├── write.py             # write: file contents
│   ├── update.py            # update: edit existing file contents
│   ├── list.py              # list: directory contents
│   ├── mkdir.py             # mkdir: create directories
│   ├── existence.py         # existence: check files/folders exist
│   ├── search.py            # search: file and content search
│   ├── git.py               # git: Git operations
│   ├── make.py              # make: Makefile target execution
│   ├── webfetch.py          # webfetch: fetch web content through a backend
│   ├── websearch.py         # websearch: search the web through a backend
│   └── skill.py             # make_skill_tool factory (skill invocation tool)
├── config/                  # Configuration system (Clevis)
│   ├── __init__.py          # Config dataclasses, get_yoker_config()
│   ├── providers.py         # Provider configs (Ollama, OpenAI, Anthropic, Gemini, Generic)
│   ├── validators.py        # Field validators
│   └── writer.py            # TOML writer with chmod 600
├── context/                 # Context managers (Protocol-based)
│   ├── __init__.py          # Exports: ContextManager, BaseContextManager, SimpleContextManager,
│   │                        #   ContextManagerWrapper, Persisted, ContextStatistics, SessionMetadata,
│   │                        #   DEFAULT_STORAGE_PATH, list_sessions, load_session_metadata
│   ├── protocol.py          # ContextManager @runtime_checkable Protocol
│   ├── manager.py           # BaseContextManager (in-memory base, self._messages)
│   ├── basic.py             # SimpleContextManager (env reminder + system prompt)
│   ├── wrapper.py           # ContextManagerWrapper (pure proxy, forwards to wrapped)
│   ├── persisted.py         # Persisted (JSONL persistence via bulk-rewrite)
│   ├── factory.py           # Context manager factory — agent-scoped construction from Config
│   ├── interface.py         # ContextStatistics, SessionMetadata dataclasses
│   ├── session.py           # list_sessions, load_session_metadata (JSONL utilities)
│   └── validator.py         # validate_session_id, validate_storage_path, is_safe_path
├── events/                  # Event types and serialization
│   ├── __init__.py          # Exports: Event types, EventRecorder, serialize/deserialize_event
│   ├── types.py             # Event dataclasses (Message, Tool, Error, Stats, ...)
│   ├── session_event.py     # SessionEvent envelope tagging an Event with its agent_id
│   └── recorder.py          # EventRecorder, serialize_event, deserialize_event (JSONL)
├── plugins/                 # Plugin system (discover, manifest, trust)
│   ├── __init__.py          # Plugin package exports
│   ├── loader.py            # Plugin package discovery via __YOKER_MANIFEST__
│   ├── manifest.py          # PluginManifest dataclass (tools, skills, agents declarations,
│                           #   agent/prompt convenience fields for yoker run)
│   ├── file_manifest.py     # File-based manifest (agent.toml): load_file_manifest() parses
│                           #   [run]/[plugin] sections + config overrides; does NOT import
│                           #   tools_module (deferred to loader after trust gate)
│   └── security.py          # Plugin trust checks (global opt-in + per-plugin trust table)
├── skills/                  # Skill definitions and registry
│   ├── __init__.py          # Exports: Skill, SkillRegistry, loaders, injection helpers
│   ├── schema.py            # Skill dataclass (from Markdown+frontmatter)
│   ├── loader.py            # Parse Markdown+YAML frontmatter into Skill objects
│   ├── registry.py          # SkillRegistry: lookup skills by name
│   └── injection.py         # Skill discovery + invocation context blocks
├── tools/                   # Tool framework
│   ├── __init__.py          # Tool framework exports (registry, annotations, guardrails, ...)
│   ├── annotations.py       # Path, Url, Query, Text markers + @tool decorator
│   ├── schema.py            # ToolSpec, build_tool_spec() (function→tool introspection)
│   ├── registry.py          # ToolRegistry (UserDict of ToolSpec)
│   ├── context.py           # Tool execution context (config/backends without exposing Agent)
│   ├── content_type.py      # Content type detection from file content and path extension
│   ├── guardrails/          # Guardrail framework
│   │   ├── __init__.py      # Guardrail abstract base class
│   │   ├── env.py           # EnvGuardrail (env var allowlist + hard denylist + value validation)
│   │   └── path.py          # PathGuardrail (traversal, size, extension checks)
│   └── web/                 # Web tool backends and guardrails
│       ├── __init__.py      # Web tool component exports
│       ├── backend.py       # Web search/fetch backend protocol and implementations
│       ├── guardrail.py     # Web guardrail (SSRF, domain allow/deny lists)
│       └── types.py         # SearchResult dataclass, WebSearchError
├── session/                 # Session construct (MBI-007; team-of-agents coordinator)
│   ├── __init__.py          # Session: async context manager owning a team of agents;
│   │                        #   name→agent map, AgentRegistry, shared backends, event
│   │                        #   aggregation; spawn()/_spawn_internal(), release(agent),
│   │                        #   create_primary_agent() -> Agent, agent property,
│   │                        #   send(to=, from_=, content=) accepting Agent instances,
│   │                        #   _id_of(agent) reverse-lookup, inject_tools(), get_backend();
│   │                        #   loads plugin agent defs via register_configured_plugin_agents()
│   └── tools.py             # Session-injected tools: agent + send_message factories
│                            #   (agent tool folds _spawn_internal + child.process + release)
└── ui/                      # UI layer (strictly separated from the Agent layer)
    ├── __init__.py          # Public UI exports
    ├── handler.py           # UIHandler protocol
    ├── bridge.py            # UIBridge: events -> UIHandler method calls
    ├── interactive.py       # InteractiveUIHandler (Rich + prompt_toolkit terminal UI)
    ├── batch.py             # BatchUIHandler (stdin/stdout/stderr for pipelines)
    ├── spinner.py           # LiveDisplay for streaming responses
    └── commands/            # Slash commands (UI layer)
        ├── __init__.py      # Command registry and dispatch
        ├── base.py          # Command base types (Agent + UIHandler received per command)
        ├── help.py          # /help: list registered commands
        ├── agents.py        # /agents: show loaded and known agents
        ├── skills.py        # /skills: list loaded skills
        ├── skill_invoke.py  # /<skill-name>: inject skill context and process follow-up
        ├── tools.py         # /tools: list known tools with availability
        ├── think.py         # /think: toggle or display thinking mode
        ├── context.py       # /context: show session context (id, counts, recent messages)
        └── config.py        # /config: show current config
```

## UI Layer Architecture

The UI layer is strictly separated from the Agent layer.

- **Agent** emits `Event` objects via `Agent.on_event()`.
- **UIBridge** is an event handler that translates events into `UIHandler` method calls.
- **UIHandler** implementations handle all presentation: input, output, streaming, errors.

Built-in handlers:

- `InteractiveUIHandler`: Rich + prompt_toolkit terminal UI.
- `BatchUIHandler`: stdin/stdout/stderr for pipelines and scripts.

### Event Flow

```text
Agent.process() -> Event -> UIBridge -> UIHandler method
```

Session lifecycle is managed by the caller (`__main__.py` or library code), not by the Agent. The Agent has no `begin_session()` or `end_session()` methods and does not emit session events.

## Adding a New UI Handler

1. Implement the `UIHandler` protocol in `src/yoker/ui/<name>.py`.
2. Add the implementation to `src/yoker/ui/__init__.py` exports.
3. Wire the handler in `src/yoker/__main__.py` `_create_ui()` if it should be selectable via `--ui-mode`.
4. Add an example under `examples/` showing usage.
5. Update this document and `README.md`.

## CLI Arguments

CLI arguments are auto-generated by Clevis from the `Config` dataclass. Common UI-related flags:

- `--ui-mode {interactive,batch}`
- `--ui-show-thinking`
- `--ui-show-tool-calls`
- `--ui-show-stats`
- `--agents-definition PATH`

## Current State

- MBI-004 CLI subcommands (tasks 4.1-4.7) in progress: `__main__.py` dispatches via Clevis `@configclass(cmd=...)` subcommand config classes in `yoker/cli/commands.py` and `get_cmd()`. Seven subcommands registered: `chat` (default, working end-to-end), `run` (working end-to-end), `init`, `config` (working), and `loop`, `inspect`, `container` (stubs printing "not yet implemented"). When no subcommand is given, Clevis's `default_cmd=True` on `ChatConfig` automatically routes to `chat` (native Clevis 0.7.0 feature — no `sys.argv` patching needed). Config-backed subcommands extend `Config`; standalone subcommands (`inspect`, `init`, `container`) have only their own fields. `--with` plugin stripping and the bootstrap pre-flight check stay in `__main__.py` (bootstrap for `chat` only). Per-subcommand handlers live in `yoker/cli/<name>.py`.
- MBI-004 `yoker run` (task 4.7) complete: `yoker/cli/run.py` implements the flagship `yoker run <source>` command. Flow: resolve_source (phase 1) → --dry-run → trust gate (`check_source_allowed` in `plugins/security.py`) → load_source (phase 2, AFTER trust) → apply manifest config overrides → resolve agent + prompt (CLI --agent/--prompt > manifest) → prompt length cap (10 KB) → Session + Agent + process → cleanup. The trust gate is a SECURITY INVARIANT — `load_source()` is never called before `check_source_allowed()` returns True. Non-interactive mode rejects untrusted sources by default (`YOKER_TRUST_SOURCE=1` env var overrides). `--persist`/`--session-id` control session persistence. Source agent definitions override built-ins on conflict (owner-confirmed).
- MBI-004 Extended Manifest (task 4.5) complete: the manifest is a generic config-override layer (not additive fields). `PluginManifest` gained convenience `agent`/`prompt` fields (default `None`, backward compatible) for Python packages without `agent.toml`. `yoker/plugins/file_manifest.py` parses `agent.toml` (filename chosen to avoid collision with project `yoker.toml`) into `FileManifestResult(run_config, plugin_config, config_overrides)` — the parser only parses TOML (using Clevis 0.7.0's public `clevis.load` loader), does NOT import `tools_module` (deferred to the loader after the trust gate). `yoker/config/get_yoker_config_with_manifest(manifest_path, cli)` implements the cascade: base TOML (user + project) → manifest overrides → CLI args, returning `(Config, RunConfig, PluginConfig)`. Uses Clevis 0.7.0's public cascade API (`build_default_cascade` + manifest provider + `get_config(cascade=...)`); no Clevis internals or `type: ignore` comments. `yoker/cli/shared.py`'s `load_subcommand_config_with_manifest()` uses Clevis 0.7.0's public helpers (`check_file_permissions`, `check_directory_permissions`, `load_toml_from_fd`, `deep_merge`) and `dacite.from_dict` directly. Test isolation note: `get_yoker_config_with_manifest(cli=True)` calls `get_factory(Config)` which registers Config on clevis's shared default parser (Config has no `cmd`, so its args land on the root parser alongside the subparser group from task 4.1); tests reset clevis global state and re-register subcommand configs via `reload(yoker.cli.commands)` in teardown.
- UI Separation migration: Phases 1-8 complete.
- MBI-003 Python API reduced to a thin single-module facade (`yoker/api.py`): `yoker.agent` is the factory function (builder → customised Config → Agent); `yoker.process` / `yoker.do` are one-shot helpers built on `yoker.agent`; `yoker.session` is an async context manager yielding the real `yoker.session.Session` (no facade class). `yoker/api/_internal.py`, `yoker/api/one_shot.py`, `yoker/api/session.py`, and the `ApiSession` facade class removed. No private helpers remain in `api.py`.
- Public Python API surface (in `yoker/__init__.py`): `Agent`, `Session`, `Config`, `process`, `do`, `agent`, `session`, `run_sync`, `ThinkingLiteral` (plus the existing context/event/exception exports). Removed: `ApiSession`, `make_config`, `Message`, `EventReplayAgent`, `ThinkingMode`, `EventRecorder`, `serialize_event`/`deserialize_event` (still importable from submodules), logging utilities, `BaseContextManager`/`ContextManagerWrapper`/`ContextStatistics`.
- Thin wrappers: `yoker.process(prompt, **kwargs)`, `yoker.do(skill_name, prompt, args="", **kwargs)`, `yoker.agent(**kwargs) -> Agent` (reusable; call `agent.process(prompt)` or `agent.do(skill_name, prompt, args="")`), `yoker.session(id=..., *, persist=True, fresh=False, **kwargs) -> AsyncContextManager[Session]` (yields the real Session; use `session.agent.process(...)`).
- Single sync helper: `yoker.run_sync(coro)` wraps `asyncio.run` — dropped per-function `*_sync` wrappers.
- `SpawnResult` removed entirely: the `agent` tool folds `Session._spawn_internal(name, requester=)` + `child.process(prompt)` (with `asyncio.wait_for` timeout) + `session.release(child)` inline, and renders `agent_id: <id>\n\n<response>` (no `_render_spawn_result` helper, no `_spawn_and_run` method).
- `Agent` no longer carries a `_session_id` attribute. `Session.send(*, to, from_, content)` resolves `Agent` instances back to ids via `Session._id_of(agent)` reverse-lookup against the active map. `Session.release(agent)` removes by identity (single cleanup path). `Session.agent` read-only property backed by `Session.create_primary_agent()`, which resolves the definition, constructs the `Agent` with the session-shared backend, and registers it.
- `Session.create_primary_agent(name=None, *, config, agent_definition, agent_path, plugins, thinking_mode, console_logging) -> Agent` is the single end-to-end path for creating the primary agent. `__main__.py` and `yoker.session()` both use it. `register_primary_agent` removed (absorbed into `create_primary_agent` + internal `_register_primary`).
- `Agent.on_event(handler)` is the single event-handler registration method (no `add_event_handler`/`remove_event_handler`/`get_event_handlers`). `Session.on_event(handler)` is the session-scoped equivalent.
- `Session.send(*, to, from_, content)` accepts `Agent` instances directly (the Python API surface); the `send_message` tool resolves the LLM-facing `agent_id` string references back to `Agent` instances via the active map before calling `send`.
- `Message` dataclass removed: inter-agent messaging is via `Session.send(to=, from_=, content=)` with plain strings.
- `make_config()` removed from `yoker.config`: use `Config()` for programmatic defaults or `get_yoker_config()` for filesystem discovery.
- Plugin agent-definition loading split: standalone `Agent` calls `load_configured_plugins(session=None)` (skips agent defs); `Session` calls `register_configured_plugin_agents(self.agents, config, extra_plugins)` to populate the registry.
- `Agent` is a single unified class in `yoker/core/__init__.py` backed by private helper modules (`_setup.py`, `_processing.py`).
- `AgentCore` and `ProcessingMixin` removed.
- `ConsoleEventHandler` and session lifecycle events removed.
- Slash commands moved to `yoker/ui/commands/`.
- `Agent` is async-only and emits events; UI is fully external.
- All output goes through `UIHandler`.
- Built-in tools are registered via the plugin loader from `yoker.builtin.__YOKER_MANIFEST__` (in `src/yoker/builtin/__init__.py`), which declares all built-in tools (`read`, `write`, `git`, `websearch`, etc.). The loader always loads the yoker builtin plugin (trusted by default). The `agent` (`make_spawn_agent_tool`) and `send_message` (`make_send_message_tool`) tools are session-injected via `yoker/session/tools.py`, and the `skill` tool is added via the `make_skill_tool` factory in `yoker/builtin/skill.py` — each needs runtime dependencies not available to the static manifest.
- Tool framework redesigned: tools are plain functions or callable classes, guardrail metadata comes from `yoker.tools.annotations` markers (`Path`, `Url`, `Query`, `Text`), and `ToolRegistry` stores `ToolSpec` objects built via `yoker.tools.schema.build_tool_spec()`.
- Multi-provider backend architecture: `OllamaBackend` (native SDK) and `LitellmBackend` (OpenAI, Anthropic, Gemini, 100+ providers) behind the `ModelBackend` Protocol.
- Bootstrap wizard (`yoker/bootstrap/`) for interactive first-run setup with curated model lists.
- OLLAMA_API_KEY env var removed; configure `backend.ollama.api_key` instead.

See `analysis/ui-separation-migration.md` for the full migration plan and `README.md` for user-facing documentation.
