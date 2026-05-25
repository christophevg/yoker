# Async-First Agent Architecture

**Document Version**: 3.0
**Date**: 2026-05-25
**Status**: Implemented

## Executive Summary

Yoker's Agent has been migrated to an **async-only architecture**:

1. **`yoker.Agent`** - Async-native implementation (the only Agent class)

The architecture was simplified from the original two-class design (Agent + AsyncAgent)
to a single async-only Agent class. This decision was made because:
- Simpler API surface (only one Agent class to learn)
- All modern Python web frameworks (FastAPI, Quart) are async-native
- No need to maintain sync/async parity
- Event handlers naturally benefit from async (I/O operations)

This architectural shift positions Yoker for:
- Better integration with async web frameworks (Quart, FastAPI)
- Non-blocking I/O operations (file, network, subprocess)
- Parallel tool execution in future phases
- Cleaner resource management with async context managers

## Vision and Goals

### Primary Goals

| Goal | Description | Status |
|------|-------------|--------|
| Async-Native Agent | Agent uses async throughout (no wrappers) | ✅ Complete |
| Code Sharing | Minimize duplication through AgentCore | ✅ Complete |
| Non-Blocking Events | Async event handlers supported | ✅ Complete |
| Foundation for Parallelism | Architecture supports future parallel tool execution | ✅ Complete |

### Non-Goals

- Sync Agent implementation (simplified to async-only)
- Parallel tool execution (Phase 2)
- Performance optimization (maintain current performance)

## Architecture Overview

### Implemented State (Async-Only Agent)

```python
# yoker/agent.py
class Agent:
    async def process(self, message: str) -> str:
        """Async implementation - fully async throughout."""
        async_stream = await self._client.chat(...)  # AsyncClient
        async for chunk in async_stream:
            await self._emit(event)  # Async event emission
        return content

    async def begin_session(self) -> None:
        """Start a new session."""
        ...

    async def end_session(self) -> None:
        """End the current session."""
        ...
```

**Issues:**
1. Blocks event loop if used in async context
2. Cannot integrate with async frameworks without thread pool
3. No async variant available
4. Tool execution is sequential with no parallelism path

### Target State (Two Separate Classes)

```python
# yoker/agent.py (sync)
class Agent:
    def process(self, message: str) -> str:
        """Sync implementation - no async/await anywhere."""
        stream = self._client.chat(...)  # Sync Client
        for chunk in stream:
            self._emit(event)  # Sync event emission
        return content

# yoker/async_agent.py (async)
class AsyncAgent:
    async def process(self, message: str) -> str:
        """Async implementation - fully async throughout."""
        async_stream = await self._client.chat(...)  # AsyncClient
        async for chunk in async_stream:
            await self._emit(event)  # Async event emission
        return content
```

**Benefits:**
1. Clean separation - no mixed sync/async in one class
2. Follows httpx pattern (Client/AsyncClient)
3. Async Agent is truly async-native
4. Sync Agent has no asyncio overhead
5. Both share utilities to minimize duplication

### Package Structure

```
src/yoker/
  __init__.py              # Exports yoker.Agent and yoker.AsyncAgent
  agent.py                 # Sync Agent implementation
  async_agent.py           # Async AsyncAgent implementation
  agent_base.py            # Shared AgentCore class
```

### Import Paths

```python
# Sync usage
from yoker import Agent

# Async usage
from yoker import AsyncAgent
```

## Code Sharing Strategy

### Approach: Composition with AgentCore

Both `Agent` classes delegate to a shared `AgentCore` class that holds common state and provides shared functionality.

