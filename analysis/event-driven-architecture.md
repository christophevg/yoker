# Event-Driven Architecture Design

**Document Version**: 1.0
**Date**: 2026-04-20
**Status**: Architecture Proposal

## Executive Summary

This document proposes an event-driven architecture refactor for the Yoker Agent class. The current implementation couples the core agent logic with Rich console output, making the library unsuitable for headless, web, or GUI contexts. This refactor separates concerns by introducing an event emission pattern that allows application layers to subscribe and handle UI independently.

## Problem Statement

### Current Coupling Issues

The `Agent` class in `src/yoker/agent.py` has UI logic baked into its core:

```python
class Agent:
  def __init__(self, ..., console: Console | None = None, ...):
    self.console = console if console is not None else Console()  # UI dependency
  
  def _print_wrapped(self, text: str, style: Style | None = None, ...):
    self.console.print(...)  # Direct console output
  
  def process(self, message: str) -> str:
    # Thinking output
    self._print_wrapped("\n[Thinking]\n", style=THINKING_STYLE)
    self._print_wrapped(chunk.message.thinking, style=THINKING_STYLE)
    # Content output
    self._print_wrapped(chunk.message.content)
  
  def start(self, get_input: Callable[[str], str] | None = None):
    self.console.print(f"Yoker v0.1.0 - Using model: {self.model}")
    # ... more console output
```

### Consequences

1. **Not reusable**: Cannot use Agent in web servers, GUI apps, or headless scripts
2. **Not testable**: Tests must mock or capture console output
3. **Not flexible**: Output format is hardcoded (Rich with specific styling)
4. **Architecture violation**: Library layer depends on presentation layer

### Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                        │
│                    (__main__.py)                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                ConsoleEventHandler                       │ │
│  │  - Subscribes to Agent events                            │ │
│  │  - Renders to Rich console                               │ │
│  │  - Handles streaming, styling, wrapping                  │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ events
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Library Layer                         │
│                    (Agent class)                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Agent                                 │ │
│  │  - Pure event emission (no console)                     │ │
│  │  - Backend communication                                 │ │
│  │  - Tool execution                                        │ │
│  │  - Context management                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Event Types

### 1.1 Event Taxonomy

Events are organized into categories based on when they occur in the agent lifecycle:

| Category | Events | Description |
|----------|--------|-------------|
| **Session** | `session_start`, `session_end` | Agent lifecycle |
| **Turn** | `turn_start`, `turn_end` | User message to response cycle |
| **Thinking** | `thinking_start`, `thinking_chunk`, `thinking_end` | LLM reasoning trace |
| **Content** | `content_start`, `content_chunk`, `content_end` | LLM response text |
| **Tool** | `tool_call`, `tool_result` | Tool execution lifecycle |
| **Error** | `error` | Error conditions |

### 1.2 Event Definitions

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum, auto


class EventType(Enum):
  """Enumeration of all event types."""
  
  # Session lifecycle
  SESSION_START = auto()
  SESSION_END = auto()
  
  # Turn lifecycle
  TURN_START = auto()
  TURN_END = auto()
  
  # Thinking (reasoning trace)
  THINKING_START = auto()
  THINKING_CHUNK = auto()
  THINKING_END = auto()
  
  # Content (response text)
  CONTENT_START = auto()
  CONTENT_CHUNK = auto()
  CONTENT_END = auto()
  
  # Tool execution
  TOOL_CALL = auto()
  TOOL_RESULT = auto()
  
  # Error
  ERROR = auto()


@dataclass(frozen=True)
class Event:
  """Base event class with common fields."""
  
  type: EventType
  timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SessionStartEvent(Event):
  """Emitted when agent session starts."""
  
  model: str
  thinking_enabled: bool
  config_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionEndEvent(Event):
  """Emitted when agent session ends."""
  
  reason: str  # "quit", "error", "interrupt"


@dataclass(frozen=True)
class TurnStartEvent(Event):
  """Emitted when processing a user message begins."""
  
  message: str


@dataclass(frozen=True)
class TurnEndEvent(Event):
  """Emitted when processing a user message completes."""
  
  response: str
  tool_calls_count: int = 0


@dataclass(frozen=True)
class ThinkingStartEvent(Event):
  """Emitted when thinking output begins."""
  
  pass


