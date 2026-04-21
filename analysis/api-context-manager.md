# API Analysis: Context Manager

**Date**: 2026-04-21
**Reviewer**: API Architect Agent
**Task**: Task 1.4 - Context Manager API Design Review

## Summary

This document provides an API design review for the Context Manager component in Yoker. The Context Manager is responsible for persisting and managing conversation context across LLM turns. The analysis covers the interface design, JSONL storage format, session management, statistics tracking, and integration with existing components.

## Findings

### 1. Interface Design Review

#### Current Proposed Interface (from architecture.md)

```python
class ContextManager(PluginInterface['ContextManager']):
    """Interface for context management strategies."""

    @abstractmethod
    def add_message(self, role: str, content: str,
                    tool_calls: list | None = None) -> None:
        """Add a message to the context."""
        pass

    @abstractmethod
    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        """Add a tool result to the context."""
        pass

    @abstractmethod
    def get_context(self) -> list[dict]:
        """Get current context for LLM API call."""
        pass

    @abstractmethod
    def save(self) -> None:
        """Persist context to storage."""
        pass

    @abstractmethod
    def load(self, session_id: str) -> None:
        """Load context from storage."""
        pass

    @abstractmethod
    def get_statistics(self) -> ContextStatistics:
        """Get token count, message count, etc."""
        pass
```

#### Analysis

**Strengths**:
- Clean separation of concerns (add vs get vs persist)
- Follows the pluggable architecture pattern with `PluginInterface`
- Simple, focused methods

**Issues Found**:

| Issue | Severity | Description | Recommendation |
|-------|----------|-------------|----------------|
| Missing session_id getter | Medium | No way to query current session ID | Add `get_session_id()` method |
| No clear_session method | Medium | Cannot reset context for subagents | Add `clear()` method |
| Missing get_messages method | Low | `get_context()` returns all messages including system, but sometimes need user/assistant only | Add `get_messages(role: str \| None = None)` for flexibility |
| No turn tracking | Medium | No concept of "turn" boundaries | Add `start_turn()` and `end_turn()` for statistics tracking |
| No metadata support | Low | Can't attach metadata to messages | Consider `metadata: dict \| None` parameter |
| Missing close method | Medium | Resource cleanup needed for file handles | Add `close()` method for cleanup |

#### Recommended Interface

