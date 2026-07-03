# Yoker Development Guide

This document provides an overview of the project architecture, conventions, and recent changes for development purposes.

## Project Overview

Yoker is a Python agent harness with configurable tools and guardrails. It provides a provider-neutral backend architecture for LLM interactions, supporting Ollama (native SDK), OpenAI, Anthropic, Google Gemini, and 100+ providers via LiteLLM.

## Recent Changes

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


