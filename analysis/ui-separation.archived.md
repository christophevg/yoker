# UI Separation Analysis

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Executive Summary

This document analyzes the current state of UI/logic entanglement in the Yoker codebase and proposes a clean separation architecture. The goal is to establish a clear boundary where:

- **Agent layer** is purely event-driven, raises exceptions, emits raw unformatted data
- **UI layer** handles all presentation, input, error display, and formatting

This separation enables multiple UI implementations (interactive, batch, API, chat integration) while keeping the agent core reusable.

---

## 1. Current State Analysis

### 1.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         __main__.py (Entry Point)                   │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Mixed Responsibilities:                                        ││
│  │  - CLI argument parsing (should stay)                           ││
│  │  - Agent creation (should stay)                                ││
│  │  - Interactive session loop (should move to UI)                ││
│  │  - Error handling with print statements (should move to UI)    ││
│  │  - Command dispatch (should move to UI)                       ││
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
│  │  - Emits events for all output (good!)                        ││
│  │  - Raises exceptions for errors (good!)                        ││
│  │  - No print statements in agent.py (good!)                     ││
│  │                                                                 ││
│  │ Issues:                                                         ││
│  │  - Single large file (~700 lines)                              ││
│  │  - Multiple responsibilities mixed                              ││
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
│  │  - Formatting logic embedded in handler                         ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 IO Operations Catalog

#### Input Operations

| Location | Operation | Current Implementation | Batch Alternative |
|----------|-----------|------------------------|-------------------|
| `__main__.py:103` | User message input | `prompt_input_async()` via prompt_toolkit | stdin/file/CLI arg |
| `__main__.py:243` | Interactive prompt loop | `while True:` with `prompt_input_async()` | No loop, predefined messages |

#### Output Operations - Session Lifecycle

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `handlers.py:146-150` | Session start banner | Model name, version, thinking status | Console | `SessionStartEvent` |
| `handlers.py:154` | Session end message | "Goodbye" | Console | `SessionEndEvent` |

#### Output Operations - Turn Lifecycle

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `handlers.py:159-165` | Turn start | Reset flags, prepare for new turn | Internal | `TurnStartEvent` |
| `handlers.py:167-191` | Turn end | Stats (timing, tokens), cleanup | Console | `TurnEndEvent` |

#### Output Operations - Thinking Stream

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `handlers.py:193-213` | Thinking start | Separator, start LiveDisplay | Console | `ThinkingStartEvent` |
| `handlers.py:214-220` | Thinking chunk | Stream thinking text | Console | `ThinkingChunkEvent` |
| `handlers.py:222-227` | Thinking end | Newlines after thinking | Console | `ThinkingEndEvent` |

#### Output Operations - Content Stream

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `handlers.py:229-251` | Content start | Separator, start LiveDisplay | Console | `ContentStartEvent` |
| `handlers.py:253-258` | Content chunk | Stream response text | Console | `ContentChunkEvent` |
| `handlers.py:260-264` | Content end | Final newline | Console | `ContentEndEvent` |

#### Output Operations - Tool Execution

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `handlers.py:306-321` | Tool call | Tool name, arguments | Console | `ToolCallEvent` |
| `handlers.py:362-380` | Tool result | Success/failure status | Console | `ToolResultEvent` |
| `handlers.py:381-418` | Tool content | File content, diff display | Console | `ToolContentEvent` |

#### Output Operations - Errors

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `handlers.py:539-544` | Error event | Error type, message | Console | `ErrorEvent` |
| `handlers.py:546-549` | Command result | Command output | Console | `CommandEvent` |
| `__main__.py:287-291` | Network error | Network error message | Console | Caught exception |
| `__main__.py:318-322` | Recoverable error | Retry message | Console | Caught exception |
| `__main__.py:328-336` | Ollama error | API error message | Console | Caught exception |

#### Output Operations - Agent Info

| Location | Operation | Content | Destination | Event Type |
|----------|-----------|---------|-------------|-------------|
| `__main__.py:396-399` | Agent loaded | Agent name, description, tools | Console | None (direct print) |

### 1.3 Error Handling Catalog

#### Exception-Based (Good - Keep)

| Location | Error Type | Where Raised | Where Caught |
|----------|-----------|--------------|--------------|
| `agent.py:413-417` | `NetworkError` | `Agent.process()` | `__main__.py:316, 339` |
| `agent.py` | Various | Tool execution | `Agent.process()` catches and emits `ToolResultEvent` |

#### Event-Based (Review - Should These Be Exceptions?)

| Location | Event Type | Current Handling | Should Be Exception? |
|----------|-----------|------------------|---------------------|
| `agent.py:358-364` | Event emission error | Logged, handler continues | **No** - non-blocking, logged |
| Various | `ErrorEvent` | Emitted to handlers | **Review** - see below |

#### Mixed Pattern (Needs Clarification)

| Error Scenario | Current Behavior | Proposed Behavior |
|---------------|------------------|-------------------|
| Network failure | `NetworkError` exception → caught in `__main__` → print | Exception → UI catches → formats |
| Tool error | `ToolResultEvent(success=False)` → handler prints | Keep as event (tool result is data) |
| Ollama API error | `ResponseError` → caught in `__main__` → print | Exception → UI catches → formats |
| Agent not found | Logged warning, uses default | Keep as logged (non-critical) |