@dataclass(frozen=True)
class ThinkingChunkEvent(Event):
  """Emitted for each chunk of thinking output."""
  
  text: str


@dataclass(frozen=True)
class ThinkingEndEvent(Event):
  """Emitted when thinking output ends."""
  
  total_length: int


@dataclass(frozen=True)
class ContentStartEvent(Event):
  """Emitted when content output begins."""
  
  pass


@dataclass(frozen=True)
class ContentChunkEvent(Event):
  """Emitted for each chunk of content output."""
  
  text: str


@dataclass(frozen=True)
class ContentEndEvent(Event):
  """Emitted when content output ends."""
  
  total_length: int


@dataclass(frozen=True)
class ToolCallEvent(Event):
  """Emitted when a tool is called."""
  
  tool_name: str
  arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResultEvent(Event):
  """Emitted when a tool returns a result."""
  
  tool_name: str
  result: str
  success: bool = True


@dataclass(frozen=True)
class ErrorEvent(Event):
  """Emitted when an error occurs."""
  
  error_type: str
  message: str
  details: dict[str, Any] = field(default_factory=dict)
```

### 1.3 Event Flow Diagram

```
User Input: "Hello"
    │
    ▼
┌─────────────────────┐
│ SESSION_START       │ ← Once per session
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ TURN_START          │ ← Per user message
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ THINKING_START      │ ← If thinking enabled
└─────────────────────┘
    │
    ▼ (multiple)
┌─────────────────────┐
│ THINKING_CHUNK      │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ THINKING_END        │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ CONTENT_START       │
└─────────────────────┘
    │
    ▼ (multiple)
┌─────────────────────┐
│ CONTENT_CHUNK       │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ CONTENT_END         │
└─────────────────────┘
    │
    ▼ (if tool calls)
┌─────────────────────┐
│ TOOL_CALL           │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ TOOL_RESULT         │
└─────────────────────┘
    │ (loop back to THINKING_START if more turns)
    ▼
┌─────────────────────┐
│ TURN_END            │
└─────────────────────┘
    │
    ▼ (on quit)
┌─────────────────────┐
│ SESSION_END         │
└─────────────────────┘
```

---

## 2. Event System Design

### 2.1 Design Requirements

| Requirement | Solution |
|-------------|----------|
| **Type-safe** | Use `dataclass` events with `Event` base class |
| **Pythonic** | Callback-based, no external dependencies |
| **Simple** | No EventEmitter class, direct callback registration |
| **Flexible** | Support multiple subscribers |
| **Async-compatible** | Support both sync and async callbacks |

### 2.2 Callback Protocol

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class EventHandler(Protocol):
  """Protocol for event handlers."""
  
  def __call__(self, event: Event) -> None:
    """Handle an event."""
    ...
```

### 2.3 Agent Interface (Proposed)

