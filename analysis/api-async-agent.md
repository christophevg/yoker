# API Analysis: AsyncAgent Implementation

**Date**: 2026-05-23
**Reviewer**: API Architect Agent
**Task**: 1.7.3 Create Async Agent Module
**Context Files**:
- `analysis/async-first-architecture.md` - Full architecture design
- `src/yoker/base.py` - AgentCore class (implemented)
- `src/yoker/agent.py` - Sync Agent implementation
- `TODO.md` - Task details

## Summary

This analysis reviews the proposed AsyncAgent design for the yoker agent harness. The design follows the **httpx pattern** with two separate classes (`Agent` for sync, `AsyncAgent` for async) that share identical public interfaces. Both classes use composition with `AgentCore` for shared state management.

**Verdict**: The architecture design is sound and well-structured. The implementation should proceed as designed with minor clarifications and recommendations documented below.

## Findings

### Strengths

1. **Clean Separation of Concerns**
   - Composition pattern with AgentCore eliminates code duplication
   - Sync Agent has no asyncio overhead
   - Async Agent is truly async-native (no wrappers)
   - Clear ownership: AgentCore owns state, Agent/AsyncAgent own I/O

2. **Consistent with httpx Pattern**
   - `Agent` / `AsyncAgent` naming matches established conventions
   - Identical public interfaces with `Awaitable` return types for async
   - Easy migration path for consumers

3. **Well-Designed Event System**
   - Async `_emit()` supports both sync and async handlers
   - Backward compatible with existing sync handlers
   - Clean detection via `asyncio.iscoroutinefunction()`

4. **Security-First Design**
   - Guardrail injection preserved via AgentCore
   - AgentTool registration happens after core initialization
   - Recursion depth tracking shared between variants

### Issues and Recommendations

#### 1. Missing Package Export Documentation

**Issue**: The architecture document shows `__init__.py` export, but the API contract should be explicitly documented.

**Location**: `src/yoker/__init__.py`

**Recommendation**: Ensure exports are documented in the public API:

```python
# src/yoker/__init__.py
"""Yoker agent harness."""

from yoker.agent import Agent
from yoker.async_agent import AsyncAgent

__all__ = ["Agent", "AsyncAgent"]
```

**Severity**: Low - Already designed, just needs verification during implementation.

---

#### 2. Async Context Manager Support (Future Consideration)

**Issue**: The architecture mentions async context manager support as "Add in future iteration, not MVP" but no `__aenter__` / `__aexit__` design is documented.

**Location**: AsyncAgent class

**Recommendation**: Document the future interface now to prevent API lock-in:

```python
# Future API (not MVP):
async def __aenter__(self) -> "AsyncAgent":
    await self.begin_session()
    return self

async def __aexit__(self, *args) -> None:
    await self.end_session(reason="context_exit")
```

**Severity**: Low - Deferred to future iteration, but should be documented.

---

#### 3. Property Delegation Completeness

**Issue**: All properties must be delegated from AsyncAgent to AgentCore to maintain identical interfaces.

**Required Properties** (from sync Agent):
- `config: Config`
- `model: str`
- `thinking_mode: ThinkingMode`
- `agent_definition: AgentDefinition | None`
- `tool_registry: ToolRegistry`
- `context: ContextManager`
- `command_registry: CommandRegistry | None`
- `_recursion_depth: int`
- `_max_recursion_depth: int`
- `_event_handlers: list[EventCallback]`
- `client: AsyncClient` (async-specific)
- `_guardrail: PathGuardrail`

**Severity**: Low - Straightforward delegation, just needs implementation verification.

---

#### 4. Client Type Difference

**Issue**: The `client` property has different types:
- `Agent.client: Client` (sync)
- `AsyncAgent.client: AsyncClient` (async)

**Recommendation**: Document this as the intentional type difference. Both classes expose `.client` but with different types. This is acceptable and follows the same pattern as httpx.

**Severity**: Low - Expected behavior, just needs documentation.

---

#### 5. Async Event Handler Signature

**Issue**: The architecture shows async handlers but doesn't document the exact signature requirements.

**Handler Signature** (to be documented):

```python
# Sync handler
def handler(event: Event) -> None:
    ...

# Async handler
async def handler(event: Event) -> None:
    ...
```

**AsyncAgent._emit() Implementation**:

```python
async def _emit(self, event: Event) -> None:
    """Emit event to all handlers asynchronously.
    
    Supports both sync and async handlers for backward compatibility.
    """
    for handler in self._core.get_event_handlers():
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)
```

**Recommendation**: Document that handlers must not raise exceptions (or exceptions will be silently ignored in async context). Consider adding try/except around handler invocation:

```python
async def _emit(self, event: Event) -> None:
    for handler in self._core.get_event_handlers():
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception:
            log.exception("event_handler_error", handler=handler.__name__)
```

**Severity**: Medium - Error handling in event emission is important for robustness.

---

#### 6. Session Method Return Types

**Issue**: The architecture shows `begin_session()` and `end_session()` but doesn't explicitly state async return types.

