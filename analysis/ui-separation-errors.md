# UI Separation - Error Handling Strategy

**Document Status:** Draft
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

## Overview

This document catalogs error handling in the current codebase and proposes a unified strategy for the new architecture.

---

## 1. Current Error Handling

### 1.1 Exception-Based (Keep)

| Location | Error Type | Where Raised | Where Caught | Propagates? |
|----------|-----------|--------------|--------------|-------------|
| `agent.py:413-417` | `NetworkError` | `Agent.process()` | `__main__.py` | Yes |
| `agent.py` | Tool errors | Tool execution | `Agent.process()` | No → `ToolResultEvent` |
| `base.py` | Validation errors | AgentCore init | Caller | Yes |

### 1.2 Event-Based (Convert to Exceptions)

| Location | Event Type | Current Handling | Action |
|----------|-----------|------------------|--------|
| `handlers.py:539-544` | `ErrorEvent` | Emitted to handlers | Convert to exception |
| Various | Handler errors | Logged, continues | Let propagate |

### 1.3 Mixed Pattern (Unify)

| Error Scenario | Current Behavior | Target Behavior |
|---------------|------------------|-----------------|
| Network failure | `NetworkError` → caught in `__main__` → print | `NetworkError` → UI catches → `output_error()` |
| Tool error | `ToolResultEvent(success=False)` | Keep as event (tool result is data) |
| Ollama API error | `ResponseError` → caught in `__main__` → print | Exception → UI catches → `output_error()` |
| Agent not found | Logged warning | Keep as logged (non-critical) |
| Config error | Raised in init | Keep as exception |

---

## 2. Exception Hierarchy

### 2.1 Proposed Hierarchy

```python
# yoker/exceptions.py

class YokerError(Exception):
    """Base exception for all Yoker errors."""
    pass


class NetworkError(YokerError):
    """Network communication error.
    
    Attributes:
        recoverable: Whether the error can be recovered from.
        original_error: The underlying exception, if any.
    """
    def __init__(
        self,
        message: str,
        recoverable: bool = True,
        original_error: Exception | None = None
    ):
        self.recoverable = recoverable
        self.original_error = original_error
        super().__init__(message)


class ToolError(YokerError):
    """Tool execution error.
    
    Attributes:
        tool_name: Name of the tool that failed.
    """
    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(f"{tool_name}: {message}")


class ConfigError(YokerError):
    """Configuration error."""
    pass


class AgentError(YokerError):
    """Agent-related error."""
    pass


class SkillError(YokerError):
    """Skill execution error.
    
    Attributes:
        skill_name: Name of the skill that failed.
    """
    def __init__(self, skill_name: str, message: str):
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}': {message}")
```

### 2.2 Error Categories

| Category | Exception | Recoverable? | UI Action |
|----------|-----------|--------------|-----------|
| Network | `NetworkError(recoverable=True)` | Yes | Show message, continue |
| Network | `NetworkError(recoverable=False)` | No | Show message, exit |
| Tool | `ToolError` | Varies | Show in tool result |
| Config | `ConfigError` | No | Show message, exit |
| Agent | `AgentError` | No | Show message, exit |
| Skill | `SkillError` | Varies | Show message |

---

## 3. Error Flow

### 3.1 Current Flow (Problematic)

```
Agent Layer                __main__.py              UI Handler
    │                          │                         │
    │ raise NetworkError       │                         │
    │─────────────────────────>│                         │
    │                          │ print(f"...")          │
    │                          │────────────────────────>│ (never reaches)
    │                          │                         │
```

**Problems:**
- Error handling in wrong layer
- Mixed print statements
- No unified formatting

### 3.2 Target Flow (Clean)

```
Agent Layer                    UI Layer
    │                             │
    │ raise NetworkError          │
    │────────────────────────────>│
    │                             │ UIHandler.output_error(exception)
    │                             │ Format and display error
    │                             │ Decide: continue or exit?
    │                             │
    │                             │ If continue: prompt for next input
    │                             │ If fatal: shutdown, exit
```

---

## 4. Error Formatting

### 4.1 UI Handler Method

```python
class UIHandler(Protocol):
    def output_error(self, error: Exception) -> None:
        """Output error message.
        
        Args:
            error: Exception that occurred.
        """
        ...
```

### 4.2 Interactive Implementation

```python
class InteractiveUIHandler:
    def output_error(self, error: Exception) -> None:
        # Format based on error type
        if isinstance(error, NetworkError):
            if error.recoverable:
                msg = f"Network Error: {error}\nYour message was preserved. Try again or type a new message."
            else:
                msg = f"Fatal Network Error: {error}\nUnable to recover. Please restart the session."
        elif isinstance(error, ToolError):
            msg = f"Tool Error ({error.tool_name}): {error}"
        else:
            msg = f"Error: {error}"
        
        self.console.print(msg, style=Style(color="red", bold=True))
```

### 4.3 Batch Implementation

```python
class BatchUIHandler:
    def output_error(self, error: Exception) -> None:
        # Simple format for batch
        error_type = type(error).__name__
        print(f"Error [{error_type}]: {error}", file=sys.stderr)
```

---

## 5. Error Handling in Agent

### 5.1 What Agent Does

**Raises exceptions for:**
- Network errors (connection failures, timeouts)
- Configuration errors (invalid config)
- Agent errors (initialization failures)
- Skill errors (skill not found, execution failed)

**Emits events for:**
- Tool results (success/failure is data, not error)

### 5.2 What Agent Does NOT Do

- Format error messages
- Print error messages
- Decide whether to continue or exit

---

## 6. Error Handling in UI

### 6.1 Exception Handling

```python
# In UI layer (session loop)

async def run_session(agent: Agent, ui: UIHandler) -> None:
    await ui.start(agent.model, VERSION, config_summary)
    
    try:
        while True:
            try:
                user_input = await ui.get_input()
                if user_input is None:
                    break
                
                # Process with agent
                response = await agent.process(user_input)
                
            except NetworkError as e:
                ui.output_error(e)
                if e.recoverable:
                    continue  # Prompt for next input
                else:
                    break  # Exit session
            
            except YokerError as e:
                ui.output_error(e)
                break  # Exit session on fatal errors
    
    finally:
        await ui.shutdown("quit")
```

### 6.2 Error Recovery

| Error Type | Recovery Action |
|-----------|----------------|
| `NetworkError(recoverable=True)` | Show message, continue session |
| `NetworkError(recoverable=False)` | Show message, exit session |
| `ToolError` | Show in tool result, continue session |
| `ConfigError` | Show message, exit session |
| `AgentError` | Show message, exit session |

---

## 7. Migration Notes

### 7.1 Remove from `__main__.py`

- All `print()` statements for errors
- All `except` blocks that print errors

### 7.2 Add to UI Handler

- `output_error(exception)` method
- Exception handling in session loop

### 7.3 Remove `ErrorEvent`

- `ErrorEvent` in events/types.py
- Emission of `ErrorEvent` in agent code
- Replace with exceptions

---

## 8. Testing

### 8.1 What to Test

- Agent raises correct exceptions
- UI handler formats exceptions correctly
- Recovery logic works (continue vs exit)

### 8.2 What NOT to Test

- Formatting details (colors, styling)
- Error message text (implementation detail)

---

**End of Document**