```python
from typing import Callable

# Type alias for clarity
EventCallback = Callable[[Event], None]


class Agent:
  """Event-driven agent that emits events during processing."""
  
  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
    thinking_enabled: bool = True,
    command_registry: "CommandRegistry | None" = None,
  ) -> None:
    """Initialize the agent without UI dependencies."""
    # ... configuration setup (unchanged)
    
    # Event handlers storage
    self._event_handlers: list[EventCallback] = []
    
  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler.
    
    Args:
      handler: Callable that receives Event objects.
    
    Example:
      def my_handler(event: Event):
        if isinstance(event, ContentChunkEvent):
          print(event.text, end='', flush=True)
      
      agent.add_event_handler(my_handler)
    """
    self._event_handlers.append(handler)
  
  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler."""
    self._event_handlers.remove(handler)
  
  def _emit(self, event: Event) -> None:
    """Emit an event to all registered handlers."""
    for handler in self._event_handlers:
      handler(event)
  
  def process(self, message: str) -> str:
    """Process a single message and return the response.
    
    Emits events during processing:
    - TURN_START
    - THINKING_START/CHUNK/END (if enabled)
    - CONTENT_START/CHUNK/END
    - TOOL_CALL/RESULT (if tools called)
    - TURN_END
    
    Args:
      message: User message to process.
    
    Returns:
      Assistant's response text.
    """
    self._emit(TurnStartEvent(type=EventType.TURN_START, message=message))
    self.messages.append({"role": "user", "content": message})
    
    while True:
      stream = self.client.chat(
        model=self.model,
        messages=self.messages,
        tools=list(self.tools.values()),
        think=self.thinking_enabled,
        stream=True,
      )
      
      content = ""
      thinking = ""
      tool_calls: list[Any] = []
      in_thinking = False
      in_content = False
      
      for chunk in stream:
        # Handle thinking output
        if chunk.message.thinking:
          if not in_thinking and self.thinking_enabled:
            in_thinking = True
            self._emit(ThinkingStartEvent(type=EventType.THINKING_START))
          thinking += chunk.message.thinking
          if self.thinking_enabled:
            self._emit(
              ThinkingChunkEvent(
                type=EventType.THINKING_CHUNK,
                text=chunk.message.thinking,
              )
            )
        
        # Handle content output
        if chunk.message.content:
          if in_thinking and self.thinking_enabled:
            in_thinking = False
            self._emit(
              ThinkingEndEvent(
                type=EventType.THINKING_END,
                total_length=len(thinking),
              )
            )
          if not in_content:
            in_content = True
            self._emit(ContentStartEvent(type=EventType.CONTENT_START))
          content += chunk.message.content
          self._emit(
            ContentChunkEvent(
              type=EventType.CONTENT_CHUNK,
              text=chunk.message.content,
            )
          )
        
        # Handle tool calls
        if chunk.message.tool_calls:
          tool_calls.extend(chunk.message.tool_calls)
      
      # End content if we were streaming
      if in_content:
        self._emit(
          ContentEndEvent(
            type=EventType.CONTENT_END,
            total_length=len(content),
          )
        )
      elif in_thinking and self.thinking_enabled:
        # No content, but thinking ended
        self._emit(
          ThinkingEndEvent(
            type=EventType.THINKING_END,
            total_length=len(thinking),
          )
        )
      
      # Build assistant message
      assistant_message: dict[str, Any] = {"role": "assistant"}
      if thinking:
        assistant_message["thinking"] = thinking
      if content:
        assistant_message["content"] = content
      if tool_calls:
        assistant_message["tool_calls"] = tool_calls
      
      self.messages.append(assistant_message)
      
      # If no tool calls, we're done
      if not tool_calls:
        self._emit(
          TurnEndEvent(
            type=EventType.TURN_END,
            response=content,
            tool_calls_count=len(tool_calls),
          )
        )
        return content
      
      # Process tool calls
      for call in tool_calls:
        tool_name = call.function.name
        tool_args = call.function.arguments
        
        self._emit(
          ToolCallEvent(
            type=EventType.TOOL_CALL,
            tool_name=tool_name,
            arguments=tool_args,
          )
        )
        
        logger.info(f"Tool call: {tool_name}({tool_args})")
        
        try:
          result = self.tools[tool_name](**tool_args)
          success = True
        except KeyError:
          result = f"Error: Unknown tool '{tool_name}'"
          success = False
        except Exception as e:
          result = f"Error executing tool: {e}"
          success = False
        
        logger.info(f"Tool result: {result[:100]}...")
        
        self._emit(
          ToolResultEvent(
            type=EventType.TOOL_RESULT,
            tool_name=tool_name,
            result=str(result),
            success=success,
          )
        )
        
        self.messages.append(
          {
            "role": "tool",
            "name": tool_name,
            "content": str(result),
          }
        )
  
  def start(self, get_input: Callable[[str], str] | None = None) -> None:
    """Start the interactive chat loop.
    
    Emits:
    - SESSION_START at the beginning
    - SESSION_END when quitting
    - All events from process() during each turn
    
    Args:
      get_input: Optional function to get user input.
    """
    if get_input is None:
      get_input = default_prompt
    
    self._emit(
      SessionStartEvent(
        type=EventType.SESSION_START,
        model=self.model,
        thinking_enabled=self.thinking_enabled,
      )
    )
    
    try:
      while True:
        try:
          user_input = get_input("> ")
        except EOFError:
          self._emit(
            SessionEndEvent(
              type=EventType.SESSION_END,
              reason="quit",
            )
          )
          break
        except KeyboardInterrupt:
          self._emit(
            SessionEndEvent(
              type=EventType.SESSION_END,
              reason="interrupt",
            )
          )
          break
        
        if not user_input.strip():
          continue
        
        # Check for commands
        if self.command_registry and user_input.startswith("/"):
          result = self.command_registry.dispatch(user_input)
          # Command results could be emitted as a special event
          # For now, let handlers decide how to display
          continue
        
        self.process(user_input)
    
    except Exception as e:
      self._emit(
        ErrorEvent(
          type=EventType.ERROR,
          error_type=type(e).__name__,
          message=str(e),
        )
      )
      raise
```