#### Error Messages Analysis

**In `__main__.py` (lines 287-336):**

```python
# Network errors - recoverable
print(f"\n[Network Error] {e}")
print("Your message was preserved. You can try again or type a new message.")

# Network errors - fatal
print(f"\n[Fatal Network Error] {e}")
print("Unable to recover. Please restart the session.")

# Ollama errors
print("\n[Error] Ollama server is overloaded. Please wait a moment and try again.")
print("\n[Error] Model not found. Check that the model is available.")
print("\n[Error] Authentication failed. Check your Ollama configuration.")
print(f"\n[Error] Ollama internal error: {e}")
print(f"\n[Error] Ollama error ({e.status_code}): {e}")
```

**In `handlers.py` (line 541-544):**

```python
self.console.print(
    f"\n[Error] {event.error_type}: {event.message}",
    style=ERROR_STYLE,
)
```

**Observations:**
- Error formatting is duplicated between `__main__.py` and `handlers.py`
- `ErrorEvent` exists but is only used in one location
- Network errors are caught in `__main__.py` and printed directly
- Need unified error handling strategy

### 1.4 Agent Module Analysis

#### Current File: `agent.py` (~700 lines)

**Responsibilities Mixed:**

| Lines | Responsibility | Should Be |
|-------|---------------|-----------|
| 70-208 | Initialization, config loading, tool registry | `agent.py` |
| 209-280 | Property accessors (model, thinking_mode, etc.) | `agent.py` |
| 281-317 | Event handler management | `agent/core.py` or `agent.py` |
| 366-653 | `process()` method - streaming, tool calls | `agent/processing.py` |
| 654-701 | Session lifecycle (begin_session, end_session) | `agent/session.py` |

#### Current File: `base.py` (~430 lines)

**Contents:**
- `AgentCore` class with shared state
- Tool registry building (`_build_tool_registry`)
- Guardrail validation
- Event handler storage

**Proposed:** Move to `agent/core.py`

#### Proposed Agent Module Structure

```
yoker/
├── agent/
│   ├── __init__.py          # Public API: Agent, AgentCore
│   ├── core.py              # AgentCore (from base.py)
│   ├── agent.py             # Agent class (initialization, properties)
│   ├── session.py           # begin_session, end_session
│   ├── processing.py        # process() method and helpers
│   └── tools.py             # _build_tool_registry
├── base.py                   # Deprecation shim: from agent import AgentCore
└── agent.py                  # Deprecation shim: from agent import Agent
```

> NOTE CVG: this migration will not implement backward compatibility, so no deprecation shims, only a clean post-migration result!

**Module Responsibilities:**

| Module | Responsibility | Lines (Est.) |
|--------|----------------|--------------|
| `core.py` | AgentCore state, event handlers, validation | ~250 |
| `agent.py` | Agent class, init, properties | ~150 |
| `session.py` | Session lifecycle, context management | ~50 |
| `processing.py` | Message processing, streaming, tool calls | ~300 |
| `tools.py` | Tool registry building | ~80 |

> NOTE CVG: I feel like there is a naming mixup between session and context. For me these are different things. Needs to be cleared up.

### 1.5 Current Content Types

#### Event Data Types (Raw, Unformatted)

| Event | Data Fields | Content Type |
|-------|-------------|--------------|
| `ContentChunkEvent` | `text: str` | `text/plain` (default) |
| `ThinkingChunkEvent` | `text: str` | `text/plain` |
| `ToolCallEvent` | `tool_name: str`, `arguments: dict` | Structured data |
| `ToolResultEvent` | `tool_name: str`, `result: str`, `success: bool` | Structured data |
| `ToolContentEvent` | `operation: str`, `path: str`, `content: str`, `content_type: str`, `metadata: dict` | Varies |

#### Tool Output Content Types

| Tool | Output | Current Format | Proposed MIME Type |
|------|--------|---------------|-------------------|
| `ReadTool` | File content | Raw text | `text/plain` (or detected) |
| `WriteTool` | Summary | Formatted string | `application/x-yoker-summary` |
| `UpdateTool` | Diff | Unified diff | `text/x-diff` |
| `GitTool` | Command output | Raw output | `text/plain` (with `--no-color`) |

#### ANSI Handling Current State

| Source | Current Handling | Proposed Handling |
|--------|-----------------|-------------------|
| Tool output (git, etc.) | Not controlled | Use `--no-color` in tools |
| LLM content | Passed through | Preserve, bubble to UI |
| LLM thinking | Passed through | Preserve, bubble to UI |
| UI elements | Formatted in handlers | No ANSI in events, UI formats |

---

## 2. Target Architecture Design

### 2.1 Layer Separation