```python
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ContextStatistics:
    """Statistics about the current context."""

    # Token tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    input_tokens_per_turn: tuple[int, ...] = field(default_factory=tuple)
    output_tokens_per_turn: tuple[int, ...] = field(default_factory=tuple)

    # Message tracking
    message_count: int = 0
    turn_count: int = 0
    tool_call_count: int = 0

    # Time tracking
    start_time: datetime = field(default_factory=datetime.now)
    last_turn_time: datetime | None = None

    # Tool tracking
    tool_calls: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class ContextManager(Protocol):
    """Interface for context management strategies.

    Context managers are responsible for:
    - Storing conversation history (messages and tool results)
    - Persisting context to storage (JSONL, database, etc.)
    - Providing context for LLM API calls
    - Tracking statistics (tokens, messages, timing)

    Implementations:
    - BasicPersistenceContextManager (MVP): JSONL append-only
    - CompactionContextManager (Phase 1): Summarization
    - MultiTierContextManager (Phase 2): Redis + vector store
    """

    @abstractmethod
    def get_session_id(self) -> str:
        """Get the current session identifier.

        Returns:
            Session ID (UUID string).
        """
        ...

    @abstractmethod
    def add_message(
        self,
        role: str,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message to the context.

        Args:
            role: Message role ('system', 'user', 'assistant', 'tool').
            content: Message content.
            tool_calls: Optional list of tool calls (for assistant messages).
            metadata: Optional metadata to attach to the message.
        """
        ...

    @abstractmethod
    def add_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
        *,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a tool result to the context.

        Args:
            tool_call_id: ID of the tool call this result is for.
            tool_name: Name of the tool that was called.
            result: Tool result content.
            success: Whether the tool call succeeded.
            metadata: Optional metadata to attach.
        """
        ...

    @abstractmethod
    def get_context(self) -> list[dict[str, Any]]:
        """Get current context for LLM API call.

        Returns the full message list in the format expected by the LLM API,
        including system prompt, user messages, assistant responses, and tool results.

        Returns:
            List of message dictionaries.
        """
        ...

    @abstractmethod
    def get_messages(
        self,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get messages, optionally filtered by role.

        Args:
            role: Optional role filter ('system', 'user', 'assistant', 'tool').

        Returns:
            List of matching message dictionaries.
        """
        ...

    @abstractmethod
    def start_turn(self, message: str) -> None:
        """Start a new turn (user message).

        This signals the beginning of a new conversation turn,
        used for timing and statistics tracking.

        Args:
            message: The user message starting the turn.
        """
        ...

    @abstractmethod
    def end_turn(self, response: str, tool_calls_count: int = 0) -> None:
        """End the current turn.

        This signals the completion of a conversation turn,
        used for statistics tracking.

        Args:
            response: The assistant's response text.
            tool_calls_count: Number of tool calls in this turn.
        """
        ...

    @abstractmethod
    def save(self) -> None:
        """Persist context to storage.

        For JSONL-based implementations, this appends new records.
        For database implementations, this commits the transaction.
        """
        ...

    @abstractmethod
    def load(self, session_id: str) -> None:
        """Load context from storage.

        Args:
            session_id: Session ID to load.

        Raises:
            SessionNotFoundError: If session does not exist.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear the context for a fresh session.

        Used when spawning subagents with isolated contexts.
        Does not delete persisted context - use delete() for that.
        """
        ...

    @abstractmethod
    def delete(self) -> None:
        """Delete persisted context from storage.

        Used for session cleanup.
        """
        ...

    @abstractmethod
    def get_statistics(self) -> ContextStatistics:
        """Get context statistics.

        Returns:
            Statistics about the current context.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the context manager and release resources.

        Flushes any pending writes and closes file handles.
        """
        ...
```

### 2. JSONL Storage Format

#### Design Considerations

1. **Append-only for MVP**: Simple, fast writes
2. **Session-level files**: One file per session for isolation
3. **Line-delimited JSON**: Easy to parse, stream-friendly
4. **Replay capability**: Must support full context reconstruction

#### JSONL Record Types

The JSONL file contains different record types, identified by a `type` field:

##### Session Metadata Record (First Record)

```json
{
  "type": "session_start",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "llama3.2:latest",
  "thinking_enabled": true,
  "config_summary": {
    "backend": "ollama",
    "agent_name": "researcher",
    "agent_description": "Research assistant"
  },
  "timestamp": "2026-04-21T10:30:00.000Z",
  "version": "1.0"
}
```

##### Message Record

```json
{
  "type": "message",
  "seq": 1,
  "role": "user",
  "content": "Summarize the README.md file",
  "timestamp": "2026-04-21T10:30:01.000Z"
}
```

```json
{
  "type": "message",
  "seq": 2,
  "role": "assistant",
  "content": "I'll read the README.md file...",
  "thinking": "User wants a summary. Let me first read the file...",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "read",
        "arguments": "{\"file_path\": \"README.md\"}"
      }
    }
  ],
  "timestamp": "2026-04-21T10:30:02.000Z"
}
```

```json
{
  "type": "message",
  "seq": 3,
  "role": "tool",
  "tool_call_id": "call_abc123",
  "tool_name": "read",
  "content": "# Yoker\n\nA Python agent harness...",
  "success": true,
  "timestamp": "2026-04-21T10:30:03.000Z"
}
```

##### Turn Record (Statistics Boundary)

```json
{
  "type": "turn",
  "turn_number": 1,
  "user_message": "Summarize the README.md file",
  "response": "The README describes Yoker as...",
  "tool_calls_count": 2,
  "input_tokens": 150,
  "output_tokens": 45,
  "duration_ms": 1250,
  "timestamp": "2026-04-21T10:30:05.000Z"
}
```

