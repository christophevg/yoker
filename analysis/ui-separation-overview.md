# UI Separation - Overview and Architecture

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Executive Summary

This document analyzes the current state of UI/logic entanglement in the Yoker codebase and proposes a clean separation architecture. The goal is to establish a clear boundary where:

- **Agent layer** is purely event-driven, raises exceptions, emits raw unformatted data (may contain ANSI from LLM)
- **UI layer** handles all presentation, input, error display, and formatting

This separation enables multiple UI implementations (interactive, batch, API, chat integration) while keeping the agent core reusable.

## Related Documents

- [IO Operations Catalog](./ui-separation-io-catalog.md) - Detailed inventory of all input/output operations
- [Error Handling Strategy](./ui-separation-errors.md) - Error handling catalog and strategy
- [Agent Module Refactoring](./ui-separation-agent-module.md) - Agent module split and context clarification
- [UI Handler Design](./ui-separation-ui-design.md) - UIHandler protocol and implementations
- [Migration Plan](./ui-separation-migration.md) - Step-by-step migration tasks

---

## 1. Current Architecture

### 1.1 Layer Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         __main__.py (Entry Point)                   │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Mixed Responsibilities:                                        ││
│  │  - CLI argument parsing (should stay)                           ││
│  │  - Agent creation (should stay)                                ││
│  │  - Interactive session loop (should move to UI)                ││
│  │  - Error handling with print statements (should move to UI)    ││
│  │  - Command dispatch (should move to UI)                        ││
│  │  - Network error handling (should move to UI)                  ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                              Agent                                  │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Current State:                                                  ││
│  │  - Event-driven (good!)                                        ││
│  │  - Emits events for all output (good!)                         ││
│  │  - Raises exceptions for errors (good!)                        ││
│  │  - No print statements in agent.py (good!)                     ││
│  │                                                                 ││
│  │ Issues:                                                         ││
│  │  - Single large file (~700 lines)                             ││
│  │  - Multiple responsibilities mixed                             ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ConsoleEventHandler                          │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Current State:                                                  ││
│  │  - Receives events and renders them (good!)                    ││
│  │  - Uses Rich console for output (works, but tied to Rich)      ││
│  │  - Contains formatting logic (should be extracted)              ││
│  │  - Contains print statements (50+ locations)                    ││
│  │                                                                 ││
│  │ Issues:                                                         ││
│  │  - Tied to Rich console implementation                          ││
│  │  - Cannot be swapped for batch mode                            ││
│  │  - Formatting logic embedded in handler                        ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Principles

1. **Agent Layer**: Pure event-driven, no UI dependencies
   - Raises exceptions on errors
   - Emits events with raw data (may contain ANSI from LLM)
   - No print statements
   - No UI formatting

2. **UI Layer**: All presentation logic
   - Receives events, formats output
   - Handles user input
   - Catches exceptions, displays errors
   - Decides streaming vs buffering

3. **Clean Break**: No backward compatibility
   - Full API redesign
   - Clean separation
   - No deprecation shims

---

## 2. Target Architecture

### 2.1 Layer Separation