**AsyncAgent Methods**:
- `async def begin_session(self) -> None`
- `async def end_session(self, reason: str = "quit") -> None`

**Sync Agent Methods**:
- `def begin_session(self) -> None`
- `def end_session(self, reason: str = "quit") -> None`

**Recommendation**: This is correct - both return `None` (or `Awaitable[None]` for async). No changes needed, just confirm during implementation.

**Severity**: Low - Already designed correctly.

---

#### 7. Resource Cleanup in AsyncAgent

**Issue**: Async context managers (`__aenter__` / `__aexit__`) are deferred, but resource cleanup is still important.

**Current Sync Agent Cleanup**:
```python
def end_session(self, reason: str = "quit") -> None:
    self.context.close()
    self._emit(SessionEndEvent(...))
```

**AsyncAgent Cleanup**:
```python
async def end_session(self, reason: str = "quit") -> None:
    self._core.context.close()  # context.close() is sync
    await self._emit(SessionEndEvent(...))
```

**Question**: Is `ContextManager.close()` async-safe? Need to verify `BasicPersistenceContextManager.close()` doesn't have blocking I/O.

**Recommendation**: Verify that `context.close()` can be safely called in async context. If it has blocking I/O, consider making it async:

```python
# If context needs async cleanup:
async def end_session(self, reason: str = "quit") -> None:
    await self._core.context.close_async()  # Future async method
    await self._emit(SessionEndEvent(...))
```

**Severity**: Medium - Need to verify during implementation.

---

#### 8. AgentTool Registration Timing

**Issue**: AgentTool is registered after AgentCore initialization in sync Agent. This pattern must be replicated in AsyncAgent.

**Sync Agent Pattern** (lines 123-134 in agent.py):
```python
# Register AgentTool after core initialization
if self._core.agent_definition is not None:
    allowed_tools = {t.lower() for t in self._core.agent_definition.tools}
    if "agent" in allowed_tools:
        self._core.tool_registry.register(
            AgentTool(guardrail=self._core.guardrail, parent_agent=self)
        )
else:
    self._core.tool_registry.register(
        AgentTool(guardrail=self._core.guardrail, parent_agent=self)
    )
```

**AsyncAgent Requirement**: Same pattern, pass `parent_agent=self` (the AsyncAgent instance) to AgentTool.

**Note**: AgentTool's `execute()` method is sync, but it spawns a subagent. Need to verify subagent spawning works in async context.

**Severity**: Medium - Need to verify AgentTool compatibility with AsyncAgent.

---

#### 9. Ollama AsyncClient Initialization

**Issue**: AsyncClient initialization should mirror the sync Client pattern.

**Sync Agent** (lines 99-108 in agent.py):
```python
api_key = os.environ.get("OLLAMA_API_KEY")
if api_key:
    self._client = Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"}
    )
else:
    base_url = loaded_config.backend.ollama.base_url
    self._client = Client(host=base_url)
```

**AsyncAgent Pattern**:
```python
from ollama import AsyncClient

api_key = os.environ.get("OLLAMA_API_KEY")
if api_key:
    self._client = AsyncClient(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"}
    )
else:
    base_url = loaded_config.backend.ollama.base_url
    self._client = AsyncClient(host=base_url)
```

**Severity**: Low - Same pattern, just different class name.

---

#### 10. Error Handling Consistency

**Issue**: NetworkError handling in async context needs to match sync implementation.

**Sync Agent** (lines 273-287 in agent.py):
```python
except (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
) as e:
    raise NetworkError(f"Network error: {e}", original_error=e, recoverable=True) from e
```

**AsyncAgent Requirement**: Same exception handling for async streaming.

**Note**: httpx exceptions are the same for sync and async, so this should work identically.

**Severity**: Low - Same exception types apply.

---

## Public Interface Contract

### AsyncAgent Class

```python
class AsyncAgent:
    """Asynchronous agent that chats with Ollama and uses tools.
    
    This implementation uses composition with AgentCore for shared state.
    Identical public interface to Agent, but all I/O operations are async.
    
    Attributes:
        client: AsyncClient for Ollama API communication.
        model: Model to use for chat.
        config: Configuration object.
        context: ContextManager for conversation history.
        thinking_mode: Current thinking mode (on/off/silent).
        agent_definition: Loaded agent definition (if provided).
    """
    
    def __init__(
        self,
        model: str | None = None,
        config: Config | None = None,
        config_path: Path | str | None = None,
        thinking_mode: ThinkingMode = ThinkingMode.ON,
        command_registry: CommandRegistry | None = None,
        agent_definition: AgentDefinition | None = None,
        agent_path: Path | str | None = None,
        context_manager: ContextManager | None = None,
        _recursion_depth: int = 0,
    ) -> None: ...
    
    # Properties (identical to Agent)
    @property
    def config(self) -> Config: ...
    
    @property
    def model(self) -> str: ...
    
    @property
    def thinking_mode(self) -> ThinkingMode: ...
    
    @property
    def agent_definition(self) -> AgentDefinition | None: ...
    
    @property
    def tool_registry(self) -> ToolRegistry: ...
    
    @property
    def context(self) -> ContextManager: ...
    
    @property
    def command_registry(self) -> CommandRegistry | None: ...
    
    @property
    def client(self) -> AsyncClient: ...  # Different type than Agent
    
    # Event handler methods
    def add_event_handler(self, handler: EventCallback) -> None: ...
    
    def remove_event_handler(self, handler: EventCallback) -> None: ...
    
    # Core methods (async versions)
    async def process(self, message: str) -> str: ...
    
    async def begin_session(self) -> None: ...
    
    async def end_session(self, reason: str = "quit") -> None: ...
    
    # Internal methods
    async def _emit(self, event: Event) -> None: ...
```

