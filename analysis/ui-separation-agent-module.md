# UI Separation - Agent Module Refactoring

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Overview

This document details the refactoring of the `agent.py` module into a focused `agent/` package.

---

## 1. Current Structure

### 1.1 `agent.py` (~700 lines)

**Responsibilities:**
- Initialization and configuration (lines 70-208)
- Property accessors (lines 209-280)
- Event handler management (lines 281-317)
- Message processing loop (lines 366-653)
- ~~Session lifecycle (lines 654-701)~~ **REMOVED**

### 1.2 `base.py` (~430 lines)

**Contents:**
- `AgentCore` class with shared state
- Tool registry building (`_build_tool_registry`)
- Guardrail validation
- Event handler storage

---

## 2. Target Structure

### 2.1 Module Organization

```
yoker/
├── agent/
│   ├── __init__.py          # Public API: Agent, AgentCore
│   ├── core.py              # AgentCore (from base.py)
│   ├── agent.py             # Agent class (initialization, properties)
│   ├── processing.py        # process() method and streaming logic
│   └── tools.py             # _build_tool_registry
├── base.py                   # REMOVED
└── agent.py                  # REMOVED
```

**No backward compatibility shims.** Clean break.

### 2.2 Module Responsibilities

| Module | Responsibility | Lines (Est.) |
|--------|----------------|--------------|
| `core.py` | AgentCore state, event handlers, validation | ~250 |
| `agent.py` | Agent class init, properties, public API | ~150 |
| `processing.py` | Message processing, streaming, tool calls | ~300 |
| `tools.py` | Tool registry building | ~80 |

**Note:** No `session.py` - Agent does NOT have session lifecycle.

---

## 3. Context and Agent Clarification

### 3.1 Context (Unchanged)

The `context/` module remains separate:

```
yoker/
├── context/
│   ├── __init__.py           # Exports ContextManager
│   ├── manager.py            # ContextManager (UserList base)
│   ├── basic.py              # BasicContextManager (in-memory)
│   ├── persistence.py        # PersistenceContextManager
│   └── advanced.py           # AdvancedContextManager (compaction)
```

### 3.2 ContextManager is List-Like

From the Agent's perspective, `context` is just a list:

```python
class Agent:
    def __init__(self, context: list | None = None):
        self.context = context if context else []
    
    async def process(self, message: str):
        self.context.append({"role": "user", "content": message})
        # ... call LLM ...
        self.context.append({"role": "assistant", "content": response})
```

**ContextManager implementations:**
- `BasicContextManager` - Just a list (default)
- `PersistenceContextManager` - Saves to disk
- `AdvancedContextManager` - Compaction, etc.

### 3.3 Agent Doesn't Know About Session

**No Agent-level session:**
- No `begin_session()` / `end_session()`
- No SessionStartEvent / SessionEndEvent (at Agent level)
- Agent lifecycle is simple: create → use → discard

**Context persistence:**
- Handled by `PersistenceContextManager`
- Agent just sees `context.append()`
- ContextManager handles persistence internally

---

## 4. Detailed Module Contents

### 4.1 `agent/core.py`

**Contents:**
- `AgentCore` class (moved from `base.py`)
- Event handler management
- Guardrail validation
- Tool registry building (or move to `tools.py`)

**Public API:**
```python
class AgentCore:
    config: Config
    model: str
    thinking_mode: ThinkingMode
    agent_definition: AgentDefinition | None
    tool_registry: ToolRegistry
    context: ContextManager  # List-like, transparent
    skill_registry: SkillRegistry | None
    
    def add_event_handler(self, handler: EventCallback) -> None: ...
    def remove_event_handler(self, handler: EventCallback) -> None: ...
    def get_event_handlers(self) -> list[EventCallback]: ...
```

### 4.2 `agent/agent.py`

**Contents:**
- `Agent` class (orchestration)
- Initialization
- Property accessors
- Public API