```
┌─────────────────────────────────────────────────────────────────────┐
│                           UI Layer                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ InteractiveUI   │  │   BatchUI       │  │   APIUI / ChatUI    │ │
│  │ (prompt_toolkit) │  │ (stdin/stdout)  │  │   (events/JSON)      │ │
│  │ Rich formatting  │  │ Plain output    │  │   Structured output │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
│                              │                                      │
│                    UIHandler Protocol                               │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               │ Events (may contain ANSI) / Exceptions
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent Layer                                │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Agent                                                            ││
│  │  - Raises exceptions on errors                                   ││
│  │  - Emits events with raw data (may contain ANSI from LLM)       ││
│  │  - No print statements                                           ││
│  │  - No formatting                                                 ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                      │
│                          Events                                     │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ EventHandler Protocol                                            ││
│  │  - Receives events                                               ││
│  │  - No formatting responsibility                                  ││
│  │  - Passes raw data to registered handlers                       ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 ANSI Handling Strategy

| Source | Handling Strategy |
|--------|-------------------|
| **Tool output** | Tools produce plain text (use `--no-color` flags) |
| **LLM content** | Preserve ANSI, bubble to UI layer |
| **LLM thinking** | Preserve ANSI, bubble to UI layer |
| **UI elements** | No ANSI in events, formatted by UI |

**Principle**: Tools do everything possible to produce plain text. If output inherently contains ANSI (e.g., LLM output), preserve and let UI handle.

### 2.3 Content Type Strategy

Content types (MIME types) are only needed for events where the tool knows its output type:

**Events with content_type:**
- `ToolContentEvent` - Tool output (tools know their type: `text/plain`, `text/x-diff`, `application/json`)

**Events without content_type:**
- `ContentChunkEvent` - LLM output is unpredictable, chunks arrive streaming, content is often mixed (markdown with code blocks, plain text, etc.)
- `ThinkingChunkEvent` - Always thinking trace
- `ToolCallEvent` - Always structured data
- `ToolResultEvent` - Always result/status
- `SessionStartEvent`, etc. - Fixed structure

**LLM Content Handling:**
- Agent never sets content type on ContentChunkEvent
- UI implementations can optionally:
  - Buffer complete content
  - Sniff content type from full text (check for markdown markers, HTML tags, etc.)
  - Format accordingly

**Tool Content Handling:**
- Tools always set content type on ToolContentEvent
- UI can rely on this for formatting
- Known types: `text/plain`, `text/x-diff`, `application/json`

---

## 3. UI Use Cases

| Use Case | Input Method | Content Output | Thinking Output | Error Output | UI Handler |
|----------|--------------|----------------|-----------------|--------------|------------|
| Full Interactive | prompt_toolkit | Rich console | Rich console | Rich console | `InteractiveUIHandler` |
| Batch stdin | stdin | stdout | stderr | stderr | `BatchUIHandler` |
| Batch `--script` | file | stdout | stderr | stderr | `BatchUIHandler` |
| Batch `--prompt` | CLI arg | stdout | stderr | stderr | `BatchUIHandler` |
| Plugin/App | injected | events only | events only | exceptions | `EventHandler` (no UI) |
| API endpoint | HTTP request | JSON response | JSON response | HTTP error | `APIHandler` |
| Library integration | method calls | events | events | exceptions | Custom handler |
| yoker-chat | chat message | chat message | chat message | chat message | `ChatUIHandler` |

**Note**: Batch mode (stdin) already works via piping. The `--batch` flag is for explicit batch mode with additional options (e.g., `--show-thinking`).

---

## 4. Context and ContextManager

### 4.1 Key Concept: ContextManager is List-Like

The ContextManager is a drop-in replacement for a simple list. From the Agent's perspective, it's just:

```python
# Agent's view of context
self.context.append(message)      # Add message
messages = self.context            # Read for LLM
```

The Agent doesn't know about:
- Persistence
- Compaction
- Event subscription
- Any ContextManager internals

### 4.2 ContextManager as UserList

```python
from collections import UserList

class ContextManager(UserList):
    """Base context manager - acts like a list."""
    
    def append(self, message):
        super().append(message)
        # Extension point for subclasses


class PersistenceContextManager(ContextManager):
    """Context manager that persists to disk."""
    
    def append(self, message):
        super().append(message)
        self._persist()
    
    def _persist(self):
        # Write to disk
        ...
    
    def close(self):
        # Finalize persistence
        ...


class AdvancedContextManager(ContextManager):
    """Context manager with advanced features like compaction."""
    
    def append(self, message):
        super().append(message)
        # Could trigger compaction analysis
        ...
    
    def compact(self):
        # Remove old messages, summarize, etc.
        ...
```

### 4.3 Agent's Context Interface

```python
class Agent:
    def __init__(self, context: list | None = None):
        # context can be a plain list or any ContextManager
        self.context = context if context else []
    
    def process(self, message: str):
        # Append user message
        self.context.append({"role": "user", "content": message})
        
        # Get messages for LLM (just reads the list)
        messages = self.context
        
        # ... call LLM, get response ...
        
        # Append assistant message
        self.context.append({"role": "assistant", "content": response})
```

**Agent doesn't know:**
- About persistence
- About compaction
- About events (for context)
- About ContextManager internals

### 4.4 Composition Pattern

```python
# Simple in-memory context
agent = Agent()

# In-memory with compaction
agent = Agent(AdvancedContextManager())

# Persisted context
agent = Agent(PersistenceContextManager())

# Persisted with compaction
agent = Agent(PersistenceContextManager(
    inner=AdvancedContextManager()
))

# Sub-agent gets own context from factory
context_manager = session.create_context_manager()
sub_agent = Agent(context_manager)
```

### 4.5 Module Structure

```
yoker/
├── agent/
│   ├── agent.py          # Agent class
│   ├── core.py           # AgentCore
│   └── processing.py     # Message processing
├── context/
│   ├── __init__.py       # Exports ContextManager
│   ├── manager.py        # ContextManager (UserList base)
│   ├── basic.py          # BasicContextManager (in-memory)
│   ├── persistence.py    # PersistenceContextManager
│   └── advanced.py       # AdvancedContextManager (compaction)
```

### 4.6 What ContextManager Does NOT Do

- Does NOT subscribe to agent events
- Does NOT have session lifecycle
- Does NOT know about Session
- Does NOT have session ID (that's internal for persistence)

ContextManager is **transparent** to Agent. Agent just sees a list.

### 4.7 Persistence and Session ID

If ContextManager persists to disk, it may use a session ID internally:

```python
class PersistenceContextManager(ContextManager):
    def __init__(self, session_id: str | None = None):
        super().__init__()
        self.session_id = session_id or generate_uuid()
        self._load()  # Load existing messages if any
    
    def _persist(self):
        # Save to disk using session_id as filename
        path = Path(f".yoker/sessions/{self.session_id}.jsonl")
        ...
    
    def _load(self):
        # Load from disk if file exists
        ...
