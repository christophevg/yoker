# API Design: AgentCore Extraction (Task 1.7.1)

**Date**: 2026-05-22
**Reviewer**: API Architect Agent
**Task**: Review API design for AgentCore class extraction

## Executive Summary

This document analyzes the proposed extraction of an `AgentCore` class from the current `Agent` implementation. The goal is to create a shared composition class that holds common state and utilities for both synchronous `Agent` and future asynchronous `AsyncAgent` implementations.

**Recommendation**: The proposed composition pattern is sound and follows established Python conventions. This document provides detailed interface design, delegation patterns, and migration considerations.

## Current State Analysis

### Existing Agent Class Structure

The current `Agent` class (`src/yoker/agent.py`, ~640 lines) contains:

| Component | Lines | Purpose |
|-----------|-------|---------|
| Configuration initialization | 107-122 | Load config from file or use defaults |
| Client initialization | 125-136 | Ollama Client setup (sync-specific) |
| Model selection | 139 | Model name resolution |
| Thinking mode | 142 | ThinkingMode enum state |
| Command registry | 145 | Slash-command registry |
| Agent definition loading | 147-158 | Markdown + YAML frontmatter |
| Guardrail initialization | 161-163 | PathGuardrail for filesystem tools |
| Tool registry building | 201-276 | Tool creation with guardrails |
| Context manager | 169-184 | Conversation persistence |
| Recursion tracking | 187-188 | Subagent depth limits |
| Event handlers | 191 | EventCallback list storage |
| Public methods | 278-639 | process(), begin_session(), end_session(), add_event_handler(), remove_event_handler() |

### Extraction Candidates

Based on the architecture document, the following should move to `AgentCore`:

**State (held in AgentCore)**:
- Configuration object
- Model name
- Thinking mode state
- Agent definition
- Tool registry
- Guardrail
- Context manager
- Recursion depth tracking
- Event handlers list
- Command registry

**Utilities (provided by AgentCore)**:
- Tool registry building
- System prompt resolution
- Context initialization (system message)
- Guardrail validation

**NOT extracted (remains in Agent/AsyncAgent)**:
- Ollama client (different types: `Client` vs `AsyncClient`)
- Event emission (sync vs async execution)
- Streaming logic (`for` vs `async for`)
- Session methods (sync vs async)

## Proposed AgentCore Interface

### Class Definition

```python
# src/yoker/agent_base.py
"""Shared state and utilities for Agent variants."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from yoker.config import Config
from yoker.thinking import ThinkingMode
from yoker.tools import ToolRegistry
from yoker.tools.guardrails import Guardrail

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.commands import CommandRegistry
  from yoker.context import ContextManager

# Type alias for event callbacks (same as in agent.py)
EventCallback = Callable[[Any], None]  # Event type

class AgentCore:
  """Shared state and utilities for both Agent variants.

  This class holds configuration, tool registry, context manager,
  and other state that is common to both sync and async agents.

  Not intended for direct use by consumers. Use Agent or AsyncAgent instead.
  """

  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    _recursion_depth: int = 0,
  ) -> None:
    """Initialize shared agent state.

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
      thinking_mode: Thinking mode (on/off/silent, default: ON).
      command_registry: Optional command registry for slash-commands.
      agent_definition: Pre-loaded AgentDefinition to use for system prompt.
      agent_path: Path to agent definition file (Markdown with frontmatter).
      context_manager: Optional ContextManager for conversation persistence.
      _recursion_depth: Internal parameter for subagent recursion tracking.
    """
    # Implementation details...
```

### Public Properties

AgentCore should expose the following read-only properties for delegation:

```python
@property
def config(self) -> Config:
  """Configuration object."""
  return self._config

@property
def model(self) -> str:
  """Model name to use for chat."""
  return self._model

@property
def thinking_mode(self) -> ThinkingMode:
  """Current thinking mode state."""
  return self._thinking_mode

@property
def agent_definition(self) -> "AgentDefinition | None":
  """Loaded agent definition, if any."""
  return self._agent_definition

@property
def tool_registry(self) -> ToolRegistry:
  """Registry of available tools."""
  return self._tool_registry

@property
def context(self) -> "ContextManager":
  """Context manager for conversation history."""
  return self._context

@property
def command_registry(self) -> "CommandRegistry | None":
  """Command registry for slash-commands."""
  return self._command_registry

@property
def recursion_depth(self) -> int:
  """Current recursion depth (internal)."""
  return self._recursion_depth

@property
def max_recursion_depth(self) -> int:
  """Maximum allowed recursion depth."""
  return self._max_recursion_depth
```