```
┌─────────────────────────────────────────────────────────────────────┐
│                           UI Layer                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ InteractiveUI   │  │   BatchUI       │  │   APIUI / ChatUI     │ │
│  │ (prompt_toolkit) │  │ (stdin/stdout)  │  │   (events/JSON)      │ │
│  │ Rich formatting  │  │ Plain output    │  │   Structured output  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
│                              │                                      │
│                    UIHandler Protocol                               │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               │ Events / Exceptions
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent Layer                                │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ Agent                                                            ││
│  │  - Raises exceptions on errors                                   ││
│  │  - Emits events with raw, unformatted data                       ││
│  │  - No print statements                                           ││
│  │  - No ANSI codes in events                                       ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                      │
│                          Events                                     │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ EventHandler Protocol                                            ││
│  │  - Receives events                                               ││
│  │  - No formatting responsibility                                   ││
│  │  - Passes raw data to registered handlers                        ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

> NOTE CVG: "No ANSI codes in events" -> I don't think this is correct. The LLM can produce ANSI codes and therefore these will (optionally) be present in events emitted by the agent layer.

### 2.2 UI Use Cases

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

### 2.3 Content Type Strategy

#### MIME Types for Events

```python
# Standard MIME types
CONTENT_TYPE_TEXT_PLAIN = "text/plain"
CONTENT_TYPE_TEXT_MARKDOWN = "text/markdown"
CONTENT_TYPE_TEXT_HTML = "text/html"
CONTENT_TYPE_APPLICATION_JSON = "application/json"
CONTENT_TYPE_TEXT_DIFF = "text/x-diff"

# Yoker-specific MIME types
CONTENT_TYPE_YOKER_TOOL_CALL = "application/x-yoker-tool-call"
CONTENT_TYPE_YOKER_TOOL_RESULT = "application/x-yoker-tool-result"
CONTENT_TYPE_YOKER_THINKING = "application/x-yoker-thinking"
CONTENT_TYPE_YOKER_STATS = "application/x-yoker-stats"
CONTENT_TYPE_YOKER_ERROR = "application/x-yoker-error"
CONTENT_TYPE_YOKER_SUMMARY = "application/x-yoker-summary"
```

> NOTE CVG: the proposed Yoker-specific MIME types are not related to content, so don't require a mime-type. These have specific event types that make clear how to interprete their content. Content types should only be provided with events that provide "content" of which the content-type isn't known from the event signature. An event providing a Tool results can contain several types of tool call result content: the tool call result content can be plain text or a diff, or ...

#### Event Updates

```python
@dataclass(frozen=True)
class ContentChunkEvent(Event):
    type: EventType
    text: str
    content_type: str = CONTENT_TYPE_TEXT_PLAIN  # NEW: MIME type

@dataclass(frozen=True)
class ToolContentEvent(Event):
    tool_name: str
    operation: str
    path: str
    content: str | None
    content_type: str  # Already exists, clarify usage
    metadata: dict[str, Any]
```

#### ANSI Handling Strategy

```python
# In tools - strip ANSI at source
class GitTool:
    def execute(self, operation: str, ...):
        args = [operation, "--no-color", ...]  # Force no color
        result = self._run_git(args)
        return ToolResult(result=strip_ansi(result), ...)

# In agent - preserve LLM output as-is
# Events carry raw text, may contain ANSI from LLM

# In UI - handle based on environment
class InteractiveUIHandler:
    def stream_content(self, chunk: str, content_type: str):
        if content_type == CONTENT_TYPE_TEXT_MARKDOWN:
            self.console.print(Markdown(chunk))
        elif self._contains_ansi(chunk):
            self.console.print(chunk)  # Rich handles ANSI
        else:
            self.console.print(chunk)

class BatchUIHandler:
    def stream_content(self, chunk: str, content_type: str):
        sys.stdout.write(chunk)  # Preserve ANSI
```

### 2.4 Slash Commands Architecture

#### Command Responsibilities

| Command | Location | Agent Interaction | Output |
|---------|----------|-------------------|--------|
| `/help` | UI only | None | Command list |
| `/skills` | UI layer | `agent.skill_registry.list_skills()` | Skill list |
| `/context` | UI layer | `agent.context.get_statistics()` | Session info |
| `/think on\|off` | UI layer | `agent.thinking_mode = value` | Status |
| `/<skill-name>` | UI layer | `agent.inject_skill_context(name, args)` | None (process follows) |

#### New Agent Method: `inject_skill_context`

```python
class Agent:
    def inject_skill_context(self, skill_name: str, args: str | None = None) -> None:
        """Inject skill context into conversation.
        
        This is the same method used by SkillTool when the LLM invokes a skill.
        Called by UI when user runs /<skill-name> command.
        
        Args:
            skill_name: Name of the skill to inject.
            args: Optional arguments to pass to the skill.
        """
        skill = self._core.skill_registry.get(skill_name)
        if skill is None:
            raise ValueError(f"Unknown skill: {skill_name}")
        
        content = format_skill_content(skill, args)
        self._core.context.add_message("system", content)
```

### 2.5 Error Handling Strategy

#### Exception Hierarchy

```python
# Base exception for all Yoker errors
class YokerError(Exception):
    """Base exception for Yoker errors."""
    pass

# Network-related errors
class NetworkError(YokerError):
    """Network communication error."""
    def __init__(self, message: str, recoverable: bool = True, original_error: Exception | None = None):
        self.recoverable = recoverable
        self.original_error = original_error
        super().__init__(message)

