# API Analysis: Logging System

**Document Version**: 1.0
**Date**: 2026-04-22
**Task**: 1.5 Logging System from TODO.md
**Status**: Architecture Review

## Summary

This analysis reviews the logging system requirements against the current implementation. The project has two distinct systems that need clarification:

1. **Event System** (already implemented) - Domain events for UI output and session recording
2. **Structured Logging** (TODO task) - Operational logging for debugging and monitoring

The TODO task "1.5 Logging System" asks for `structlog` integration, but the codebase already has an event-based architecture for session recording. This analysis clarifies the relationship and provides API design recommendations.

---

## 1. Current State Assessment

### 1.1 Event System (Implemented)

The `src/yoker/events/` module provides a complete event-driven architecture:

| Component | File | Purpose |
|-----------|------|---------|
| `Event` types | `types.py` | Dataclasses for all event types |
| `EventHandler` | `handlers.py` | Protocol for event consumers |
| `ConsoleEventHandler` | `handlers.py` | Renders events to Rich console |
| Event emission | `agent.py` | Agent emits events during processing |

**Event Types**:
- Session lifecycle: `SESSION_START`, `SESSION_END`
- Turn lifecycle: `TURN_START`, `TURN_END`
- Thinking: `THINKING_START`, `THINKING_CHUNK`, `THINKING_END`
- Content: `CONTENT_START`, `CONTENT_CHUNK`, `CONTENT_END`
- Tools: `TOOL_CALL`, `TOOL_RESULT`
- Commands: `COMMAND`
- Errors: `ERROR`

**Key Characteristics**:
- Domain-focused (what happened in the agent session)
- Emitted by Agent to registered handlers
- Handlers decide what to do (console output, file logging, etc.)
- Events are data-rich (timestamps, event-specific payload)

### 1.2 Event Logger (Implemented)

The `src/yoker/logging/` module provides session recording:

| Component | File | Purpose |
|-----------|------|---------|
| `EventLogger` | `event_logger.py` | Writes all events to JSONL |
| `EventReplayAgent` | `event_replay.py` | Replays sessions from JSONL |
| Serialization | `event_logger.py` | Event <-> dict conversion |

**Key Characteristics**:
- Records complete session for replay
- JSONL format (one JSON object per line)
- Used for demos, debugging, testing
- Part of the event handling system

### 1.3 Structured Logging (Not Implemented)

The TODO task requests:

```
- [ ] **1.5 Logging System**
  - Integrate structlog for structured logging
  - Add file and console handlers
  - Log tool calls and guardrail decisions
  - Add timing information for performance tracking
```

**What This Means**:

| Requirement | Current Status |
|-------------|----------------|
| structlog integration | Not implemented (using standard `logging`) |
| File handlers | EventLogger writes JSONL, but no general log file |
| Console handlers | ConsoleEventHandler outputs to Rich console |
| Tool call logging | Logged via events, not structlog |
| Guardrail decisions | Not implemented (guardrails don't exist yet) |
| Timing information | Not tracked |

### 1.4 Architecture Vision

From `analysis/architecture.md`, the Support Layer should include:

```
Support Layer
  [Logging] [Reporting] [Statistics Collector]
```

The architecture specifies:
- `src/yoker/logging.py` - Structured logging setup (single file, not a module)
- `src/yoker/statistics.py` - Token and time tracking

**Important Note**: The architecture shows `logging.py` as a single file, but the current implementation has `logging/` as a module. This needs resolution.

---

## 2. Systems Clarification

### 2.1 Event System vs Logging System

| Aspect | Event System | Logging System |
|--------|--------------|----------------|
| **Purpose** | Domain events for UI/recording | Operational logs for debugging |
| **Audience** | Users, session replay | Developers, operators |
| **Content** | What happened in session | System state, decisions, metrics |
| **Format** | Typed dataclasses | Structured key-value logs |
| **Storage** | JSONL for replay | Log files (text/JSON) |
| **Example** | `ToolCallEvent(tool_name="read", args={...})` | `log.info("tool_executed", tool="read", duration_ms=45)` |

### 2.2 Relationship

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Agent Execution                                │
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │                     Event Emission (Domain)                       │ │
│   │                                                                    │ │
│   │   Agent.emit(event) ───────┬───────────────────────────────────┐  │ │
│   │                            │                                    │  │ │
│   │   Events:                  │                                    │  │ │
│   │   - SESSION_START/END      │                                    │  │ │
│   │   - TURN_START/END         ▼                                    │  │ │
│   │   - THINKING_*/CONTENT_*  ConsoleEventHandler ──► Rich Console  │  │ │
│   │   - TOOL_CALL/RESULT                                          │  │ │
│   │   - COMMAND/ERROR         EventLogger ──► session.jsonl        │  │ │
│   │                                                                    │ │
│   └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │                   Structured Logging (Infrastructure)             │ │ │
│   │                                                                    │ │
│   │   log.info("session_started", model="llama3.2") ──► stdout/file   │ │
│   │   log.debug("tool_call", tool="read", file="test.py")             │ │
│   │   log.warning("guardrail_blocked", rule="allowed_paths")          │ │
│   │   log.info("turn_complete", duration_ms=1234, tokens=456)        │ │
│   │                                                                    │ │
│   └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.3 What Goes Where

**Event System** (already implemented):
- User-visible session flow
- Session recording for replay
- UI updates (thinking, content streaming)
- Tool call notifications
- Error display to user

**Logging System** (to implement):
- Internal state changes
- Guardrail decisions (when implemented)
- Performance metrics (timing, token counts)
- Debug information
- Operational warnings/errors

---

## 3. API Design Recommendations

### 3.1 Logging Module API

**Recommendation**: Rename `logging/` module to `events/` (already exists) and create a new `logging.py` file for structlog.

**Rationale**: 
- Architecture shows `logging.py` as single file
- Current `logging/` module is really about event persistence/replay
- Clearer separation of concerns

**Proposed Structure**:

```
src/yoker/
  events/              # Domain events (already exists)
    __init__.py
    types.py
    handlers.py
  logging.py           # Structured logging (new file)
  statistics.py        # Token/time tracking (TODO)
```

### 3.2 Structlog Configuration API

```python
# src/yoker/logging.py

import structlog
from pathlib import Path
from typing import Literal


def configure_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    format: Literal["json", "text"] = "text",
    include_timing: bool = True,
) -> None:
    """Configure structlog for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path for log output.
        format: Output format (json for production, text for development).
        include_timing: Whether to include timing context in all logs.
    
    Example:
        configure_logging(
            level="DEBUG",
            log_file=Path("logs/yoker.log"),
            format="json",
        )
    """
    ...


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured logger for a module.
    
    Args:
        name: Module name (typically __name__).
    
    Returns:
        Configured structlog logger.
    
    Example:
        log = get_logger(__name__)
        log.info("session_started", model="llama3.2")
    """
    ...
```

### 3.3 Logging Context API

```python
# Context management for structured logging

@dataclass
class LogContext:
    """Context added to all log messages within a scope."""
    
    session_id: str | None = None
    agent_name: str | None = None
    turn_number: int | None = None


class LoggingContext:
    """Thread-local context for structured logging."""
    
    @staticmethod
    def bind(**kwargs: Any) -> structlog.stdlib.BoundLogger:
        """Add context to the current logger.
        
        Example:
            with LoggingContext.bind(session_id="abc123"):
                log.info("turn_started", message="Hello")
        """
        ...
    
    @staticmethod
    def get_context() -> LogContext:
        """Get current logging context."""
        ...
```

### 3.4 Timing Integration API

```python
# Timing context manager for performance logging

import time
from contextlib import contextmanager

@contextmanager
def log_timing(
    operation: str,
    log_level: str = "debug",
    **context: Any,
) -> Iterator[None]:
    """Log timing for an operation.
    
    Args:
        operation: Operation name.
        log_level: Log level for timing message.
        **context: Additional context to log.
    
    Example:
        with log_timing("tool_execution", tool="read", file="test.py"):
            result = read_file("test.py")
    """
    log = get_logger(__name__)
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        getattr(log, log_level)(
            operation,
            duration_ms=round(duration_ms, 2),
            **context,
        )
```

### 3.5 Configuration Integration

```toml
# yoker.toml - Logging configuration

[logging]
# Level: DEBUG, INFO, WARNING, ERROR
level = "INFO"

# Output format: json (production) or text (development)
format = "text"

# Optional log file
file = "logs/yoker.log"

# Context inclusion
include_tool_calls = true      # Log tool calls
include_guardrails = true      # Log guardrail decisions (Phase 2)
include_timing = true          # Include timing information

# Console output
console_enabled = true         # Also log to console
console_format = "text"        # Console format (text or json)
```

### 3.6 Configuration Schema

```python
# src/yoker/config/schema.py (addition)

@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""
    
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "text"] = "text"
    file: str | None = None
    include_tool_calls: bool = True
    include_guardrails: bool = True
    include_timing: bool = True
    console_enabled: bool = True
    console_format: Literal["json", "text"] = "text"


@dataclass(frozen=True)
class Config:
    """Main configuration."""
    
    # ... existing fields ...
    logging: LoggingConfig = field(default_factory=LoggingConfig)
```

---

## 4. Integration Points

### 4.1 Where to Add Logging

| Location | What to Log | Level |
|----------|-------------|-------|
| `agent.py` | Session start/end, turn start/end | INFO |
| `agent.py` | Tool calls, tool results | DEBUG |
| `agent.py` | Thinking start/end (if enabled) | DEBUG |
| `backend/ollama.py` | API calls, streaming start/end | DEBUG |
| `context/manager.py` | Context save/load operations | DEBUG |
| `tools/*.py` | Tool execution start/end, guardrail checks | DEBUG |
| `permissions/enforcer.py` | Permission decisions | INFO (blocked), DEBUG (allowed) |
| `config/loader.py` | Configuration loading | DEBUG |

### 4.2 Example Logging Statements

```python
# In agent.py
from yoker.logging import get_logger, log_timing

log = get_logger(__name__)

class Agent:
    def __init__(self, ...):
        log.info("agent_initialized", 
                 model=self.model,
                 thinking_enabled=self.thinking_enabled)
    
    def process(self, message: str) -> str:
        log.info("turn_started", message_preview=message[:50])
        
        with log_timing("llm_request", model=self.model):
            response = self._call_llm(message)
        
        log.info("turn_completed", 
                 response_length=len(response),
                 tool_calls=len(tool_calls))
        
        return response
    
    def _execute_tool(self, name: str, args: dict) -> str:
        log.debug("tool_call", tool=name, args=args)
        
        with log_timing("tool_execution", tool=name):
            result = self.tools[name](**args)
        
        log.debug("tool_result", 
                  tool=name,
                  result_preview=str(result)[:100])
        
        return result
```

### 4.3 Integration with Events

The event system and logging system are complementary:

```python
# Agent emits both events (for UI) and logs (for debugging)

def _emit(self, event: Event) -> None:
    # Emit to event handlers (UI, recording)
    for handler in self._event_handlers:
        handler(event)
    
    # Also log at appropriate level
    log = get_logger(__name__)
    if isinstance(event, SessionStartEvent):
        log.info("session_start", model=event.model)
    elif isinstance(event, ToolCallEvent):
        log.debug("tool_call", 
                  tool=event.tool_name,
                  args=event.arguments)
    elif isinstance(event, ErrorEvent):
        log.error("error",
                  type=event.error_type,
                  message=event.message)
```

---

## 5. Module Restructuring

### 5.1 Current State

```
src/yoker/
  events/              # Domain events
    __init__.py
    types.py
    handlers.py
  logging/             # Event persistence (misnamed)
    __init__.py
    event_logger.py
    event_replay.py
  agent.py             # Uses events, standard logging
```

### 5.2 Recommended Changes

**Option A: Minimal Change (Keep Current Structure)**
- Keep `logging/` module name, add `structlog_setup.py` file
- Confusing naming (`logging` contains event persistence, not structlog)

**Option B: Restructure (Recommended)**
```
src/yoker/
  events/              # Domain events
    __init__.py
    types.py
    handlers.py
    recorder.py        # Renamed from event_logger.py
    replay.py          # Renamed from event_replay.py
  logging.py           # New: structlog configuration
  statistics.py        # New: timing and token tracking
```

**Rationale for Option B**:
1. `events/` module clearly contains all event-related code
2. `logging.py` follows architecture specification
3. `recorder.py` and `replay.py` are clearly event-related
4. Clear separation: events (domain) vs logging (infrastructure)

### 5.3 Migration Path

1. Create `src/yoker/logging.py` for structlog
2. Move `logging/event_logger.py` to `events/recorder.py`
3. Move `logging/event_replay.py` to `events/replay.py`
4. Update imports across codebase
5. Update `events/__init__.py` to export `EventRecorder`, `EventReplayAgent`
6. Remove `logging/` directory

---

## 6. Implementation Considerations

### 6.1 Phase Order

The TODO has logging before guardrails. However:

| Task | Dependencies | Can Implement Now? |
|------|--------------|-------------------|
| structlog setup | None | Yes |
| File/console handlers | structlog setup | Yes |
| Log tool calls | structlog setup | Yes (Agent already calls tools) |
| Log guardrail decisions | Guardrails exist | No (Phase 2 tools) |
| Timing information | None | Yes |

**Recommendation**: Implement logging infrastructure now, add guardrail logging later.

### 6.2 Library vs Application Separation

The Agent is in the **library layer** and should:

- Accept a configured logger (dependency injection)
- Use the logging context for session/turn information
- Not configure logging itself (application does that)

The CLI (`__main__.py`) is in the **application layer** and should:

- Configure structlog with appropriate handlers
- Set up file logging if configured
- Configure console logging format

```python
# In __main__.py (application layer)
from yoker.logging import configure_logging, get_logger
from yoker.events import ConsoleEventHandler

def main():
    # Configure logging
    configure_logging(
        level=config.logging.level,
        log_file=Path(config.logging.file) if config.logging.file else None,
        format=config.logging.format,
    )
    
    log = get_logger(__name__)
    log.info("session_started", config_file=config_path)
    
    # Create agent with event handler
    agent = Agent(config=config)
    agent.add_event_handler(ConsoleEventHandler(console))
    
    # Agent uses injected logger context
    # ...
```

```python
# In agent.py (library layer)
from yoker.logging import get_logger, LoggingContext

log = get_logger(__name__)

class Agent:
    def process(self, message: str) -> str:
        # Use context set by application
        log.info("turn_started", message_preview=message[:50])
        
        with LoggingContext.bind(turn_number=self.turn_count):
            # All logs in this scope include turn_number
            ...
```

### 6.3 Performance Considerations

**Logging Overhead**:
- structlog is fast, but logging has overhead
- Use DEBUG level for verbose logs (tool arguments, timing)
- Use INFO for important events (session start/end, guardrail blocks)
- Use WARNING/ERROR for problems

**Timing**:
- Use `time.perf_counter()` for precise timing
- Include timing in DEBUG logs only (avoid overhead in production)
- Statistics collection is separate (can aggregate timing)

```python
# Performance-aware logging
log = get_logger(__name__)

# Always logged (INFO level)
log.info("session_started", model=self.model)

# Only in DEBUG mode (avoid overhead)
if log.isEnabledFor(logging.DEBUG):
    log.debug("tool_arguments", tool=name, full_args=args)
```

### 6.4 Statistics Integration

The TODO mentions timing for "performance tracking". This connects to statistics:

```python
# src/yoker/statistics.py (future)

@dataclass
class TurnStatistics:
    """Statistics for a single turn."""
    
    input_tokens: int = 0
    output_tokens: int = 0
    llm_time_ms: float = 0
    tool_time_ms: float = 0
    tools_called: list[str] = field(default_factory=list)


class StatisticsCollector:
    """Collects statistics during session."""
    
    def __init__(self):
        self.turns: list[TurnStatistics] = []
        self.start_time = time.perf_counter()
    
    def record_turn(self, stats: TurnStatistics) -> None:
        self.turns.append(stats)
        # Also log
        log.info("turn_completed",
                 input_tokens=stats.input_tokens,
                 output_tokens=stats.output_tokens,
                 llm_time_ms=stats.llm_time_ms,
                 tool_time_ms=stats.tool_time_ms)
```

---

## 7. Action Items

### 7.1 Immediate (Phase 1.5 - Logging System)

| Priority | Task | Effort |
|----------|------|--------|
| High | Create `src/yoker/logging.py` with structlog configuration | Medium |
| High | Add logging configuration to `Config` schema | Small |
| High | Add logging statements to `Agent` class | Medium |
| Medium | Restructure `logging/` to `events/recorder.py` and `events/replay.py` | Medium |
| Medium | Add timing context manager | Small |
| Low | Create `src/yoker/statistics.py` for token/time tracking | Medium |

### 7.2 Future (Phase 2 - Guardrails)

| Priority | Task | Effort |
|----------|------|--------|
| High | Add guardrail decision logging | Small (once guardrails exist) |
| Medium | Add permission enforcer logging | Small |
| Low | Add detailed tool execution logging with guardrail context | Medium |

### 7.3 Documentation Updates

1. Update `analysis/architecture.md` to reflect actual file structure
2. Update `TODO.md` to clarify logging system scope
3. Add logging configuration to example `yoker.toml`
4. Document logging levels and what goes where

---

## 8. Summary

### 8.1 Key Findings

1. **Two Systems Needed**: Event system (domain) and logging system (infrastructure) serve different purposes and should coexist.

2. **EventLogger Misnamed**: The `logging/` module actually contains event persistence/replay, not general logging. Should be renamed to `events/recorder.py` and `events/replay.py`.

3. **structlog Not Yet Integrated**: The TODO task is correct - structlog needs to be added for operational logging.

4. **Guardrails Block Full Completion**: Some TODO items (guardrail decision logging) depend on Phase 2 work.

### 8.2 Recommended Architecture

```
Event System (Domain):
  events/types.py          - Event dataclasses
  events/handlers.py       - EventHandler protocol, ConsoleEventHandler
  events/recorder.py       - EventLogger -> JSONL
  events/replay.py         - EventReplayAgent

Logging System (Infrastructure):
  logging.py               - structlog configuration
  statistics.py            - Token/time tracking
```

### 8.3 Implementation Order

1. Create `logging.py` with structlog configuration
2. Add logging configuration to `Config`
3. Add logging to `Agent` class (tool calls, turns)
4. Add timing context manager
5. Restructure `logging/` to `events/recorder.py` and `events/replay.py`
6. Create `statistics.py` for performance tracking
7. (Future) Add guardrail logging when tools have guardrails