##### Session End Record (Last Record)

```json
{
  "type": "session_end",
  "reason": "quit",
  "total_input_tokens": 500,
  "total_output_tokens": 250,
  "total_turns": 3,
  "total_tool_calls": 5,
  "duration_ms": 5500,
  "timestamp": "2026-04-21T10:35:00.000Z"
}
```

#### File Naming Convention

```
{storage_path}/{session_id}.jsonl
```

Example: `./context/550e8400-e29b-41d4-a716-446655440000.jsonl`

#### Loading Algorithm

```python
def load(self, session_id: str) -> None:
    """Load context from JSONL file."""
    file_path = self.storage_path / f"{session_id}.jsonl"

    with open(file_path) as f:
        for line in f:
            record = json.loads(line)

            match record["type"]:
                case "session_start":
                    self._load_session_start(record)
                case "message":
                    self._load_message(record)
                case "turn":
                    self._load_turn(record)
                case "session_end":
                    pass  # End marker

    self.session_id = session_id
```

### 3. Session Management

#### Session ID Generation

```python
import uuid

def generate_session_id() -> str:
    """Generate a unique session ID (UUID v4)."""
    return str(uuid.uuid4())
```

**Rationale**:
- UUID v4 provides strong uniqueness guarantees
- String format is human-readable and URL-safe
- Standard format supported by databases and file systems

#### Session Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    Session Lifecycle                             │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Created   │───▶│   Active    │───▶│   Closed    │         │
│  │             │    │             │    │             │         │
│  │ session_id  │    │ messages    │    │ persisted   │         │
│  │ generated   │    │ accumulated │    │ closed      │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                            │                                     │
│                            ▼                                     │
│                     ┌─────────────┐                              │
│                     │   Resumed   │                              │
│                     │             │                              │
│                     │ loaded from │                              │
│                     │ storage     │                              │
│                     └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

#### Session Resumption

```python
def resume_session(session_id: str, storage_path: Path) -> ContextManager:
    """Resume an existing session from storage.

    Args:
        session_id: Session ID to resume.
        storage_path: Path to context storage.

    Returns:
        ContextManager with loaded context.

    Raises:
        SessionNotFoundError: If session does not exist.
    """
    context = BasicPersistenceContextManager(storage_path=storage_path)
    context.load(session_id)
    return context
```

#### Context Isolation for Subagents

When spawning a subagent, create a fresh context:

```python
def create_subagent_context(
    parent_session_id: str,
    subagent_depth: int,
    storage_path: Path,
) -> ContextManager:
    """Create an isolated context for a subagent.

    Args:
        parent_session_id: Parent session ID (for logging hierarchy).
        subagent_depth: Recursion depth (0 = main agent).
        storage_path: Path to context storage.

    Returns:
        Fresh ContextManager with new session ID.
    """
    # Generate new session ID
    session_id = generate_session_id()

    # Create fresh context (no message inheritance)
    context = BasicPersistenceContextManager(
        storage_path=storage_path,
        session_id=session_id,
    )

    # Log parent relationship in session_start record
    context._write_session_start(
        parent_session_id=parent_session_id,
        subagent_depth=subagent_depth,
    )

    return context
```

### 4. Context Statistics

#### Statistics Tracking

```python
@dataclass(frozen=True)
class ContextStatistics:
    """Statistics about the current context."""

    # Token tracking (accumulated)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Per-turn token tracking
    input_tokens_per_turn: tuple[int, ...] = ()
    output_tokens_per_turn: tuple[int, ...] = ()

    # Message counts
    message_count: int = 0  # Total messages (system + user + assistant + tool)
    turn_count: int = 0     # Number of user-assistant exchanges
    tool_call_count: int = 0  # Total tool calls

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    last_turn_time: datetime | None = None

    # Tool breakdown
    tool_calls: tuple[str, ...] = ()  # List of tool names called

    # Computed properties
    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def average_tokens_per_turn(self) -> float:
        """Average tokens per turn."""
        if self.turn_count == 0:
            return 0.0
        return self.total_tokens / self.turn_count

    @property
    def duration_seconds(self) -> float:
        """Session duration in seconds."""
        if self.last_turn_time is None:
            return 0.0
        return (self.last_turn_time - self.start_time).total_seconds()
```