---

## 3. Console Event Handler

### 3.1 Rich Console Handler Implementation

```python
"""Console event handler for Rich output."""

from rich.console import Console
from rich.style import Style

from yoker.events import (
  Event,
  EventType,
  SessionStartEvent,
  SessionEndEvent,
  TurnStartEvent,
  TurnEndEvent,
  ThinkingStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ContentStartEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ToolCallEvent,
  ToolResultEvent,
  ErrorEvent,
)


# Styles
THINKING_STYLE = Style(color="bright_black", dim=True)
ERROR_STYLE = Style(color="red", bold=True)
TOOL_STYLE = Style(color="yellow")


class ConsoleEventHandler:
  """Handles events by rendering to Rich console."""
  
  def __init__(
    self,
    console: Console | None = None,
    show_thinking: bool = True,
    show_tool_calls: bool = True,
    wrap_width: int | None = None,
  ) -> None:
    """Initialize the console handler.
    
    Args:
      console: Rich console (default: new Console).
      show_thinking: Whether to display thinking output.
      show_tool_calls: Whether to display tool call info.
      wrap_width: Optional width for wrapping streaming output.
    """
    self.console = console if console is not None else Console()
    self.show_thinking = show_thinking
    self.show_tool_calls = show_tool_calls
    self.wrap_width = wrap_width
    
    # State for wrapping
    self._column = 0
  
  def __call__(self, event: Event) -> None:
    """Handle an event."""
    handler = getattr(self, f"_handle_{event.type.name.lower()}", None)
    if handler is not None:
      handler(event)
  
  def _handle_session_start(self, event: SessionStartEvent) -> None:
    self.console.print(f"Yoker v0.1.0 - Using model: {event.model}")
    thinking_status = "enabled" if event.thinking_enabled else "disabled"
    self.console.print(f"Thinking mode: {thinking_status} (use /think on|off to toggle)")
    self.console.print("Type /help for available commands.")
    self.console.print("Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")
  
  def _handle_session_end(self, event: SessionEndEvent) -> None:
    self.console.print("\nGoodbye!")
  
  def _handle_turn_start(self, event: TurnStartEvent) -> None:
    # User input is already displayed by the input function
    pass
  
  def _handle_turn_end(self, event: TurnEndEvent) -> None:
    # Add blank line after response
    self.console.print()
  
  def _handle_thinking_start(self, event: ThinkingStartEvent) -> None:
    if self.show_thinking:
      self._print_wrapped("\n[Thinking]\n", style=THINKING_STYLE)
  
  def _handle_thinking_chunk(self, event: ThinkingChunkEvent) -> None:
    if self.show_thinking:
      self._print_wrapped(event.text, style=THINKING_STYLE)
  
  def _handle_thinking_end(self, event: ThinkingEndEvent) -> None:
    if self.show_thinking:
      self._print_wrapped("\n\n[Response]\n")
  
  def _handle_content_start(self, event: ContentStartEvent) -> None:
    pass  # Content starts immediately
  
  def _handle_content_chunk(self, event: ContentChunkEvent) -> None:
    self._print_wrapped(event.text)
  
  def _handle_content_end(self, event: ContentEndEvent) -> None:
    self.console.print()  # Final newline
  
  def _handle_tool_call(self, event: ToolCallEvent) -> None:
    if self.show_tool_calls:
      self.console.print(
        f"\n[Tool Call] {event.tool_name}({event.arguments})",
        style=TOOL_STYLE,
      )
  
  def _handle_tool_result(self, event: ToolResultEvent) -> None:
    if self.show_tool_calls:
      status = "success" if event.success else "failed"
      preview = event.result[:100] + "..." if len(event.result) > 100 else event.result
      self.console.print(
        f"[Tool Result] {status}: {preview}",
        style=TOOL_STYLE,
      )
  
  def _handle_error(self, event: ErrorEvent) -> None:
    self.console.print(
      f"\n[Error] {event.error_type}: {event.message}",
      style=ERROR_STYLE,
    )
  
  def _print_wrapped(
    self,
    text: str,
    style: Style | None = None,
    end: str = "",
  ) -> None:
    """Print text with optional wrapping at wrap_width."""
    if self.wrap_width is None:
      self.console.print(text, style=style, end=end)
      return
    
    for char in text:
      if char == "\n":
        self._column = 0
      elif char == "\r":
        self._column = 0
      elif self._column >= self.wrap_width:
        self.console.print()
        self._column = 0
      
      self.console.print(char, style=style, end="")
      self._column += 1
    
    if end:
      self.console.print(end, style=style, end="")
```