# Tool execution errors
class ToolError(YokerError):
    """Tool execution error."""
    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(f"{tool_name}: {message}")

# Configuration errors
class ConfigError(YokerError):
    """Configuration error."""
    pass

# Agent errors
class AgentError(YokerError):
    """Agent-related error."""
    pass
```

#### Error Flow

```
Agent Layer                    UI Layer
    │                             │
    │ raise NetworkError          │
    │────────────────────────────>│
    │                             │ UIHandler.handle_error(exception)
    │                             │ Format and display error
    │                             │ Decide: continue or exit?
    │                             │
    │                             │ If continue: prompt for next input
    │                             │ If fatal: emit SessionEndEvent, exit
```

---

## 3. Proposed Implementation

### 3.1 UI Handler Protocol

```python
# yoker/ui/handler.py

from pathlib import Path
from typing import Protocol

class UIHandler(Protocol):
    """Abstract interface for all UI operations.
    
    All methods receive raw, unformatted data.
    Implementations are responsible for formatting and output.
    
    Input methods return None for no input (end of session).
    Output methods should handle ANSI codes appropriately for their context.
    """
    
    # === Lifecycle ===
    
    async def start(self, model: str, version: str, config: dict) -> None:
        """Start UI session. Called once at beginning.
        
        Args:
            model: Model name being used.
            version: Yoker version.
            config: Configuration summary.
        """
        ...
    
    async def shutdown(self, reason: str) -> None:
        """End UI session. Called once at end.
        
        Args:
            reason: Reason for ending ("quit", "error", "interrupt").
        """
        ...
    
    # === Input ===
    
    async def get_input(self, prompt: str = "> ") -> str | None:
        """Get user input.
        
        Args:
            prompt: Prompt string to display.
            
        Returns:
            User input string, or None if end of input (EOF).
        """
        ...
    
    # === Content Output (stdout in batch) ===

    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        """Output content text.
        
        Args:
            content: Content text (may contain ANSI from LLM).
            content_type: MIME type of content.
        """
        ...
    
    def output_command_result(self, result: str) -> None:
        """Output command result.
        
        Args:
            result: Command output text.
        """
        ...
    
    # === Diagnostic Output (stderr in batch) ===
    
    def output_thinking(self, text: str) -> None:
        """Output thinking/trace text.
        
        Args:
            text: Thinking text (may contain ANSI from LLM).
        """
        ...
    
    def output_tool_call(self, tool_name: str, args: dict) -> None:
        """Output tool call information.
        
        Args:
            tool_name: Name of tool being called.
            args: Tool arguments.
        """
        ...
    
    def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
        """Output tool result status.
        
        Args:
            tool_name: Name of tool.
            success: Whether tool succeeded.
            result: Result text or error message.
        """
        ...
    
    def output_tool_content(
        self,
        tool_name: str,
        operation: str,
        path: str,
        content: str | None,
        content_type: str,
        metadata: dict
    ) -> None:
        """Output tool content (file contents, diff, etc.).
        
        Args:
            tool_name: Name of tool.
            operation: Operation type (read, write, update, etc.).
            path: File path.
            content: Content text (may be None for summary).
            content_type: MIME type of content.
            metadata: Additional metadata (lines, bytes, etc.).
        """
        ...
    
    def output_stats(
        self,
        duration_ms: int,
        prompt_tokens: int,
        eval_tokens: int
    ) -> None:
        """Output turn statistics.
        
        Args:
            duration_ms: Duration in milliseconds.
            prompt_tokens: Number of prompt tokens.
            eval_tokens: Number of evaluation tokens.
        """
        ...
    
    def output_error(self, error: Exception) -> None:
        """Output error message.
        
        Args:
            error: Exception that occurred.
        """
        ...
    
    # === Streaming ===
    
    def start_content_stream(self) -> None:
        """Start streaming content."""
        ...
    
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        """Stream content chunk.
        
        Args:
            chunk: Content chunk (may contain ANSI from LLM).
            content_type: MIME type of content.
        """
        ...
    
    def end_content_stream(self, total_length: int) -> None:
        """End streaming content.
        
        Args:
            total_length: Total content length.
        """
        ...
    
    def start_thinking_stream(self) -> None:
        """Start streaming thinking."""
        ...
    
    def stream_thinking(self, chunk: str) -> None:
        """Stream thinking chunk.
        
        Args:
            chunk: Thinking chunk (may contain ANSI from LLM).
        """
        ...
    
    def end_thinking_stream(self, total_length: int) -> None:
        """End streaming thinking.
        
        Args:
            total_length: Total thinking length.
        """
        ...
```

### 3.2 Base UI Handler

> NOTE CVG: Something to consider: not all implementations will want streaming output, so although we might default on a streaming-backend interaction, we might have to buffer and only produce end-results for the front-end? Or will will, in that case, simply turn of streaming in the backend?

```python
# yoker/ui/base.py

from abc import ABC, abstractmethod
from typing import Any


