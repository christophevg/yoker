# Task 6.1 Implementation Summary

**Task**: Create the `backends/` package with `ModelBackend` Protocol and `ChatChunk`/`UsageStats` types

**Branch**: `feature/mbi-006-phase1-backend-protocol`

**Date**: 2026-06-29

## What was implemented

### Package Structure

Created `src/yoker/backends/` package with:

1. **`protocol.py`**: Core types and Protocol definition
   - `ModelBackend` Protocol - provider-neutral streaming chat backend interface
   - `ChatChunk` frozen dataclass - neutral streaming chunk type
   - `ChatChunkEvent` enum - all event types (content, thinking, tool_call, usage, done)
   - `ToolCallDelta` frozen dataclass - incremental tool-call fragment
   - `UsageStats` frozen dataclass - token/duration statistics

2. **`__init__.py`**: Public API exports
   - Exports: `ModelBackend`, `ChatChunk`, `ChatChunkEvent`, `ToolCallDelta`, `UsageStats`

### Key Design Features

- **Provider-agnostic types**: Single `ChatChunk` type serves all providers (Ollama, OpenAI, Anthropic)
- **One-of semantics**: Each chunk is primarily one kind (text, tool_call, or usage)
- **Ollama-native fields preserved**: `UsageStats` includes `prompt_eval_count`, `eval_count`, `total_duration_ms`
- **Generic fields**: `UsageStats` also includes `input_tokens`, `output_tokens` for OpenAI/Anthropic
- **Frozen dataclasses**: All types immutable to prevent accidental mutation
- **Protocol-based interface**: Structural subtyping for backends
- **Async-first design**: `ModelBackend.chat_stream()` is an async generator

### Type Details

**ChatChunkEvent** (enum):
- `CONTENT_START`, `CONTENT_DELTA`, `CONTENT_STOP` - text streaming
- `THINKING_START`, `THINKING_DELTA`, `THINKING_STOP` - reasoning blocks
- `TOOL_CALL_START`, `TOOL_CALL_DELTA`, `TOOL_CALL_STOP` - tool execution
- `USAGE` - stats available
- `DONE` - stream complete

**ChatChunk** (frozen dataclass):
- `event: ChatChunkEvent` - required
- `index: int | None` - block index for Anthropic
- `text: str | None` - text delta
- `tool_call: ToolCallDelta | None` - tool call fragment
- `usage: UsageStats | None` - usage statistics

**ToolCallDelta** (frozen dataclass):
- `index: int` - required
- `id: str | None` - tool call ID
- `name: str | None` - tool name
- `arguments_delta: str | None` - JSON arguments fragment

**UsageStats** (frozen dataclass):
- `input_tokens: int | None` - OpenAI/Anthropic
- `output_tokens: int | None` - OpenAI/Anthropic
- `prompt_eval_count: int | None` - Ollama native
- `eval_count: int | None` - Ollama native
- `total_duration_ms: int | None` - Ollama native

**ModelBackend** (Protocol):
- `provider: str` property - backend identifier
- `chat_stream(*, model, messages, tools, think, **kwargs)` - async generator yielding ChatChunk

## Files Created

```
src/yoker/backends/
├── __init__.py          (29 lines)
└── protocol.py          (129 lines)

tests/test_backends/
├── __init__.py          (1 line)
└── test_protocol.py     (213 lines)

reporting/mbi-006-phase1-backend-protocol/
└── development-summary.md (this file)

DEVELOPMENT.md           (created - project development guide)
```

## Tests Added

Created `tests/test_backends/test_protocol.py` with 14 tests:

### TestChatChunk (4 tests)
- ✅ `test_imports_from_top_level_package` - verifies public imports work from `yoker.backends`
- ✅ `test_chat_chunk_is_frozen` - verifies immutability with AttributeError
- ✅ `test_chat_chunk_with_all_fields` - verifies creation with all optional fields
- ✅ `test_chat_chunk_event_kinds` - verifies all event types present

