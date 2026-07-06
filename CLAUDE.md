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
├── __init__.py              # Public API exports
├── __main__.py              # CLI entry point and run_session()
├── agent/                   # Agent layer (no UI)
│   ├── __init__.py          # Unified Agent class
│   ├── _plugins.py          # Plugin loading helpers
│   ├── _processing.py       # Message processing, streaming, tool loop
│   ├── _setup.py            # Client, guardrail, registry setup
│   ├── _tools.py            # Built-in tool filtering
│   └── thinking.py          # Thinking mode enum
├── agents/                  # Agent definition parsing
├── backends/                # Provider-neutral backend layer
│   ├── protocol.py          # ModelBackend Protocol, ChatChunk, UsageStats
│   ├── factory.py           # create_backend() dispatch
│   ├── ollama.py            # OllamaBackend (native SDK)
│   ├── litellm.py           # LitellmBackend (OpenAI, Anthropic, Gemini, 100+)
│   └── trust.py             # Custom base URL trust validation
├── bootstrap/               # First-run bootstrap wizard
│   ├── wizard.py            # Wizard orchestration
│   ├── steps.py             # Provider-specific setup steps
│   ├── providers.py         # Curated model lists and provider metadata
│   ├── detect.py            # Config detection
│   └── modellist.py         # Model list rendering
├── builtin/                 # Built-in tools (read, write, git, websearch, ...)
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
│   ├── interface.py         # ContextStatistics, SessionMetadata dataclasses
│   ├── session.py           # list_sessions, load_session_metadata (JSONL utilities)
│   └── validator.py         # validate_session_id, validate_storage_path, is_safe_path
├── events/                  # Event types and serialization
├── exceptions.py            # Exception hierarchy (incl. NetworkError)
├── logging.py               # Structured logging
├── plugins/                 # Plugin system
│   ├── __init__.py
│   ├── agents.py            # Agent definition loading
│   ├── builtin.py           # Built-in yoker plugin manifest
│   ├── loader.py            # Plugin package discovery
│   ├── manifest.py          # Plugin manifest dataclass
│   ├── registration.py      # Component registration
│   ├── resources.py         # Package resource helpers
│   ├── security.py          # Plugin trust checks
│   ├── skills.py            # Plugin skill discovery
│   └── urls.py              # plugin:// URL parsing
├── schema.py                # NameSpaced base class
├── skills/                  # Skill definitions and registry
├── tools/                   # Tool framework
│   ├── annotations.py       # Path, Url, Query, Text markers + @tool decorator
│   ├── schema.py            # ToolSpec, build_tool_spec()
│   ├── registry.py          # ToolRegistry
│   ├── guardrails/          # PathGuardrail, WebGuardrail
│   └── web/                 # Web tool backends
├── session/                 # Session construct (MBI-007; team-of-agents coordinator)
│   ├── __init__.py          # Exports Session, Message, SpawnResult
│   ├── message.py           # Message frozen dataclass (inter-agent, plain-string content)
│   ├── session.py           # Session: async context manager, lifecycle, name→agent map,
│   │                        #   spawn(), send(), inject_tools(), register_primary_agent()
│   ├── spawn_result.py      # SpawnResult(agent_id, response) — return of Session.spawn
│   └── tools.py             # Session-injected tools: SpawnAgent, SendMessage factories
└── ui/                      # UI layer
    ├── __init__.py          # Public UI exports
    ├── handler.py           # UIHandler protocol
    ├── bridge.py            # UIBridge: events -> UIHandler
    ├── interactive.py       # InteractiveUIHandler
    ├── batch.py             # BatchUIHandler
    ├── spinner.py           # LiveDisplay for streaming
    └── commands/            # Slash commands (UI layer)
```

## UI Layer Architecture

The UI layer is strictly separated from the Agent layer.

- **Agent** emits `Event` objects via `Agent.add_event_handler()`.
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

- UI Separation migration: Phases 1-8 complete.
- `Agent` is a single unified class in `yoker/agent/__init__.py` backed by private helper modules (`_setup.py`, `_processing.py`, `_plugins.py`, `_tools.py`).
- `AgentCore` and `ProcessingMixin` removed.
- `ConsoleEventHandler` and session lifecycle events removed.
- Slash commands moved to `yoker/ui/commands/`.
- `Agent` is async-only and emits events; UI is fully external.
- All output goes through `UIHandler`.
- Built-in tools are registered via the plugin loader from `yoker.builtin.__YOKER_MANIFEST__` (in `src/yoker/builtin/__init__.py`), which declares all built-in tools (`read`, `write`, `git`, `websearch`, etc.). The loader always loads the yoker builtin plugin (trusted by default). The `agent` and `skill` tools are added separately via `make_agent_tool` / `make_skill_tool` factories because they need runtime dependencies.
- Tool framework redesigned: tools are plain functions or callable classes, guardrail metadata comes from `yoker.tools.annotations` markers (`Path`, `Url`, `Query`, `Text`), and `ToolRegistry` stores `ToolSpec` objects built via `yoker.tools.schema.build_tool_spec()`.
- Multi-provider backend architecture: `OllamaBackend` (native SDK) and `LitellmBackend` (OpenAI, Anthropic, Gemini, 100+ providers) behind the `ModelBackend` Protocol.
- Bootstrap wizard (`yoker/bootstrap/`) for interactive first-run setup with curated model lists.
- OLLAMA_API_KEY env var removed; configure `backend.ollama.api_key` instead.

See `analysis/ui-separation-migration.md` for the full migration plan and `README.md` for user-facing documentation.