class BaseUIHandler(ABC):
    """Base implementation with shared logic.
    
    Provides:
    - State management (current turn, streaming state)
    - Common formatting utilities

> NOTE CVG: Not sure if formatting already should be done at this level? This forces any actual UI implementation to these formatting choices. The proposed implementation is also so "light" that this doesn't add real value and can be done at the implementation side.

    - Default implementations for optional methods
    
    Subclasses implement:
    - Platform-specific output methods
    - Input handling
    - Error formatting
    """
    
    def __init__(self) -> None:
        self._turn_count = 0
        self._streaming_content = False
        self._streaming_thinking = False
        self._content_buffer: list[str] = []
        self._thinking_buffer: list[str] = []
    
    # === State Management ===
    
    def start_turn(self) -> None:
        """Start a new turn."""
        self._turn_count += 1
        self._streaming_content = False
        self._streaming_thinking = False
        self._content_buffer = []
        self._thinking_buffer = []
    
    def end_turn(self) -> None:
        """End current turn."""
        self._streaming_content = False
        self._streaming_thinking = False
    
    # === Formatting Utilities ===
    
    @staticmethod
    def format_tool_args(args: dict[str, Any]) -> str:
        """Format tool arguments for display.
        
        Args:
            args: Tool arguments.
            
        Returns:
            Formatted string.
        """
        # Subclasses can override for different formatting
        if not args:
            return ""
        return " ".join(f"{k}={v}" for k, v in list(args.items())[:3])
    
    @staticmethod
    def format_error(error: Exception) -> str:
        """Format error for display.
        
        Args:
            error: Exception to format.
            
        Returns:
            Formatted error string.
        """
        error_type = type(error).__name__
        return f"[{error_type}] {error}"
    
    # === Default Implementations ===
    
    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        """Default: output via streaming."""
        self.start_content_stream()
        self.stream_content(content, content_type)
        self.end_content_stream(len(content))
    
    def output_thinking(self, text: str) -> None:
        """Default: output via streaming."""
        self.start_thinking_stream()
        self.stream_thinking(text)
        self.end_thinking_stream(len(text))
    
    # === Abstract Methods ===
    
    @abstractmethod
    async def start(self, model: str, version: str, config: dict) -> None: ...
    
    @abstractmethod
    async def shutdown(self, reason: str) -> None: ...
    
    @abstractmethod
    async def get_input(self, prompt: str = "> ") -> str | None: ...
    
    # ... other abstract methods
```

### 3.3 Interactive UI Handler

```python
# yoker/ui/interactive.py

from pathlib import Path
from typing import Any

from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console
from rich.style import Style

from yoker.ui.base import BaseUIHandler
from yoker.ui.formatters import Formatter, RichFormatter