```

But Agent never sees or uses `session_id`. That's internal to ContextManager.

---

## 5. Key Decisions

### 5.1 Streaming vs Non-Streaming

**Question:** Should UI always receive streaming, or can it request buffered output?

**Analysis:**
- Backend (Ollama) streams by default
- Some UIs may want buffered output (e.g., API responses)
- Options:
  1. UI buffers internally (complexity in UI)
  2. Provide streaming control (complexity in agent)
  3. Default streaming, UI handles buffering if needed

**Decision:** Option 3 - Default streaming, UI handles buffering
- Agent always streams
- UI implementations can buffer if needed
- Simpler agent, flexible UI

### 5.2 Command Reusability

**Question:** Can other UI implementations reuse slash commands?

**Analysis:**
- Commands are UI-layer concerns
- Commands query agent state and output to UI
- Commands should be reusable across UI implementations

**Decision:** Commands are UI-layer, reusable
- Command registry lives in UI layer
- Commands receive UIHandler reference
- Commands call Agent API methods for data
- Different UI implementations can use same command logic

### 5.3 Error Handling

**Question:** Should errors be exceptions or events?

**Decision:** All errors are exceptions at agent layer
- Agent raises exceptions
- UI catches and displays
- No `ErrorEvent` needed (or convert for event-based handlers)

---

## 6. Agent Lifecycle (No Session)

### 6.1 No Agent-Level Session

**Decision:** Agent does NOT have session lifecycle methods.

**Removed:**
- `begin_session()` - No longer needed
- `end_session()` - No longer needed
- `SessionStartEvent` - May be added later at Session level
- `SessionEndEvent` - May be added later at Session level

**Agent lifecycle is simply:**
```python
agent = Agent(context=[])
# ... use agent ...
# Done - no explicit lifecycle
```

**Context persistence is handled by ContextManager:**
```python
# If persistence needed
context = PersistenceContextManager(session_id="abc123")
agent = Agent(context=context)
# ... use agent ...
# ContextManager persists automatically on append()
context.close()  # Finalize persistence
```

### 6.2 Why No Session?

Session implies multi-agent orchestration, which is:
- A future feature
- Should wrap Agent, not be inside Agent
- Session will manage multiple agents

Current migration focuses on:
- Single-agent use cases
- UI separation
- ContextManager as list-like

---

## 7. Future Extensions

### 7.1 Session (Multi-Agent Orchestration)

**Future:** A Session class that wraps multiple agents.

```python
Session (Agent-like interface)
  ├── process(message) → routes to root-agent
  ├── list_agents() → returns agent IDs
  ├── get_agent_info(id) → agent details
  ├── pause() → wait for in-flight, then block new
  ├── resume() → unblock
  └── close() → terminate
  
  Internal:
  ├── Agent registry (ID → Agent)
  ├── ID generator
  └── Event router (Agent events → UI)
```

**Key features:**
- Creates root-agent automatically
- Injects `AgentTool` and `SendMessageToAgentTool` into agents
- Routes events from agents to UI
- Manages agent lifecycle

**Agent is Session-agnostic:**
- Agent doesn't know about Session
- Agent just uses tools (including AgentTool)
- Tools have back-reference to Session internally

### 7.2 Advanced Context Management

**Future:** ContextManagers with advanced features:

```python
# Compaction
class CompactingContextManager(ContextManager):
    def compact(self):
        # Remove old messages, summarize
        ...

# Composition
context = PersistenceContextManager(
    inner=CompactingContextManager()
)
```

### 7.3 Clevis Top-Level Commands

**Future consideration:** Introducing top-level Clevis-supported commands like `yoker run <plugin>`.

---

## 8. Migration Order

**This migration:**
1. ✅ Refactor ContextManager to be list-like (UserList)
2. ✅ Separate UI from Agent
3. ✅ Remove Agent-level session (begin_session/end_session)
4. ✅ Agent raises exceptions, UI catches
5. ✅ Agent emits events, UI receives

**Future (not this migration):**
1. ❌ Session class for multi-agent orchestration
2. ❌ AgentTool, SendMessageToAgentTool
3. ❌ Advanced ContextManagers (compaction, etc.)
4. ❌ Top-level Clevis commands

---

## Next Steps

1. Review [IO Operations Catalog](./ui-separation-io-catalog.md)
2. Review [Error Handling Strategy](./ui-separation-errors.md)
3. Review [Agent Module Refactoring](./ui-separation-agent-module.md)
4. Review [UI Handler Design](./ui-separation-ui-design.md)
5. Review [Migration Plan](./ui-separation-migration.md)

---

**End of Document**