```python
# yoker/agent_base.py
class AgentCore:
    """Shared state and utilities for both Agent variants.

    Holds:
    - Configuration
    - Context manager
    - Tool registry
    - Guardrails
    - Agent definition
    - Recursion tracking

    Provides:
    - Tool registry building
    - System prompt handling
    - Context initialization
    """

    def __init__(
        self,
        model: str | None = None,
        config: Config | None = None,
        ...
    ):
        self.config = config or Config()
        self.model = model or self.config.backend.ollama.model
        self.tool_registry = self._build_tool_registry()
        self.context = context_manager or BasicPersistenceContextManager(...)
        self._guardrail = PathGuardrail(self.config)
        # ... common initialization

    def _build_tool_registry(self) -> ToolRegistry:
        """Build tool registry (used by both sync and async agents)."""
        # Tool creation logic (same for both)
        ...

    def add_event_handler(self, handler: EventCallback) -> None:
        """Register an event handler."""
        self._event_handlers.append(handler)

    def remove_event_handler(self, handler: EventCallback) -> None:
        """Remove an event handler."""
        self._event_handlers.remove(handler)
```

```python
# yoker/agent.py
from ollama import Client

from yoker.agent_base import AgentCore

class Agent:
    """Synchronous Agent implementation."""

    def __init__(self, **kwargs):
        self._core = AgentCore(**kwargs)
        self._client = Client(host=self._core.config.backend.ollama.base_url)
        # Sync client initialization

    # Delegate property access to core
    @property
    def model(self) -> str:
        return self._core.model

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._core.tool_registry

    @property
    def context(self) -> ContextManager:
        return self._core.context

    # ... other delegated properties

    def add_event_handler(self, handler: EventCallback) -> None:
        """Register an event handler (sync)."""
        self._core.add_event_handler(handler)

    def _emit(self, event: Event) -> None:
        """Emit event to all handlers (sync)."""
        for handler in self._core._event_handlers:
            handler(event)

    def process(self, message: str) -> str:
        """Process a message synchronously."""
        # Sync streaming implementation
        stream = self._client.chat(...)
        for chunk in stream:
            self._emit(event)
        return content

    def begin_session(self) -> None:
        """Begin a session synchronously."""
        self._core.context.save()
        self._emit(SessionStartEvent(...))

    def end_session(self, reason: str = "quit") -> None:
        """End a session synchronously."""
        self._core.context.close()
        self._emit(SessionEndEvent(...))
```

```python
# yoker/async_agent.py
from ollama import AsyncClient

from yoker.agent_base import AgentCore

class AsyncAgent:
    """Asynchronous Agent implementation."""

    def __init__(self, **kwargs):
        self._core = AgentCore(**kwargs)
        self._client = AsyncClient(host=self._core.config.backend.ollama.base_url)
        # Async client initialization

    # Delegate property access to core
    @property
    def model(self) -> str:
        return self._core.model

    # ... other delegated properties (same as sync)

    def add_event_handler(self, handler: EventCallback) -> None:
        """Register an event handler (supports both sync and async handlers)."""
        self._core.add_event_handler(handler)

    async def _emit(self, event: Event) -> None:
        """Emit event to all handlers (async).

        Supports both sync and async handlers for compatibility.
        """
        for handler in self._core._event_handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)

    async def process(self, message: str) -> str:
        """Process a message asynchronously."""
        # Async streaming implementation
        async_stream = await self._client.chat(...)
        async for chunk in async_stream:
            await self._emit(event)
        return content

    async def begin_session(self) -> None:
        """Begin a session asynchronously."""
        self._core.context.save()
        await self._emit(SessionStartEvent(...))

    async def end_session(self, reason: str = "quit") -> None:
        """End a session asynchronously."""
        self._core.context.close()
        await self._emit(SessionEndEvent(...))
```

### Shared Code Summary

| Component | Location | Shared? |
|-----------|----------|---------|
| Configuration | AgentCore | Yes |
| Context management | AgentCore | Yes |
| Tool registry | AgentCore | Yes |
| Guardrails | AgentCore | Yes |
| Agent definition | AgentCore | Yes |
| Client | Agent/AsyncAgent | No (different types) |
| Event emission | Agent/AsyncAgent | No (sync vs async) |
| Streaming logic | Agent/AsyncAgent | No (sync vs async for) |
| Session methods | Agent/AsyncAgent | Similar but different sync/async |