### Public Methods

```python
def add_event_handler(self, handler: EventCallback) -> None:
  """Register an event handler.

  Args:
    handler: Callable that receives Event objects.
  """
  self._event_handlers.append(handler)

def remove_event_handler(self, handler: EventCallback) -> None:
  """Remove a registered event handler.

  Args:
    handler: The handler to remove.
  """
  self._event_handlers.remove(handler)

def get_event_handlers(self) -> list[EventCallback]:
  """Get list of registered event handlers.

  Returns:
    List of event handler callables.
  """
  return self._event_handlers.copy()
```

### Internal Methods (Package-Private)

```python
def _build_tool_registry(self) -> ToolRegistry:
  """Build tool registry filtered by agent definition.

  If an agent definition is loaded, only registers tools listed in
  the agent's tools field. Otherwise, registers all default tools.

  All filesystem tools are created with the agent's guardrail injected
  for defense-in-depth validation.

  Returns:
    ToolRegistry with available tools for this agent.
  """
  # Current implementation from agent.py lines 201-276

def _get_system_prompt(self) -> str:
  """Get system prompt from agent definition or default.

  Returns:
    System prompt string.
  """
  if self._agent_definition is not None:
    return self._agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT
  return DEFAULT_SYSTEM_PROMPT
```

### Internal Attributes (Package-Private)

```python
# Guardrail for filesystem tool validation
_guardrail: Guardrail

# Event handlers storage
_event_handlers: list[EventCallback]
```

## Composition Pattern

### Agent Class (Sync)

After extraction, `Agent` should use composition:

```python
# src/yoker/agent.py
from ollama import Client

from yoker.agent_base import AgentCore

class Agent:
  """Synchronous Agent implementation."""

  def __init__(self, **kwargs) -> None:
    """Initialize synchronous agent."""
    # Delegate initialization to core
    self._core = AgentCore(**kwargs)

    # Initialize sync-specific client
    # Note: Client initialization depends on config from core
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key:
      self._client = Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"}
      )
    else:
      self._client = Client(host=self._core.config.backend.ollama.base_url)

  # Delegate property access to core
  @property
  def config(self) -> Config:
    return self._core.config

  @property
  def model(self) -> str:
    return self._core.model

  @property
  def thinking_mode(self) -> ThinkingMode:
    return self._core.thinking_mode

  @property
  def agent_definition(self) -> "AgentDefinition | None":
    return self._core.agent_definition

  @property
  def tool_registry(self) -> ToolRegistry:
    return self._core.tool_registry

  @property
  def context(self) -> "ContextManager":
    return self._core.context

  @property
  def command_registry(self) -> "CommandRegistry | None":
    return self._core.command_registry

  # Event handler methods delegate to core
  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler."""
    self._core.add_event_handler(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler."""
    self._core.remove_event_handler(handler)

  def _emit(self, event: Event) -> None:
    """Emit event to all handlers (sync)."""
    for handler in self._core.get_event_handlers():
      handler(event)

  # Sync-specific methods remain here
  def process(self, message: str) -> str:
    """Process a message synchronously."""
    # Current implementation from agent.py
    ...

  def begin_session(self) -> None:
    """Begin a session synchronously."""
    self._core.context.save()
    self._emit(SessionStartEvent(...))

  def end_session(self, reason: str = "quit") -> None:
    """End a session synchronously."""
    self._core.context.close()
    self._emit(SessionEndEvent(...))
```

### AsyncAgent Class (Future)

The future `AsyncAgent` will follow the same pattern:

```python
# src/yoker/async_agent.py
from ollama import AsyncClient

from yoker.agent_base import AgentCore

class AsyncAgent:
  """Asynchronous Agent implementation."""

  def __init__(self, **kwargs) -> None:
    """Initialize asynchronous agent."""
    # Delegate initialization to core
    self._core = AgentCore(**kwargs)

    # Initialize async-specific client
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key:
      self._client = AsyncClient(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"}
      )
    else:
      self._client = AsyncClient(host=self._core.config.backend.ollama.base_url)

  # Same property delegations as Agent
  @property
  def config(self) -> Config:
    return self._core.config
  # ... (same as Agent)

  # Event handler methods delegate to core
  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler."""
    self._core.add_event_handler(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler."""
    self._core.remove_event_handler(handler)

  async def _emit(self, event: Event) -> None:
    """Emit event to all handlers (async).

    Supports both sync and async handlers for compatibility.
    """
    for handler in self._core.get_event_handlers():
      if asyncio.iscoroutinefunction(handler):
        await handler(event)
      else:
        handler(event)

  # Async-specific methods
  async def process(self, message: str) -> str:
    """Process a message asynchronously."""
    ...

  async def begin_session(self) -> None:
    """Begin a session asynchronously."""
    self._core.context.save()
    await self._emit(SessionStartEvent(...))

  async def end_session(self, reason: str = "quit") -> None:
    """End a session asynchronously."""
    self._core.context.close()
    await self._emit(SessionEndEvent(...))
```

## Interface Contract

### Public Interface (Identical for Agent and AsyncAgent)

Both classes expose the **same public interface** with matching method signatures:

| Method/Property | Agent (Sync) | AsyncAgent (Async) |
|-----------------|--------------|---------------------|
| `config` property | `Config` | `Config` |
| `model` property | `str` | `str` |
| `thinking_mode` property | `ThinkingMode` | `ThinkingMode` |
| `agent_definition` property | `AgentDefinition \| None` | `AgentDefinition \| None` |
| `tool_registry` property | `ToolRegistry` | `ToolRegistry` |
| `context` property | `ContextManager` | `ContextManager` |
| `add_event_handler(handler)` | `None` | `None` |
| `remove_event_handler(handler)` | `None` | `None` |
| `process(message)` | `str` | `Awaitable[str]` |
| `begin_session()` | `None` | `Awaitable[None]` |
| `end_session(reason)` | `None` | `Awaitable[None]` |

**Note**: The only difference is that async methods return `Awaitable` types.

### Protocol Definition (Optional)

For type checking and documentation, a Protocol can be defined:

```python
# src/yoker/protocols.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class AgentProtocol(Protocol):
  """Protocol defining the public interface for Agent classes."""

  @property
  def config(self) -> Config: ...

  @property
  def model(self) -> str: ...

  @property
  def thinking_mode(self) -> ThinkingMode: ...

  @property
  def agent_definition(self) -> "AgentDefinition | None": ...

  @property
  def tool_registry(self) -> ToolRegistry: ...

  @property
  def context(self) -> "ContextManager": ...

  def add_event_handler(self, handler: EventCallback) -> None: ...

  def remove_event_handler(self, handler: EventCallback) -> None: ...
```

**Recommendation**: Add this Protocol in a future iteration for better type checking, but not required for initial implementation.

## Migration Considerations

### Backward Compatibility

**Critical**: The extraction must maintain 100% backward compatibility with existing `Agent` usage.

**Verification steps**:
1. All existing tests pass without modification
2. All existing imports continue to work
3. All public method signatures unchanged
4. All property names unchanged
5. `python -m yoker` continues to work identically

### Breaking Changes

**None allowed** in this task. The extraction is purely internal refactoring.

### Deprecations

**None required**. The public API remains unchanged.

### Migration Path

```
Before:
  Agent.__init__() → self.config, self.model, self._build_tool_registry(), etc.
  Agent.process() → self.client, self._emit(), etc.

After:
  Agent.__init__() → self._core = AgentCore(...)
                     self._client = Client(...)
  Agent.process() → self._client, self._core.tool_registry, self._emit(), etc.
```

## Implementation Recommendations

### 1. Create agent_base.py Module

**File**: `src/yoker/agent_base.py`