### EventCallback Type

```python
# Sync callback
EventCallback = Callable[[Event], None]

# Also supports async callbacks (detected via asyncio.iscoroutinefunction)
# async def handler(event: Event) -> None: ...
```

---

## Implementation Recommendations

### 1. Error Handling in Event Emission

Add try/except around handler invocation:

```python
async def _emit(self, event: Event) -> None:
    for handler in self._core.get_event_handlers():
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception:
            log.exception(
                "event_handler_error",
                handler=handler.__name__,
                event_type=event.type,
            )
```

### 2. Context Manager Cleanup Verification

Verify that `BasicPersistenceContextManager.close()` is safe for async context:
- Check for blocking I/O operations
- Consider adding `close_async()` method if needed

### 3. AgentTool Compatibility

Verify that AgentTool.execute() works when spawned from AsyncAgent:
- AgentTool creates a sync Agent internally
- This is acceptable for MVP
- Future: Consider AsyncAgentTool for async subagent spawning

### 4. Documentation Update

Update `src/yoker/__init__.py` to export AsyncAgent:

```python
from yoker.agent import Agent
from yoker.async_agent import AsyncAgent

__all__ = ["Agent", "AsyncAgent"]
```

---

## Acceptance Criteria Verification

### From TODO.md (Task 1.7.3):

- [x] Create `src/yoker/async_agent.py` with AsyncAgent class
- [x] Update `src/yoker/__init__.py` to export AsyncAgent
- [x] Use AgentCore for shared state (composition)
- [x] Use `AsyncClient` from ollama library
- [x] Add property delegations to AgentCore (same as sync Agent)
- [x] Implement async `_emit()` supporting both sync and async handlers
- [ ] **Estimated time**: 2 hours
- [ ] **Satisfies**: FR2, FR5, FR6, FR7

**Requirements Mapping**:

| Requirement | Status | Notes |
|-------------|--------|-------|
| FR2: AsyncAgent class with async process() | Ready for implementation | Interface designed |
| FR5: AsyncClient from ollama | Ready for implementation | Pattern matches sync |
| FR6: Sync Agent uses Client | Already implemented | No changes needed |
| FR7: Async handlers support | Designed | `_emit()` handles both types |

---

## Breaking Changes

**None**. This is a new feature with no impact on existing sync Agent.

---

## Migration Considerations

### For Library Consumers

1. **Sync users**: No changes required. Continue using `from yoker import Agent`.

2. **Async users**: Import AsyncAgent:
   ```python
   from yoker import AsyncAgent
   
   agent = AsyncAgent(model="llama3.2")
   await agent.begin_session()
   response = await agent.process("Hello")
   await agent.end_session()
   ```

3. **Framework integration**:
   ```python
   # Quart/FastAPI
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

## Action Items

1. **Implement AsyncAgent class** (`src/yoker/async_agent.py`)
   - Follow the exact pattern from sync Agent
   - Use AsyncClient from ollama
   - Implement async `_emit()` with sync/async handler support
   - Add error handling in event emission

2. **Update package exports** (`src/yoker/__init__.py`)
   - Add `from yoker.async_agent import AsyncAgent`
   - Add to `__all__`

3. **Verify context cleanup**
   - Check `BasicPersistenceContextManager.close()` for blocking I/O
   - Document any async safety considerations

4. **Verify AgentTool compatibility**
   - Test that subagent spawning works from AsyncAgent
   - Document any limitations

5. **Write unit tests**
   - Test async process() with mock AsyncClient
   - Test async event emission with both handler types
   - Test async session lifecycle

---

## Conclusion

**Status**: Approved for Implementation

The AsyncAgent design is well-structured and follows established patterns (httpx). The composition with AgentCore is clean and eliminates code duplication. The async event emission design properly supports both sync and async handlers for backward compatibility.

**Key Points**:
1. Interface is identical to sync Agent (except return types are Awaitable)
2. Composition with AgentCore shares all state management
3. AsyncClient mirrors sync Client initialization pattern
4. Event handlers can be sync or async (detected at runtime)

**Implementation Time Estimate**: 2 hours (as specified in TODO.md)

**Next Steps**:
1. Implement AsyncAgent following the patterns documented here
2. Verify context cleanup safety
3. Test with both sync and async event handlers
4. Update documentation with async examples