**Public API:**
```python
class Agent:
    def __init__(
        self,
        config: Config | None = None,
        thinking_mode: ThinkingMode = ThinkingMode.ON,
        agent_definition: AgentDefinition | None = None,
        agent_path: Path | str | None = None,
        context: list | ContextManager | None = None,  # List-like
    ) -> None: ...
    
    # Properties (delegate to AgentCore)
    @property
    def config(self) -> Config: ...
    @property
    def model(self) -> str: ...
    @property
    def thinking_mode(self) -> ThinkingMode: ...
    @property
    def context(self) -> list: ...  # List-like
    # ... other properties
    
    # Public methods
    async def process(self, message: str) -> str: ...
    def inject_skill_context(self, skill_name: str, args: str | None = None) -> None: ...
    def add_event_handler(self, handler: EventCallback) -> None: ...
```

**Note:** No `begin_session()` or `end_session()` methods.

### 4.3 `agent/processing.py`

**Contents:**
- `process()` method
- Streaming logic
- Tool call handling
- Event emission

**Internal structure:**
```python
# In Agent class
async def process(self, message: str) -> str:
    """Process a single message and return the response.
    
    Emits events during processing.
    Raises exceptions on errors.
    """
    log.info("turn_started", message_preview=message[:50])
    await self._emit(TurnStartEvent(...))
    self.context.append({"role": "user", "content": message})
    
    # Streaming and tool handling
    while True:
        stream = await self._client.chat(
            model=self.model,
            messages=self.context,  # Just the list
            ...
        )
        # ... streaming logic
    
    self.context.append({"role": "assistant", "content": response})
    return content
```

### 4.4 `agent/tools.py`

**Contents:**
- `_build_tool_registry()` method
- Tool initialization logic

**Internal to Agent:**
```python
def _build_tool_registry(
    config: Config,
    guardrail: PathGuardrail,
    agent_definition: AgentDefinition | None,
    client: AsyncClient | None,
) -> ToolRegistry:
    """Build a tool registry filtered by agent definition.
    
    Args:
        config: Configuration object.
        guardrail: Path guardrail for filesystem tools.
        agent_definition: Agent definition (filters tools).
        client: AsyncClient for web tools.
    
    Returns:
        ToolRegistry with available tools.
    """
    registry = ToolRegistry()
    
    # Create tools with guardrail
    tools = [
        ReadTool(guardrail=guardrail),
        ListTool(guardrail=guardrail),
        # ... other tools
    ]
    
    # Filter by agent definition
    if agent_definition:
        allowed = {t.lower() for t in agent_definition.tools}
        tools = [t for t in tools if t.name.lower() in allowed]
    
    for tool in tools:
        registry.register(tool)
    
    return registry
```

---

## 5. Migration Steps

### 5.1 Create Package

1. Create `yoker/agent/` directory
2. Create `agent/__init__.py` with public API exports

### 5.2 Move Files

1. Move `base.py` → `agent/core.py`
2. Extract from `agent.py`:
   - Init and properties → `agent/agent.py`
   - Processing logic → `agent/processing.py`
   - Tool registry → `agent/tools.py`
3. **Remove** `begin_session()` and `end_session()` methods
4. **Remove** SessionStartEvent and SessionEndEvent (at Agent level)

### 5.3 Update ContextManager

1. Refactor `ContextManager` to extend `UserList`
2. Update `PersistenceContextManager` to persist on `append()`
3. Agent uses `context` as a plain list

### 5.4 Update Imports

1. Update `yoker/__init__.py`:
   ```python
   from yoker.agent import Agent, AgentCore
   from yoker.context import ContextManager, PersistenceContextManager
   ```

2. Update all imports throughout codebase

### 5.5 Remove Old Files

1. Delete `yoker/base.py`
2. Delete `yoker/agent.py`
3. Remove session-related events from `events/types.py` (at Agent level)

---

## 6. Testing Focus

### 6.1 Test Functionality, Not Structure

Focus tests on:
- Agent processes messages correctly
- Tool calls work
- Events are emitted correctly
- Exceptions are raised appropriately
- Context appends correctly
- ContextManager persists correctly

### 6.2 Don't Test

- Module structure (implementation detail)
- Import paths (refactor may change)

---

## 7. Summary

### 7.1 Key Changes

- `agent.py` (700 lines) → `agent/` package (4 modules, no session)
- `base.py` → `agent/core.py`
- No Agent-level session (begin/end methods removed)
- ContextManager is list-like (UserList)
- Context stays separate in `context/` module

### 7.2 Benefits

- Smaller, focused modules
- Easier to navigate
- Clear responsibilities
- Better testability
- Simpler Agent interface (no session lifecycle)

---

**End of Document**