### TestToolCallDelta (3 tests)
- ✅ `test_tool_call_delta_is_frozen` - verifies immutability
- ✅ `test_tool_call_delta_with_arguments` - verifies arguments_delta field
- ✅ `test_tool_call_delta_minimal` - verifies minimal creation (index only)

### TestUsageStats (4 tests)
- ✅ `test_usage_stats_is_frozen` - verifies immutability
- ✅ `test_usage_stats_defaults` - verifies all fields default to None
- ✅ `test_usage_stats_ollama_native_fields` - verifies Ollama fields preserved
- ✅ `test_usage_stats_openai_fields` - verifies generic fields work
- ✅ `test_usage_stats_mixed_fields` - verifies both field types can coexist

### TestModelBackend (2 tests)
- ✅ `test_model_backend_is_protocol` - verifies it's a Protocol
- ✅ `test_model_backend_protocol_structure` - verifies interface structure with mock implementation

## Quality Checks

All checks passed:

```bash
make check
```

- ✅ **Formatting**: `ruff format` - 4 files reformatted (standard formatting)
- ✅ **Linting**: `ruff check` - All checks passed
- ✅ **Type checking**: `mypy --strict` - Success: no issues found in 87 source files
- ✅ **Testing**: `pytest` - 1296 tests passed (including 14 new backends tests)

## Public API

The `yoker.backends` package exports:

```python
from yoker.backends import (
    ModelBackend,      # Protocol for streaming chat backends
    ChatChunk,         # Frozen dataclass for streaming chunks
    ChatChunkEvent,    # Enum of event types
    ToolCallDelta,     # Frozen dataclass for tool call fragments
    UsageStats,        # Frozen dataclass for usage statistics
)
```

## Acceptance Criteria Status

All acceptance criteria met:

- ✅ **Public imports work from `yoker.backends`**: Verified in `test_imports_from_top_level_package`
- ✅ **`ChatChunk` is frozen dataclass**: Verified in `test_chat_chunk_is_frozen`
- ✅ **One-of text/tool_call/usage per event**: Design supports this via optional fields
- ✅ **`UsageStats` preserves Ollama-native fields**: Verified in `test_usage_stats_ollama_native_fields`
- ✅ **`UsageStats` includes generic fields**: Verified in `test_usage_stats_openai_fields`
- ✅ **`make check` green**: All checks pass (format, lint, typecheck, test)

## Design Notes

### Protocol Signature

The `ModelBackend.chat_stream()` signature follows the design document (§4.3):
- Async-only (Yoker is async-first)
- `**kwargs` is purely internal (not a public extension point)
- Per-provider parameters live in config, not call-site kwargs

### Event Ordering

Backends must emit events in a specific order:
1. `CONTENT_START` before first `CONTENT_DELTA`
2. `THINKING_START` before first `THINKING_DELTA`
3. `TOOL_CALL_START` / `DELTA` / `STOP` bracket each tool call
4. `USAGE` when stats are available (may arrive before final DONE)
5. `DONE` as terminal event

### Compatibility

The design preserves backward compatibility:
- Ollama-native fields (`prompt_eval_count`, `eval_count`, `total_duration_ms`) are first-class
- Generic fields (`input_tokens`, `output_tokens`) added for OpenAI/Anthropic
- Existing `TurnEndEvent` will be extended (Task 6.2) to include both field sets

## Next Steps

This task (6.1) is a **pure creation task** - no existing code was modified. The remaining Phase 1 tasks are:

- **Task 6.2**: Add `input_tokens`/`output_tokens` to `TurnEndEvent`
- **Task 6.3**: Widen `BackendConfig` to tagged-union shape
- **Task 6.4**: Create `backends/factory.py` with `create_backend()` dispatch
- **Task 6.5**: Create `OllamaBackend` adapter
- **Task 6.6**: Update Agent to use ModelBackend instead of direct client

## No Commit

Per instructions, this implementation is **not committed** - the project-manager will handle the commit after the full Phase 1 is implemented.