**Contents**:
- AgentCore class with all shared state and utilities
- EventCallback type alias (moved from agent.py)
- DEFAULT_SYSTEM_PROMPT constant (moved from agent.py)

### 2. Update agent.py

**Changes**:
1. Import AgentCore from agent_base
2. Remove initialization code that moves to AgentCore
3. Add `self._core = AgentCore(...)` in `__init__`
4. Add property delegations to `self._core`
5. Update method implementations to use `self._core` attributes
6. Keep sync-specific code: `Client`, `_emit()`, `process()`, session methods

### 3. Update __init__.py

**Current**:
```python
from yoker.agent import Agent

__all__ = ["Agent", ...]
```

**After Phase 1.7 (future)**:
```python
from yoker.agent import Agent
from yoker.async_agent import AsyncAgent

__all__ = ["Agent", "AsyncAgent", ...]
```

**For Task 1.7.1**: No change to `__init__.py` (AsyncAgent comes later).

### 4. Update agent_base.py Exports

Add to `src/yoker/agent_base.py`:
```python
__all__ = ["AgentCore"]
```

## API Design Patterns

### Composition Over Inheritance

The design uses **composition** rather than inheritance:

```python
# Composition (chosen approach)
class Agent:
  def __init__(self):
    self._core = AgentCore()

# Inheritance (rejected approach)
class AgentBase:
  pass

class Agent(AgentBase):
  pass
```

**Rationale**:
- Cleaner separation of sync/async implementations
- No diamond inheritance problems
- Easier to test AgentCore in isolation
- Follows Python best practices (composition over inheritance)

### Property Delegation Pattern

Properties delegate to the composed object:

```python
@property
def model(self) -> str:
  return self._core.model
```

**Benefits**:
- Maintains existing public API
- Provides type hints for IDEs
- Allows future customization in Agent/AsyncAgent
- Clear separation of concerns

### Read-Only Properties

All delegated properties are read-only:

```python
@property
def model(self) -> str:
  return self._core.model  # No setter
```

**Rationale**:
- State should only be modified through methods
- Prevents accidental mutation
- Maintains immutability where possible

## Open Questions

### Q1: Should AgentCore be a public class?

**Options**:
1. **Public**: `from yoker.agent_base import AgentCore`
2. **Private**: Rename to `_AgentCore`, not exported
3. **Internal**: Public but documented as internal-use-only

**Recommendation**: **Option 3 (Internal)**. Export as `AgentCore` but document that it's for internal use only. This allows advanced users to extend it while discouraging casual use.

```python
# In agent_base.py
class AgentCore:
  """Shared state and utilities for Agent variants.

  .. warning::
    This class is for internal use. Use Agent or AsyncAgent instead.
  """
```

### Q2: Should `_emit()` be in AgentCore?

**Current design**: `_emit()` stays in Agent/AsyncAgent (sync vs async)

**Alternative**: Put `_emit()` in AgentCore with sync/async support

**Recommendation**: Keep `_emit()` in Agent/AsyncAgent. The implementation differs significantly (sync loop vs async loop with `iscoroutinefunction` checks). Separation keeps AgentCore simpler.

### Q3: Should event handlers be in AgentCore?

**Current design**: Event handlers stored in AgentCore

**Alternative**: Event handlers stored in Agent/AsyncAgent

**Recommendation**: Keep in AgentCore. The storage is identical (a list), only the emission differs. This allows `add_event_handler()` and `remove_event_handler()` to be simple delegation methods.

### Q4: How to handle `_recursion_depth` parameter?

**Current**: `_recursion_depth` is a constructor parameter (internal use)

**Options**:
1. Keep as parameter in both AgentCore and Agent constructors
2. Make AgentCore attribute private, remove from Agent constructor
3. Pass only to AgentCore, not exposed in Agent constructor

**Recommendation**: **Option 1** (keep as-is). It's an internal parameter used by AgentTool for subagent spawning. The underscore prefix makes it clear it's not a public API.

## Test Strategy

### Unit Tests for AgentCore

Create `tests/test_agent_core.py`:

```python
def test_agent_core_initialization():
  """Test AgentCore initializes with defaults."""
  core = AgentCore()
  assert core.model == "llama3.2:latest"  # Default from config
  assert core.thinking_mode == ThinkingMode.ON
  assert core.tool_registry is not None
  assert core.context is not None

def test_agent_core_model_override():
  """Test model parameter overrides config."""
  core = AgentCore(model="custom-model")
  assert core.model == "custom-model"

def test_agent_core_agent_definition():
  """Test agent definition loading."""
  core = AgentCore(agent_path="examples/agents/researcher.md")
  assert core.agent_definition is not None
  assert "research" in core.agent_definition.system_prompt.lower()

def test_agent_core_event_handlers():
  """Test event handler registration."""
  core = AgentCore()

  handler_called = []
  def handler(event):
    handler_called.append(event)

  core.add_event_handler(handler)
  assert len(core.get_event_handlers()) == 1

  core.remove_event_handler(handler)
  assert len(core.get_event_handlers()) == 0

def test_agent_core_tool_registry_filtering():
  """Test tool registry respects agent definition."""
  # Agent with only "read" tool
  core = AgentCore(agent_definition=AgentDefinition(
    name="test",
    system_prompt="test",
    tools=["read"]
  ))
  assert "read" in core.tool_registry.names
  # Other tools should not be present
```

### Integration Tests for Agent

Existing tests in `tests/test_agent.py` should pass unchanged:

```python
def test_agent_initialization():
  agent = Agent()
  assert agent.model is not None
  assert agent.tool_registry is not None
  # ... existing tests continue to work
```

### Test Coverage Requirements

- AgentCore unit tests: >90% coverage
- Agent integration tests: All existing tests pass
- No regression in test coverage percentage

## Acceptance Criteria

### Functional Requirements

- [ ] AgentCore class created in `src/yoker/agent_base.py`
- [ ] AgentCore holds: config, model, thinking_mode, agent_definition, tool_registry, guardrail, context, recursion_depth, event_handlers
- [ ] AgentCore provides: `_build_tool_registry()`, `_get_system_prompt()`, `add_event_handler()`, `remove_event_handler()`, `get_event_handlers()`
- [ ] Agent class updated to use AgentCore via composition
- [ ] Agent property delegations added for all core attributes
- [ ] Agent methods updated to use `self._core` attributes
- [ ] All existing tests pass without modification
- [ ] New unit tests for AgentCore created

### Non-Functional Requirements

- [ ] No breaking changes to public API
- [ ] No performance degradation (initialization time)
- [ ] Code quality maintained (ruff, mypy)
- [ ] Type hints complete for AgentCore
- [ ] Docstrings provided for AgentCore class and methods

### Quality Gates

- [ ] `make test` passes (all existing + new tests)
- [ ] `make typecheck` passes (mypy validates AgentCore)
- [ ] `make lint` passes (ruff validates AgentCore)
- [ ] Test coverage maintained or improved (target: >80%)
- [ ] `python -m yoker` works identically to before

## Summary

The AgentCore extraction is a well-designed refactoring that:

1. **Follows composition over inheritance** - Clean, testable separation
2. **Maintains backward compatibility** - No breaking changes
3. **Prepares for AsyncAgent** - Clear separation of sync/async concerns
4. **Reduces duplication** - Shared state and utilities in one place
5. **Improves testability** - AgentCore can be tested in isolation

The implementation should proceed as outlined, with careful attention to maintaining the existing public API and passing all existing tests.

## Next Steps

1. **Create** `src/yoker/agent_base.py` with AgentCore class
2. **Refactor** `src/yoker/agent.py` to use AgentCore
3. **Write** unit tests for AgentCore
4. **Verify** all existing tests pass
5. **Proceed** to Task 1.7.2 (Refactor Sync Agent)

## Appendix: Code Comparison

### Before (Current Agent.__init__)