### 3.2 Integration in __main__.py

```python
# In main()
from yoker.agent import Agent
from yoker.events import ConsoleEventHandler

# Create agent
agent = Agent(model=args.model, config=config)

# Create command registry
command_registry = create_command_registry(agent)
agent.command_registry = command_registry

# Create and attach console handler
console_handler = ConsoleEventHandler(
  show_thinking=True,
  show_tool_calls=True,
)
agent.add_event_handler(console_handler)

# Start agent
agent.start(get_input=get_input)
```

---

## 4. Alternative Consumers

### 4.1 Headless (No Output)

```python
from yoker.agent import Agent

agent = Agent(config=config)
# No handlers = no output

response = agent.process("What is 2+2?")
print(f"Response: {response}")
```

### 4.2 JSON Output (for APIs)

```python
import json
from yoker.agent import Agent
from yoker.events import Event, ContentChunkEvent

class JSONEventHandler:
  def __init__(self):
    self.chunks = []
  
  def __call__(self, event: Event):
    if isinstance(event, ContentChunkEvent):
      self.chunks.append(event.text)

agent = Agent(config=config)
handler = JSONEventHandler()
agent.add_event_handler(handler)

response = agent.process("Hello")
print(json.dumps({
  "response": response,
  "streamed_chunks": len(handler.chunks),
}))
```

### 4.3 WebSockets (for Web Apps)

```python
from yoker.agent import Agent
from yoker.events import Event

class WebSocketEventHandler:
  def __init__(self, websocket):
    self.websocket = websocket
  
  def __call__(self, event: Event):
    # Serialize event to JSON and send
    import json
    data = {
      "type": event.type.name,
      "timestamp": event.timestamp.isoformat(),
      **{
        k: v for k, v in event.__dict__.items()
        if k not in ("type", "timestamp")
      }
    }
    # asyncio.run(self.websocket.send(json.dumps(data)))
    print(f"Would send to WebSocket: {data}")

# Usage in FastAPI/FastHTML route
agent = Agent(config=config)
agent.add_event_handler(WebSocketEventHandler(websocket))
await agent.process_async(user_message)
```

### 4.4 Logging Handler

```python
import logging
from yoker.agent import Agent
from yoker.events import Event, ToolCallEvent, ToolResultEvent

logger = logging.getLogger(__name__)

class LoggingEventHandler:
  def __call__(self, event: Event):
    if isinstance(event, ToolCallEvent):
      logger.info(f"Tool called: {event.tool_name}({event.arguments})")
    elif isinstance(event, ToolResultEvent):
      logger.debug(f"Tool result: {event.result[:100]}...")

agent = Agent(config=config)
agent.add_event_handler(LoggingEventHandler())
```

### 4.5 Statistics Collector