## Identical Public Interface

Both classes expose the **same public methods** with **same signatures**:

```python
# Common interface (Protocol)
class AgentProtocol(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def tool_registry(self) -> ToolRegistry: ...

    @property
    def context(self) -> ContextManager: ...

    @property
    def thinking_mode(self) -> ThinkingMode: ...

    @property
    def agent_definition(self) -> AgentDefinition | None: ...

    def add_event_handler(self, handler: EventCallback) -> None: ...

    def remove_event_handler(self, handler: EventCallback) -> None: ...

    def process(self, message: str) -> str: ...  # sync: str, async: Awaitable[str]

    def begin_session(self) -> None: ...  # sync: None, async: Awaitable[None]

    def end_session(self, reason: str = "quit") -> None: ...  # sync: None, async: Awaitable[None]
```

**Note:** The only difference is that async methods return `Awaitable` types. This is the httpx pattern:
- `httpx.Client.get()` returns `Response`
- `httpx.AsyncClient.get()` returns `Awaitable[Response]`

## Implementation Plan

### Phase 1: Shared Infrastructure (Estimated: 2 hours)

#### 1.1 Extract AgentCore Class

**Create:** `src/yoker/agent_base.py`

**Extract from current `agent.py`:**
- Configuration initialization
- Tool registry building
- Context manager initialization
- Guardrail setup
- Agent definition loading
- Event handler storage
- Recursion tracking

**Estimated time:** 1 hour

---

#### 1.2 Refactor Sync Agent to Use AgentCore

**Update:** `src/yoker/agent.py`

**Changes:**
- Replace direct initialization with AgentCore delegation
- Keep sync Client initialization
- Keep sync `_emit()` method
- Keep sync `process()` method
- Keep sync session methods
- Add property delegations to AgentCore

**Estimated time:** 1 hour

---

### Phase 2: Async Agent Implementation (Estimated: 4 hours)

#### 2.1 Create Async Agent Module

**Create:** `src/yoker/async_agent.py`

**Implementation:**
- Use AgentCore for shared state
- Use AsyncClient from ollama library
- Implement async `_emit()` with sync/async handler support
- Implement async `process()` with async streaming
- Implement async session methods

**Update:** `src/yoker/__init__.py`

```python
"""Yoker agent harness."""
from yoker.agent import Agent
from yoker.async_agent import AsyncAgent

__all__ = ["Agent", "AsyncAgent"]
```

**Estimated time:** 2 hours

---

#### 2.2 Async Event Emission

**Implementation:**

```python
async def _emit(self, event: Event) -> None:
    """Emit event to all handlers asynchronously.

    Supports both sync and async handlers for backward compatibility.
    """
    for handler in self._core._event_handlers:
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)
```

**Key Decision:** Support both sync and async handlers for compatibility.

**Estimated time:** 30 minutes

---

#### 2.3 Async Ollama Streaming

**Implementation:**

```python
async def process(self, message: str) -> str:
    # Use AsyncClient
    async_stream = await self._client.chat(
        model=self.model,
        messages=self.context.get_context(),
        tools=self.tool_registry.get_schemas(),
        think=self.thinking_mode.is_enabled,
        stream=True,
    )

    # Async iteration
    async for chunk in async_stream:
        # Process chunks
        await self._emit(event)
```

**Estimated time:** 1.5 hours

---

### Phase 3: CLI Integration (Estimated: 1.5 hours)

#### 3.1 Add Async CLI Entry Point

**Update:** `src/yoker/__main__.py`

**Current (sync):**
```python
def main():
    agent = Agent(...)
    agent.begin_session()
    while True:
        message = session.prompt("You: ")
        response = agent.process(message)
        print(response)
    agent.end_session()
```

**New (async):**
```python
async def main_async():
    from yoker import AsyncAgent
    agent = AsyncAgent(...)
    await agent.begin_session()
    try:
        while True:
            message = await session.prompt_async("You: ")
            response = await agent.process(message)
            print(response)
    except KeyboardInterrupt:
        await agent.end_session(reason="interrupt")

def main():
    asyncio.run(main_async())
```