#### Token Counting Integration

```python
def count_tokens(self, text: str) -> int:
    """Count tokens in text using the backend provider.

    Args:
        text: Text to count tokens for.

    Returns:
        Token count.
    """
    # Delegate to backend provider's tokenizer
    return self.backend.count_tokens(text)
```

### 5. Integration Points

#### Agent Class Integration

Replace `self.messages` with ContextManager:

```python
class Agent:
    """Agent with context management."""

    def __init__(
        self,
        model: str | None = None,
        config: Config | None = None,
        context_manager: ContextManager | None = None,
        # ... other params
    ) -> None:
        # ... existing initialization

        # Use provided context manager or create default
        if context_manager is not None:
            self.context = context_manager
        else:
            self.context = BasicPersistenceContextManager(
                storage_path=Path(self.config.context.storage_path),
                session_id=self.config.context.session_id,
            )

        # Load system prompt into context
        self.context.add_message("system", system_prompt)

    def process(self, message: str) -> str:
        """Process a single message."""
        # Start turn tracking
        self.context.start_turn(message)

        # ... existing processing logic

        # Update context with messages
        self.context.add_message("user", message)

        # Get context for LLM
        messages = self.context.get_context()

        # ... call LLM, process tool calls

        # End turn tracking
        self.context.end_turn(response, tool_calls_count)

        # Persist if configured
        if self.config.context.persist_after_turn:
            self.context.save()

        return response
```

#### Event System Integration

ContextManager should emit events for statistics:

```python
class ContextManager:
    """Context manager with event emission."""

    def __init__(self, event_handler: EventHandler | None = None) -> None:
        self._event_handler = event_handler

    def _emit(self, event: Event) -> None:
        """Emit an event if handler is registered."""
        if self._event_handler is not None:
            self._event_handler(event)

    def add_message(self, role: str, content: str, **kwargs) -> None:
        # ... add message logic
        # Event emission is handled by Agent, not ContextManager
        pass
```

**Note**: ContextManager should NOT emit events. Events are emitted by the Agent class. ContextManager is a storage/persistence component, not an event source. Statistics are retrieved via `get_statistics()` and can be emitted by Agent.

#### Configuration Integration

```python
@dataclass(frozen=True)
class ContextConfig:
    """Context management configuration."""

    manager: str = "basic_persistence"  # basic_persistence | compaction | multi_tier
    storage_path: str = "./context"
    session_id: str = "auto"  # auto = generate new, or specific ID
    persist_after_turn: bool = True
    compaction_threshold: int = 100  # Messages before compaction (Phase 1)
    compaction_strategy: str = "summarize"  # summarize | truncate (Phase 1)
```

### 6. Pluggable Architecture

#### Implementation Registry

```python
# src/yoker/context/__init__.py
from yoker.context.interface import ContextManager
from yoker.context.basic import BasicPersistenceContextManager

# Registry of context manager implementations
_CONTEXT_MANAGERS: dict[str, type[ContextManager]] = {
    "basic_persistence": BasicPersistenceContextManager,
    # Phase 1:
    # "compaction": CompactionContextManager,
    # Phase 2:
    # "multi_tier": MultiTierContextManager,
}

def create_context_manager(
    config: ContextConfig,
    **kwargs,
) -> ContextManager:
    """Create a context manager from configuration.

    Args:
        config: Context configuration.
        **kwargs: Additional arguments for context manager.

    Returns:
        Configured context manager instance.

    Raises:
        ValueError: If manager type is not registered.
    """
    manager_class = _CONTEXT_MANAGERS.get(config.manager)
    if manager_class is None:
        raise ValueError(f"Unknown context manager: {config.manager}")

    return manager_class(
        storage_path=Path(config.storage_path),
        session_id=config.session_id,
        **kwargs,
    )
```