```python
from yoker.agent import Agent
from yoker.events import Event, ThinkingEndEvent, ContentEndEvent, ToolResultEvent

class StatisticsCollector:
  def __init__(self):
    self.thinking_chars = 0
    self.content_chars = 0
    self.tool_calls = 0
    self.tool_successes = 0
  
  def __call__(self, event: Event):
    if isinstance(event, ThinkingEndEvent):
      self.thinking_chars += event.total_length
    elif isinstance(event, ContentEndEvent):
      self.content_chars += event.total_length
    elif isinstance(event, ToolResultEvent):
      self.tool_calls += 1
      if event.success:
        self.tool_successes += 1
  
  def get_stats(self):
    return {
      "thinking_chars": self.thinking_chars,
      "content_chars": self.content_chars,
      "tool_calls": self.tool_calls,
      "tool_success_rate": (
        self.tool_successes / self.tool_calls if self.tool_calls else 0
      ),
    }

agent = Agent(config=config)
stats = StatisticsCollector()
agent.add_event_handler(stats)

agent.process("Hello")
print(stats.get_stats())
```

---

## 5. Migration Strategy

### 5.1 Phase 1: Add Event Module (Non-Breaking)

1. Create `src/yoker/events/__init__.py` with event types
2. Add `add_event_handler`, `remove_event_handler`, `_emit` to Agent
3. Keep `console` parameter for backward compatibility
4. Agent still works without handlers (no output)

### 5.2 Phase 2: Refactor Agent.process() (Breaking)

1. Remove `console` parameter from `__init__`
2. Remove `_print_wrapped` method
3. Replace all console.print with `_emit` calls
4. Update `start()` to emit session events

### 5.3 Phase 3: Update __main__.py

1. Import `ConsoleEventHandler`
2. Create handler and attach to agent
3. Remove any direct console output from main

### 5.4 Phase 4: Remove Legacy Code

1. Delete deprecated `console`-related code
2. Update tests to use event handlers
3. Update documentation

### 5.5 Backward Compatibility

For users who relied on `Agent(console=...)`:

```python
# Before (v0.1.x)
agent = Agent(console=my_console)

# After (v0.2.x)
from yoker.events import ConsoleEventHandler

agent = Agent()
handler = ConsoleEventHandler(console=my_console)
agent.add_event_handler(handler)
```

---

## 6. File Structure

### Proposed Package Structure

```
src/yoker/
  events/
    __init__.py           # Public API: all event classes + handler protocol
    types.py              # Event dataclasses
    handlers.py           # Built-in handlers (ConsoleEventHandler)
```

### events/__init__.py

```python
"""Event system for Yoker agents."""

from yoker.events.types import (
  Event,
  EventType,
  SessionStartEvent,
  SessionEndEvent,
  TurnStartEvent,
  TurnEndEvent,
  ThinkingStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ContentStartEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ToolCallEvent,
  ToolResultEvent,
  ErrorEvent,
)
from yoker.events.handlers import (
  ConsoleEventHandler,
  EventHandler,
)

__all__ = [
  # Base
  "Event",
  "EventType",
  "EventHandler",
  # Session
  "SessionStartEvent",
  "SessionEndEvent",
  # Turn
  "TurnStartEvent",
  "TurnEndEvent",
  # Thinking
  "ThinkingStartEvent",
  "ThinkingChunkEvent",
  "ThinkingEndEvent",
  # Content
  "ContentStartEvent",
  "ContentChunkEvent",
  "ContentEndEvent",
  # Tool
  "ToolCallEvent",
  "ToolResultEvent",
  # Error
  "ErrorEvent",
  # Handlers
  "ConsoleEventHandler",
]
```

---

## 7. Testing Strategy

### 7.1 Event Emission Tests

```python
import pytest
from yoker.agent import Agent
from yoker.events import Event, ContentChunkEvent, ToolCallEvent


class EventCollector:
  def __init__(self):
    self.events = []
  
  def __call__(self, event: Event):
    self.events.append(event)


def test_process_emits_content_events():
  agent = Agent(model="test-model")
  collector = EventCollector()
  agent.add_event_handler(collector)
  
  response = agent.process("Hello")
  
  # Should have at least TURN_START, CONTENT_*, TURN_END
  assert len(collector.events) >= 4
  assert any(isinstance(e, ContentChunkEvent) for e in collector.events)


def test_process_emits_tool_events(mocker):
  # Mock the ollama client to return a tool call
  agent = Agent(model="test-model")
  collector = EventCollector()
  agent.add_event_handler(collector)
  
  # ... mock tool call scenario
  
  assert any(isinstance(e, ToolCallEvent) for e in collector.events)
```

### 7.2 Handler Tests