**Estimated time:** 45 minutes

---

#### 3.2 Async Event Handler Updates

**Update:** `src/yoker/events/handlers.py`

Make `ConsoleEventHandler` async-compatible:

```python
class ConsoleEventHandler:
    """Console event handler supporting both sync and async contexts."""

    async def __call__(self, event: Event) -> None:
        """Handle event (async for compatibility)."""
        # Event handling logic
        ...

    # Keep sync support for backward compatibility
    def handle_sync(self, event: Event) -> None:
        """Sync handler (wraps async)."""
        asyncio.run(self(event))
```

**Estimated time:** 45 minutes

---

### Phase 4: Testing and Documentation (Estimated: 2 hours)

#### 4.1 Async Test Coverage

**Test Files:**
- `tests/test_async_agent.py` - New async agent tests
- `tests/test_agent.py` - Update existing sync agent tests
- `tests/conftest.py` - Add async fixtures

**Test Cases:**
```python
import pytest

# Sync agent tests
def test_sync_agent_process():
    agent = Agent()
    agent.begin_session()
    response = agent.process("Hello")
    assert isinstance(response, str)
    agent.end_session()

# Async agent tests
@pytest.mark.asyncio
async def test_async_agent_process():
    from yoker import AsyncAgent
    agent = AsyncAgent()
    await agent.begin_session()
    response = await agent.process("Hello")
    assert isinstance(response, str)
    await agent.end_session()

@pytest.mark.asyncio
async def test_async_event_handlers():
    from yoker import AsyncAgent
    agent = AsyncAgent()

    events_received = []
    async def async_handler(event):
        events_received.append(event)

    agent.add_event_handler(async_handler)
    await agent.process("test")
    assert len(events_received) > 0
```

**Estimated time:** 1 hour

---

#### 4.2 Documentation Updates

**Files to Update:**
- `README.md` - Document both sync and async usage
- `docs/quickstart.md` - Add async examples
- `docs/api/agent.md` - Document both Agent classes
- `CLAUDE.md` - Update architecture description

**Key Documentation Points:**
1. `yoker.Agent` is sync-native
2. `yoker.AsyncAgent` is async-native
3. Both have identical interfaces
4. Code examples for both variants

**Estimated time:** 1 hour

---

## Migration Path

### Backward Compatibility Guarantee

**Existing sync code continues to work unchanged:**
```python
# Sync API (unchanged)
from yoker import Agent
agent = Agent(model="llama3.2")
agent.begin_session()
response = agent.process("Hello")
agent.end_session()
```

### New Async Usage

**Async consumers use the new AsyncAgent:**
```python
# Async API (new)
from yoker import AsyncAgent
agent = AsyncAgent(model="llama3.2")
await agent.begin_session()
response = await agent.process("Hello")
await agent.end_session()
```

### Framework Integration

```python
# Quart/FastAPI integration (new capability)
from quart import Quart
from yoker import AsyncAgent

app = Quart(__name__)
agent = AsyncAgent(model="llama3.2")

@app.route("/chat", methods=["POST"])
async def chat():
    data = await request.get_json()
    response = await agent.process(data["message"])
    return {"response": response}
```

---

## Acceptance Criteria

### Functional Requirements

- [ ] **FR1:** `yoker.Agent` class exists with sync `process()` method
- [ ] **FR2:** `yoker.AsyncAgent` class exists with async `process()` method
- [ ] **FR3:** Both classes have identical public interfaces
- [ ] **FR4:** `AgentCore` class holds shared state and utilities
- [ ] **FR5:** AsyncAgent uses `AsyncClient` from ollama library
- [ ] **FR6:** Sync Agent uses `Client` from ollama library
- [ ] **FR7:** AsyncAgent supports both sync and async event handlers
- [ ] **FR8:** All existing tests pass (backward compatibility)
- [ ] **FR9:** New async tests cover async functionality
- [ ] **FR10:** Documentation updated with both sync and async examples
- [ ] **FR11:** CLI uses AsyncAgent internally