```python
def __init__(
  self,
  model: str | None = None,
  config: Config | None = None,
  config_path: Path | str | None = None,
  thinking_mode: ThinkingMode = ThinkingMode.ON,
  command_registry: "CommandRegistry | None" = None,
  agent_definition: "AgentDefinition | None" = None,
  agent_path: Path | str | None = None,
  context_manager: "ContextManager | None" = None,
  _recursion_depth: int = 0,
) -> None:
  # Load environment variables
  load_dotenv(Path(".env"))
  load_dotenv(Path(".env.local"))

  # Load configuration
  if config is not None:
    self.config = config
  elif config_path is not None:
    from yoker.config import load_config
    self.config = load_config(config_path)
  else:
    self.config = Config()

  # Validate configuration
  from yoker.config.validator import validate_config
  warnings = validate_config(self.config)
  for warning in warnings:
    log.warning("config_validation_warning", warning=warning)

  # Initialize client
  api_key = os.environ.get("OLLAMA_API_KEY")
  if api_key:
    self.client = Client(host="https://ollama.com", headers={"Authorization": f"Bearer {api_key}"})
  else:
    self.client = Client(host=self.config.backend.ollama.base_url)

  # Use provided model or config model
  self.model = model if model is not None else self.config.backend.ollama.model

  # Thinking mode state
  self.thinking_mode = thinking_mode

  # Command registry
  self.command_registry = command_registry

  # Load agent definition
  self.agent_definition: AgentDefinition | None = None
  system_prompt = DEFAULT_SYSTEM_PROMPT
  if agent_definition is not None:
    self.agent_definition = agent_definition
    system_prompt = agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT
  elif agent_path is not None:
    from yoker.agents import load_agent_definition
    self.agent_definition = load_agent_definition(agent_path)
    system_prompt = self.agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT

  # Initialize guardrail
  from yoker.tools.path_guardrail import PathGuardrail
  self._guardrail = PathGuardrail(self.config)

  # Build tool registry
  self.tool_registry = self._build_tool_registry()

  # Initialize context manager
  if context_manager is not None:
    self.context = context_manager
  else:
    from yoker.context import BasicPersistenceContextManager
    self.context = BasicPersistenceContextManager(
      storage_path=Path(self.config.context.storage_path),
      session_id=self.config.context.session_id,
    )

  # Add system prompt to context
  messages = self.context.get_messages()
  has_system = any(m.get("role") == "system" for m in messages)
  if not has_system:
    self.context.add_message("system", system_prompt)

  # Recursion tracking
  self._recursion_depth = _recursion_depth
  self._max_recursion_depth = self.config.tools.agent.max_recursion_depth

  # Event handlers
  self._event_handlers: list[EventCallback] = []

  log.info("agent_initialized", ...)
```

### After (Agent.__init__ with AgentCore)

```python
def __init__(
  self,
  model: str | None = None,
  config: Config | None = None,
  config_path: Path | str | None = None,
  thinking_mode: ThinkingMode = ThinkingMode.ON,
  command_registry: "CommandRegistry | None" = None,
  agent_definition: "AgentDefinition | None" = None,
  agent_path: Path | str | None = None,
  context_manager: "ContextManager | None" = None,
  _recursion_depth: int = 0,
) -> None:
  # Delegate to AgentCore for shared state
  self._core = AgentCore(
    model=model,
    config=config,
    config_path=config_path,
    thinking_mode=thinking_mode,
    command_registry=command_registry,
    agent_definition=agent_definition,
    agent_path=agent_path,
    context_manager=context_manager,
    _recursion_depth=_recursion_depth,
  )

  # Initialize sync-specific client
  api_key = os.environ.get("OLLAMA_API_KEY")
  if api_key:
    self._client = Client(
      host="https://ollama.com",
      headers={"Authorization": f"Bearer {api_key}"}
    )
  else:
    self._client = Client(host=self._core.config.backend.ollama.base_url)

  log.info(
    "agent_initialized",
    model=self.model,
    thinking_mode=self.thinking_mode.value,
    has_agent_definition=self.agent_definition is not None,
    available_tools=self.tool_registry.names,
  )

# Property delegations
@property
def config(self) -> Config:
  return self._core.config

@property
def model(self) -> str:
  return self._core.model

# ... other property delegations ...
```

This demonstrates the significant simplification of Agent's constructor while maintaining the same initialization logic in AgentCore.