```python
from io import StringIO
from rich.console import Console
from yoker.events import (
  ContentChunkEvent,
  EventType,
  ConsoleEventHandler,
)


def test_console_handler_prints_content():
  output = StringIO()
  console = Console(file=output, force_terminal=False)
  handler = ConsoleEventHandler(console=console)
  
  handler(ContentChunkEvent(
    type=EventType.CONTENT_CHUNK,
    text="Hello",
  ))
  
  assert "Hello" in output.getvalue()
```

---

## 8. Open Questions

### 8.1 Async Support

**Question**: Should handlers support async callbacks?

**Options**:
1. **Sync only** (MVP): Simpler, works for most cases
2. **Async support**: Add `_emit_async` method for async handlers

**Recommendation**: Start with sync only. Add async support in Phase 1 if needed for web use cases.

### 8.2 Event Filtering

**Question**: Should handlers be able to filter by event type?

**Options**:
1. **Manual filtering**: Handlers check `isinstance(event, ...)`
2. **Decorator-based**: `@agent.on(ContentChunkEvent)`
3. **Registration by type**: `agent.add_handler(ContentChunkEvent, handler)`

**Recommendation**: Manual filtering for MVP (simplest). Add decorator-based filtering in Phase 1.

### 8.3 Command Results

**Question**: How should command results (from `/help`, etc.) be handled?

**Options**:
1. **Emit as events**: Add `CommandEvent` type
2. **Direct handling**: Commands handled separately from agent events
3. **Leave to application**: Commands handled in `__main__.py`

**Recommendation**: Direct handling in `__main__.py` for MVP (commands are CLI-specific).

---

## 9. Success Criteria

| Metric | Target |
|--------|--------|
| Agent has no UI dependencies | `console` parameter removed |
| Events cover all output | Thinking, content, tools covered |
| Console works via handler | `__main__.py` uses `ConsoleEventHandler` |
| Headless mode works | No handlers = no output |
| Tests pass | All event and handler tests pass |
| Backward compat documented | Migration guide in docs |

---

## 10. Implementation Order

1. **Create `events/types.py`**: Define all event dataclasses
2. **Create `events/handlers.py`**: Define `ConsoleEventHandler`
3. **Create `events/__init__.py`**: Export public API
4. **Update `agent.py`**: Add `_emit`, `_event_handlers`, update `process()` and `start()`
5. **Update `__main__.py`**: Create and attach `ConsoleEventHandler`
6. **Remove legacy code**: Delete `console` parameter and `_print_wrapped`
7. **Add tests**: Event emission and handler tests
8. **Update documentation**: Document new event system

---

## Appendix A: Full Event Type Reference

| Event | Fields | When Emitted |
|-------|--------|--------------|
| `SessionStartEvent` | `model`, `thinking_enabled`, `config_summary` | Agent starts |
| `SessionEndEvent` | `reason` | Agent quits |
| `TurnStartEvent` | `message` | User message received |
| `TurnEndEvent` | `response`, `tool_calls_count` | Response complete |
| `ThinkingStartEvent` | (none) | Thinking begins |
| `ThinkingChunkEvent` | `text` | Thinking chunk received |
| `ThinkingEndEvent` | `total_length` | Thinking ends |
| `ContentStartEvent` | (none) | Content begins |
| `ContentChunkEvent` | `text` | Content chunk received |
| `ContentEndEvent` | `total_length` | Content ends |
| `ToolCallEvent` | `tool_name`, `arguments` | Tool called |
| `ToolResultEvent` | `tool_name`, `result`, `success` | Tool returned |
| `ErrorEvent` | `error_type`, `message`, `details` | Error occurred |

---

## Appendix B: Comparison with Other Patterns

| Pattern | Pros | Cons | Used In |
|---------|------|------|---------|
| **Callback-based** (proposed) | Simple, no deps, type-safe | Manual registration | Many Python libs |
| **Observer** | Classic pattern | More boilerplate | Java-style code |
| **EventEmitter** | Flexible, powerful | External dep needed | Node.js style |
| **Signals/Slots** | Decoupled | Complex setup | Qt, PySignal |
| **Generator/Yield** | Native streaming | Not for all events | Async iteration |

**Choice**: Callback-based for simplicity, Pythonic style, and zero dependencies.