### Non-Functional Requirements

- [ ] **NFR1:** No code duplication (shared utilities in AgentCore)
- [ ] **NFR2:** Async API properly handles concurrent operations
- [ ] **NFR3:** Sync API has no asyncio overhead
- [ ] **NFR4:** Resource cleanup works correctly for both variants
- [ ] **NFR5:** Error handling preserves stack traces for both variants
- [ ] **NFR6:** Type hints updated for both sync and async variants

### Quality Gates

- [ ] `make test` passes (all existing tests)
- [ ] `make typecheck` passes (mypy validates both agents)
- [ ] `make lint` passes (code quality)
- [ ] Test coverage maintained or improved (target: >80%)
- [ ] Documentation builds without errors

---

## Time Estimates

| Phase | Task | Estimate |
|-------|------|----------|
| 1.1 | Extract AgentCore Class | 1 hour |
| 1.2 | Refactor Sync Agent | 1 hour |
| **Phase 1 Total** | | **2 hours** |
| 2.1 | Create Async Agent | 2 hours |
| 2.2 | Async Event Emission | 30 min |
| 2.3 | Async Ollama Streaming | 1.5 hours |
| **Phase 2 Total** | | **4 hours** |
| 3.1 | Async CLI Entry Point | 45 min |
| 3.2 | Async Event Handler Updates | 45 min |
| **Phase 3 Total** | | **1.5 hours** |
| 4.1 | Async Test Coverage | 1 hour |
| 4.2 | Documentation Updates | 1 hour |
| **Phase 4 Total** | | **2 hours** |
| **Total Estimated Time** | | **9.5 hours** |

**Buffer for unexpected issues:** +2 hours
**Total with buffer:** ~11-12 hours

---

## Future Enhancements (Phase 2)

### Async Tool Execution

**Future Goal:** Tools become async-native

```python
class Tool(ABC):
    @abstractmethod
    async def execute_async(self, params: dict, config: ToolConfig) -> ToolResult:
        """Execute tool asynchronously."""
        pass

    def execute(self, params: dict, config: ToolConfig) -> ToolResult:
        """Sync wrapper for backward compatibility."""
        return asyncio.run(self.execute_async(params, config))
```

**Benefits:**
- Non-blocking file I/O (aiofiles)
- Non-blocking subprocess execution
- Non-blocking network calls
- Foundation for parallel tool execution

---

### Parallel Tool Execution

**Future Goal:** Execute multiple independent tool calls in parallel

```python
# Async Agent can execute tools in parallel
results = await asyncio.gather(*[
    self._execute_tool(call) for call in tool_calls
])
```

---

## Open Questions

### Q1: Should we provide a convenience import?

**Current design:** `from yoker import AsyncAgent` (matches httpx pattern exactly)

**Alternative:** Also provide type aliases for clarity
```python
from yoker import Agent, AsyncAgent  # Primary
# or
from yoker import Agent as SyncAgent, AsyncAgent  # Explicit naming
```

**Recommendation:** Match httpx exactly with `Agent` and `AsyncAgent` as primary exports

---

### Q2: How to handle context manager protocol?

The AsyncAgent might benefit from async context manager support:

```python
async with AsyncAgent() as agent:
    response = await agent.process("Hello")
```

**Decision:** Add in future iteration, not MVP

---

### Q3: Should we provide a unified factory function?

**Option:**
```python
def create_agent(async_: bool = False, **kwargs):
    if async_:
        from yoker import AsyncAgent
        return AsyncAgent(**kwargs)
    else:
        from yoker import Agent
        return Agent(**kwargs)
```

**Recommendation:** Not for MVP, let users import explicitly

---

## References

- Python asyncio documentation: https://docs.python.org/3/library/asyncio.html
- ollama Python library async support: https://github.com/ollama/ollama-python
- httpx Client/AsyncClient pattern: https://www.python-httpx.org/async/