class InteractiveUIHandler(BaseUIHandler):
    """Interactive UI with prompt_toolkit input and Rich output.
    
    Features:
    - Multiline input (Esc+Enter for newline)
    - Command history
    - Rich console formatting
    - Live streaming display
    """
    
    def __init__(
        self,
        formatter: Formatter | None = None,
        history_file: Path | None = None,
        show_thinking: bool = True,
        show_tool_calls: bool = True,
    ) -> None:
        super().__init__()
        self.console = Console()
        self.formatter = formatter or RichFormatter(self.console)
        self.history_file = history_file or Path.home() / ".yoker_history"
        self.show_thinking = show_thinking
        self.show_tool_calls = show_tool_calls
        
        # Create prompt session
        self._session = self._create_session()
        self._live_display: LiveDisplay | None = None
    
    def _create_session(self) -> PromptSession[str]:
        """Create prompt session with multiline support."""
        kb = KeyBindings()
        
        @kb.add("enter")
        def _handle_enter(event: KeyPressEvent) -> None:
            event.current_buffer.validate_and_handle()
        
        @kb.add("escape", "enter")
        def _handle_meta_enter(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text("\n")
        
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        return PromptSession(
            history=FileHistory(str(self.history_file)),
            multiline=True,
            mouse_support=False,
            key_bindings=kb,
        )
    
    # === Lifecycle ===
    
    async def start(self, model: str, version: str, config: dict) -> None:
        self.console.print(f"Yoker v{version} - Using model: {model}")
        thinking_status = "enabled" if config.get("thinking_enabled", True) else "disabled"
        self.console.print(f"Thinking mode: {thinking_status} (use /think on|off to toggle)")
        self.console.print("Type /help for available commands.")
        self.console.print("Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")
    
    async def shutdown(self, reason: str) -> None:
        self.console.print("\nGoodbye!")
    
    # === Input ===
    
    async def get_input(self, prompt: str = "> ") -> str | None:
        try:
            result: str = await self._session.prompt_async(prompt)
            return result
        except EOFError:
            return None
        except KeyboardInterrupt:
            self.console.print()  # Newline after ^C
            return None
    
    # === Content Output ===
    
    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        self.formatter.format_content(content, content_type)
    
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        self.formatter.stream_content(chunk, content_type)
    
    # === Error Output ===
    
    def output_error(self, error: Exception) -> None:
        formatted = self.formatter.format_error(error)
        self.console.print(formatted, style=Style(color="red", bold=True))
    
    # ... other implementations
```

### 3.4 Batch UI Handler

```python
# yoker/ui/batch.py

import sys
from typing import Any

from yoker.ui.base import BaseUIHandler
from yoker.ui.formatters import Formatter, PlainFormatter


class BatchUIHandler(BaseUIHandler):
    """Batch UI for non-interactive execution.
    
    Output channels:
    - Content → stdout
    - Thinking, errors, stats → stderr
    
    Input:
    - From file (predefined messages)
    - From stdin (one message per line)
    - From CLI argument (--prompt)
    """
    
    def __init__(
        self,
        formatter: Formatter | None = None,
        show_thinking: bool = False,
        show_tool_calls: bool = False,
    ) -> None:
        super().__init__()
        self.formatter = formatter or PlainFormatter()
        self.show_thinking = show_thinking
        self.show_tool_calls = show_tool_calls
        
        # Predefined input source
        self._input_source: list[str] | None = None
        self._input_index = 0
    
    def set_input_messages(self, messages: list[str]) -> None:
        """Set predefined input messages.
        
        Args:
            messages: List of messages to process.
        """
        self._input_source = messages
        self._input_index = 0
    
    # === Lifecycle ===
    
    async def start(self, model: str, version: str, config: dict) -> None:
        # Minimal output for batch mode
        if self.show_thinking:
            print(f"# Model: {model}", file=sys.stderr)
    
    async def shutdown(self, reason: str) -> None:
        # No output for batch mode
        pass
    
    # === Input ===
    
    async def get_input(self, prompt: str = "> ") -> str | None:
        if self._input_source is not None:
            # Predefined messages
            if self._input_index >= len(self._input_source):
                return None
            message = self._input_source[self._input_index]
            self._input_index += 1
            return message
        else:
            # Read from stdin
            try:
                return input()
            except EOFError:
                return None
    
    # === Content Output (stdout) ===
    
    def output_content(self, content: str, content_type: str = "text/plain") -> None:
        print(content, file=sys.stdout)

> NOTE CVG: So, here I'd expect that batch-processing wouldn't want streaming content, so option 1) we require the batch-ui-handler to do the buffering here, or 2) we provide a way to control this in the base-ui-handler, making it available for all ui-handler implementations.
    
    def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        print(chunk, file=sys.stdout, end="", flush=True)
    
    def end_content_stream(self, total_length: int) -> None:
        print(file=sys.stdout)  # Final newline
    
    # === Diagnostic Output (stderr) ===
    
    def output_thinking(self, text: str) -> None:
        if self.show_thinking:
            print(f"# Thinking: {text}", file=sys.stderr)
    
    def stream_thinking(self, chunk: str) -> None:
        if self.show_thinking:
            print(chunk, file=sys.stderr, end="", flush=True)
    
    def output_tool_call(self, tool_name: str, args: dict) -> None:
        if self.show_tool_calls:
            print(f"# Tool: {tool_name}({self.format_tool_args(args)})", file=sys.stderr)
    
    def output_error(self, error: Exception) -> None:
        print(f"Error: {error}", file=sys.stderr)
    
    # ... other implementations
```

### 3.5 Formatter Protocol

```python
# yoker/ui/formatters/__init__.py

from abc import ABC, abstractmethod
from typing import Any


class Formatter(Protocol):
    """Abstract formatter for content display.
    
    Formatters handle the presentation layer:
    - Rich formatting for interactive
    - Plain text for batch
    - Markdown/HTML for other contexts
    """
    
    def format_content(self, content: str, content_type: str) -> None:
        """Format and output content.
        
        Args:
            content: Content to format.
            content_type: MIME type of content.
        """
        ...
    
    def stream_content(self, chunk: str, content_type: str) -> None:
        """Stream content chunk.
        
        Args:
            chunk: Content chunk.
            content_type: MIME type of content.
        """
        ...
    
    def format_tool_call(self, tool_name: str, args: dict[str, Any]) -> str:
        """Format tool call for display.
        
        Args:
            tool_name: Tool name.
            args: Tool arguments.
            
        Returns:
            Formatted string.
        """
        ...
    
    def format_error(self, error: Exception) -> str:
        """Format error for display.
        
        Args:
            error: Exception to format.
            
        Returns:
            Formatted error string.
        """
        ...
    
    def format_diff(self, diff: str, filename: str) -> str:
        """Format diff output.
        
        Args:
            diff: Unified diff content.
            filename: File name.
            
        Returns:
            Formatted diff string.
        """
        ...
    
    def format_file_content(self, content: str, filename: str, metadata: dict) -> str:
        """Format file content display.
        
        Args:
            content: File content.
            filename: File name.
            metadata: Metadata (lines, etc.).
            
        Returns:
            Formatted content string.
        """
        ...
