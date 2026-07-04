# Yoker Development Guide

This document provides an overview of the project architecture, conventions, and recent changes for development purposes.

## Project Overview

Yoker is a Python agent harness with configurable tools and guardrails. It provides a provider-neutral backend architecture for LLM interactions, supporting Ollama (native SDK), OpenAI, Anthropic, Google Gemini, and 100+ providers via LiteLLM.

## Recent Changes

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
- Multi-agent orchestration, tool timing metrics, token usage tracking, tool
  result caching, and parallel tool execution.