#### BasicPersistenceContextManager Implementation

```python
# src/yoker/context/basic.py
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import uuid

from yoker.context.interface import ContextManager, ContextStatistics


class BasicPersistenceContextManager:
    """Basic context manager with JSONL persistence.

    Features:
    - Append-only JSONL storage
    - No compaction (MVP)
    - Simple statistics tracking
    - Session resumption support
    """

    def __init__(
        self,
        storage_path: Path,
        session_id: str = "auto",
    ) -> None:
        """Initialize context manager.

        Args:
            storage_path: Directory to store context files.
            session_id: Session ID ('auto' for new session).
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Generate or use provided session ID
        self._session_id = (
            str(uuid.uuid4()) if session_id == "auto" else session_id
        )

        # In-memory context
        self._messages: list[dict[str, Any]] = []
        self._turns: list[dict[str, Any]] = []

        # Statistics
        self._statistics = ContextStatistics()

        # Track if session_start has been written
        self._started = False

    def get_session_id(self) -> str:
        """Get the current session identifier."""
        return self._session_id

    def add_message(
        self,
        role: str,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message to the context."""
        message: dict[str, Any] = {
            "role": role,
            "content": content,
        }

        if tool_calls is not None:
            message["tool_calls"] = tool_calls

        if metadata is not None:
            message["metadata"] = metadata

        self._messages.append(message)

    def add_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
        *,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a tool result to the context."""
        message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "content": result,
            "success": success,
        }

        if metadata is not None:
            message["metadata"] = metadata

        self._messages.append(message)

    def get_context(self) -> list[dict[str, Any]]:
        """Get current context for LLM API call."""
        # Return copy to prevent mutation
        return list(self._messages)

    def get_messages(self, role: str | None = None) -> list[dict[str, Any]]:
        """Get messages, optionally filtered by role."""
        if role is None:
            return list(self._messages)

        return [m for m in self._messages if m.get("role") == role]

    def start_turn(self, message: str) -> None:
        """Start a new turn."""
        # For BasicPersistence, turns are implicit
        # Statistics are tracked via end_turn()
        pass

    def end_turn(
        self,
        response: str,
        tool_calls_count: int = 0,
    ) -> None:
        """End the current turn."""
        # Update statistics
        # For MVP, we don't track per-turn tokens (requires backend integration)
        pass

    def save(self) -> None:
        """Persist context to JSONL file."""
        file_path = self.storage_path / f"{self._session_id}.jsonl"

        with open(file_path, "a") as f:
            # Write session_start if not already written
            if not self._started:
                self._write_session_start(f)

            # Write all messages
            for i, message in enumerate(self._messages):
                self._write_message(f, i, message)

            self._started = True

    def load(self, session_id: str) -> None:
        """Load context from JSONL file."""
        file_path = self.storage_path / f"{session_id}.jsonl"

        if not file_path.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")

        self._session_id = session_id
        self._messages.clear()
        self._turns.clear()
        self._started = True

        with open(file_path) as f:
            for line in f:
                record = json.loads(line)

                if record["type"] == "message":
                    self._load_message(record)

    def clear(self) -> None:
        """Clear the context."""
        self._messages.clear()
        self._turns.clear()
        self._statistics = ContextStatistics()
        # Note: Does not delete persisted file

    def delete(self) -> None:
        """Delete persisted context from storage."""
        file_path = self.storage_path / f"{self._session_id}.jsonl"
        if file_path.exists():
            file_path.unlink()

    def get_statistics(self) -> ContextStatistics:
        """Get context statistics."""
        return ContextStatistics(
            message_count=len(self._messages),
            turn_count=len(self._turns),
            start_time=self._statistics.start_time,
        )

    def close(self) -> None:
        """Close the context manager."""
        # No resources to close for JSONL
        pass

    # Private methods

    def _write_session_start(self, f) -> None:
        """Write session_start record."""
        record = {
            "type": "session_start",
            "session_id": self._session_id,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",
        }
        f.write(json.dumps(record) + "\n")

    def _write_message(self, f, seq: int, message: dict) -> None:
        """Write message record."""
        record = {
            "type": "message",
            "seq": seq,
            **message,
            "timestamp": datetime.now().isoformat(),
        }
        f.write(json.dumps(record) + "\n")

    def _load_message(self, record: dict) -> None:
        """Load a message from record."""
        message = {
            "role": record["role"],
            "content": record.get("content", ""),
        }

        if "tool_calls" in record:
            message["tool_calls"] = record["tool_calls"]

        if "tool_call_id" in record:
            message["tool_call_id"] = record["tool_call_id"]
            message["tool_name"] = record["tool_name"]
            message["success"] = record.get("success", True)

        self._messages.append(message)


class SessionNotFoundError(Exception):
    """Raised when a session is not found in storage."""
    pass
```