```

---

## 4. Migration Plan

### 4.1 Phase 1: Foundation

**Goal:** Create UI module structure without breaking existing code.

**Tasks:**

1. **Create `yoker/ui/` module structure**
   - `__init__.py` - Public API exports
   - `handler.py` - UIHandler protocol
   - `base.py` - BaseUIHandler implementation
   - `formatters/__init__.py` - Formatter protocol

2. **Define UIHandler protocol**
   - Document all methods with type hints
   - Add docstrings with usage examples

3. **Define Formatter protocol**
   - Document formatting methods
   - Define MIME type constants

4. **Create deprecation plan for ConsoleEventHandler**
   - Mark as deprecated in docstring
   - Add deprecation warning in code

> NOTE CVG: we're not going to "waste" time on backward compatibility, no deprecation support/warning, only the pure resulting new API/structure/documentation. FULL CLEAN CLEAR CUT/BREAK, everywhere.

### 4.2 Phase 2: Extract Formatters

**Goal:** Extract formatting logic from ConsoleEventHandler.

**Tasks:**

1. **Create `formatters/rich_formatter.py`**
   - Move formatting logic from ConsoleEventHandler
   - Implement Formatter protocol
   - Use Rich console for output

2. **Create `formatters/plain_formatter.py`**
   - Implement plain text formatting
   - No ANSI codes, minimal formatting
   - Use for batch mode

3. **Update ConsoleEventHandler to use Formatter**
   - Replace direct console.print calls
   - Delegate to formatter methods
   - Maintain backward compatibility

> NOTE CVG: NO backward compatibility!

### 4.3 Phase 3: Create UI Handlers

**Goal:** Create InteractiveUIHandler and BatchUIHandler.

**Tasks:**

1. **Create `ui/interactive.py`**
   - Move input handling from `__main__.py`
   - Move session loop from `__main__.py`
   - Implement UIHandler protocol

2. **Create `ui/batch.py`**
   - Implement stdin/file/CLI arg input
   - Implement stdout/stderr output split
   - Implement UIHandler protocol

3. **Create `ui/event_adapter.py`**
   - Bridge between EventHandler protocol and UIHandler
   - Receive events, call UIHandler methods
   - Handle error events

> NOTE CVG: call this "ui/brigde.py"

### 4.4 Phase 4: Move Slash Commands

**Goal:** Move slash command logic to UI layer.

**Tasks:**

1. **Create `ui/commands/` directory**
   - Move command handlers from `__main__.py`
   - Each command in its own file
   - Commands call Agent API methods

2. **Add `Agent.inject_skill_context()` method**
   - Same method used by SkillTool
   - Called by `/<skill-name>` command

3. **Update command registry**
   - Commands receive UIHandler reference
   - Commands call Agent methods for data

> NOTE CVG: So this new architecture implies that other UI implementations can reuse the commands (and UI slash-commands are merely a UI text entry triggering the command execution)?

### 4.5 Phase 5: Refactor Agent Module

**Goal:** Split agent.py into focused modules.

**Tasks:**

1. **Create `yoker/agent/` package**
   - Move `base.py` to `agent/core.py`
   - Create `agent/__init__.py` with public API
   - Create deprecation shims in old locations

2. **Split `agent.py`**
   - `agent/agent.py` - Agent class (init, properties)
   - `agent/session.py` - Session lifecycle
   - `agent/processing.py` - Message processing
   - `agent/tools.py` - Tool registry building

> NOTE CVG: we need to clarify session <-> context

3. **Update imports throughout codebase**
   - Update `__init__.py` files
   - Update tests
   - Update documentation

> NOTE CVG: Focus should be on testing the agent modules/classes, not on the UI parts, testing formatting is wasted testing. We need to focus on testing functionality, not output/formatting details.

### 4.6 Phase 6: Update Entry Points

**Goal:** Update `__main__.py` and add batch mode entry point.

**Tasks:**

1. **Refactor `__main__.py`**
   - Thin dispatcher
   - Create UIHandler based on mode
   - Run appropriate session

2. **Add CLI arguments for batch mode**
   - `--batch` - Batch mode (stdin/stdout)
   - `--script FILE` - Script mode
   - `--prompt TEXT` - Single prompt mode

> NOTE CVG: this includes the introduction of top-level Clevis-supported commands. We need to analyze the full scope here in more detail. This is not part of this migration, this is a future extension.

> NOTE CVG: I think that batchmode is a default that already works, since reading from stdin includes piping a file to it?


3. **Create entry point for plugin/app mode**
   - `yoker run <plugin>` - Execute plugin

> NOTE CVG: this includes the introduction of top-level Clevis-supported commands. We need to analyze the full scope here in more detail. This is not part of this migration, this is a future extension.

### 4.7 Phase 7: Testing and Documentation

**Goal:** Ensure all modes work correctly.

**Tasks:**

1. **Add tests for UIHandler implementations**
   - Test InteractiveUIHandler
   - Test BatchUIHandler
   - Test Formatter implementations

2. **Add tests for batch mode**
   - Test stdin input
   - Test file input
   - Test CLI arg input
   - Test stdout/stderr output

3. **Update documentation**
   - Document UIHandler protocol
   - Document Formatter protocol
   - Document batch mode usage
   - Document plugin/app mode

---

## 5. Open Questions

### 5.1 Context Module Location

**Question:** Where should `agent/context.py` go?

**Options:**
- A) Context initialization code from `Agent.__init__` in `agent/context.py`
- B) Keep `context/` separate, `agent/context.py` doesn't exist
- C) Move `context/` into `agent/` as `agent/context/`

**Recommendation:** Option B - Keep `context/` separate. Context management is a distinct concern.

> NOTE CVG: Oh, I see the context module is already a module with multiple modules below it.

> NOTE CVG: To consider: We now have a basic context manager. A more advanced context manager (in the future, not part of this migration) would for example change the context based on certain events. So it will probably also subscribe to the agent's events. E.g. working prototype idea - this needs to be substantiated with research - when inserting a skill, this results in the effect of that skill being added to the context - that is normal. Now, a more advanced context manager would for example remove the inserted skill, only keeping the result, to avoid over and over sending of that skill, while only the result is useful.  We need to think this, and other uses cases, through to determine the interaction with/dependency on the agent to define how distinct the context is. For example: can an agent live without context manager? Can some implementation just instanticate an Agent() and not have anything from the context/ module? If the agent includes the context, I feel it belongs inside the agent/ module as `agent/context`. To be discussed.

### 5.2 ANSI Handling in Tools

**Question:** Should all tools strip ANSI, or only those that might produce it?

**Options:**
- A) All tools strip ANSI (simpler, consistent)
- B) Only tools that might produce ANSI (more precise)

**Recommendation:** Option B - Only `GitTool` and similar. Add `strip_ansi()` utility.

> NOTE CVG: At most option B. It would rephrase this to: tools do everything they can to produce as plain-text as possible output. If the output inherently IS using ansi codes, then these can't be stripped.

### 5.3 Content Type Detection

**Question:** Should `ReadTool` detect content type automatically?

**Options:**
- A) Always return `text/plain` (simplest)
- B) Detect from file extension (more useful)
- C) Detect from file content (most accurate)

**Recommendation:** Option B - Detect from extension, fallback to `text/plain`.

> NOTE CVG: If we can use an existing library for it: Option C + fallback to Option B and fallback to Option A.

### 5.4 Error Event vs Exception

**Question:** Should all errors be exceptions, or should some be `ErrorEvent`?

**Analysis:**
- **Exceptions:** Network errors, tool errors (recoverable by agent), config errors
- **Events:** None - all errors should be exceptions at agent layer

**Recommendation:** All errors are exceptions at agent layer. UI layer catches and displays.

> NOTE CVG: Exceptions

---

## 6. Implementation Checklist

### Phase 1: Foundation
- [ ] Create `yoker/ui/__init__.py`
- [ ] Create `yoker/ui/handler.py` (UIHandler protocol)
- [ ] Create `yoker/ui/base.py` (BaseUIHandler)
- [ ] Create `yoker/ui/formatters/__init__.py` (Formatter protocol)
- [ ] Add content type constants (MIME types)
- [ ] Add deprecation warning to ConsoleEventHandler

### Phase 2: Extract Formatters
- [ ] Create `yoker/ui/formatters/rich_formatter.py`
- [ ] Create `yoker/ui/formatters/plain_formatter.py`
- [ ] Move formatting logic from ConsoleEventHandler
- [ ] Add `strip_ansi()` utility function
- [ ] Update tools to use `--no-color` flags

### Phase 3: Create UI Handlers
- [ ] Create `yoker/ui/interactive.py`
- [ ] Create `yoker/ui/batch.py`
- [ ] Create `yoker/ui/event_adapter.py`
- [ ] Move input handling from `__main__.py`
- [ ] Move session loop from `__main__.py`

### Phase 4: Move Slash Commands
- [ ] Create `yoker/ui/commands/__init__.py`
- [ ] Create command handler files
- [ ] Add `Agent.inject_skill_context()` method
- [ ] Update command registry to use UIHandler

### Phase 5: Refactor Agent Module
- [ ] Create `yoker/agent/__init__.py`
- [ ] Create `yoker/agent/core.py` (from base.py)
- [ ] Create `yoker/agent/agent.py`
- [ ] Create `yoker/agent/session.py`
- [ ] Create `yoker/agent/processing.py`
- [ ] Create `yoker/agent/tools.py`
- [ ] Update imports

### Phase 6: Update Entry Points
- [ ] Refactor `__main__.py`
- [ ] Add `--batch` CLI argument
- [ ] Add `--script` CLI argument
- [ ] Add `--prompt` CLI argument
- [ ] Test all modes

### Phase 7: Testing and Documentation
- [ ] Add UIHandler tests
- [ ] Add BatchUIHandler tests
- [ ] Add Formatter tests
- [ ] Update documentation
- [ ] Update README.md

---

## 7. Notes

### 7.1 Backward Compatibility

- Keep `ConsoleEventHandler` working during migration
- Add deprecation warnings gradually
- Remove old code only after new code is stable

### 7.2 Performance Considerations

- Streaming must remain efficient
- No string copying in hot paths
- Batch mode should be fast (no UI overhead)

### 7.3 Future Extensions

- `ChatUIHandler` for yoker-chat integration
- `APIHandler` for HTTP/REST API
- `WebUIHandler` for web interface
- Custom formatters via configuration

---

## 8. References

- Current architecture: `src/yoker/agent.py`, `src/yoker/__main__.py`
- Event system: `src/yoker/events/`
- Demo script: `scripts/demo_session.py` (batch mode example)
- Commands: `src/yoker/commands/`

---

**End of Document**