## Recommendations

### Priority: High

1. **Implement BasicPersistenceContextManager as MVP**: Simple, working implementation for Task 1.4
2. **Add turn tracking**: `start_turn()` and `end_turn()` methods for statistics
3. **Add clear() method**: Essential for subagent context isolation
4. **Add close() method**: Resource cleanup pattern

### Priority: Medium

5. **Integrate with Agent class**: Replace `self.messages` with ContextManager
6. **Add session resumption**: Ability to continue previous session
7. **Add statistics integration**: Connect with backend provider's token counting

### Priority: Low

8. **Add metadata support**: Optional field for extensibility
9. **Add get_messages() filtering**: Convenience for filtering by role

## Concerns

### Design Concerns

1. **Token Counting Dependency**: Statistics need backend provider for accurate token counts. Recommend adding `backend: BackendProvider` parameter to ContextManager for token counting.

2. **Concurrent Access**: JSONL files are not safe for concurrent access. Recommend noting this limitation and suggesting database implementations for concurrent use cases.

3. **Large Context Files**: JSONL files can grow large for long conversations. Recommend documenting size limits and suggesting compaction for production use.

### Integration Concerns

1. **Event System Overlap**: Current Agent class uses events for all output. ContextManager should NOT emit events - it's a storage component. Statistics retrieval should be separate.

2. **Subagent Context**: Need to ensure context isolation when spawning subagents. The `clear()` method addresses this, but integration with Agent tool needs care.

## Action Items

### Implementation Tasks (Task 1.4)

1. Create `src/yoker/context/__init__.py` with interface and registry
2. Create `src/yoker/context/interface.py` with `ContextManager` protocol and `ContextStatistics`
3. Create `src/yoker/context/basic.py` with `BasicPersistenceContextManager`
4. Create `src/yoker/context/exceptions.py` with `SessionNotFoundError`
5. Add tests in `tests/test_context/`
6. Integrate with Agent class
7. Update configuration loading to create context manager

### Documentation Tasks

1. Document JSONL format in `docs/api/context.md`
2. Add session management examples in `docs/quickstart.md`
3. Update architecture diagram to show ContextManager integration

### Future Enhancements (Phase 1)

1. Implement `CompactionContextManager` with summarization
2. Add context pruning for token limit management
3. Add context compaction configuration options

## Conclusion

The proposed Context Manager interface is well-designed but needs a few additions for full functionality:

1. **Essential additions**: `get_session_id()`, `clear()`, `close()`, and turn tracking methods
2. **JSONL format**: Append-only, session-scoped files with typed records
3. **Session management**: UUID v4 for IDs, clear isolation for subagents
4. **Statistics**: Token tracking, message counts, timing - integration with backend provider

The `BasicPersistenceContextManager` implementation provides a solid MVP foundation. The pluggable architecture allows for future enhancements (compaction, multi-tier) without breaking the interface.

**Recommendation**: Proceed with Task 1.4 implementation using the recommended interface and JSONL format.