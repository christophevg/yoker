# API Analysis: Agent Tool (Task 2.7)

**Document Version**: 1.0
**Date**: 2026-04-29
**Task**: 2.7 Agent Tool from TODO.md
**Status**: API Design Complete

## Summary

This document designs the API for the `AgentTool` class, which enables subagent spawning for the Yoker agent harness. The design follows the patterns established by other tools, extends them with recursion depth tracking and context isolation, and integrates with the existing Agent class for hierarchical spawning.

---

## 1. AgentTool Class Design

### 1.1 Class Definition

```python
# src/yoker/tools/agent.py

"""Agent tool implementation for Yoker.

Provides the AgentTool for spawning sub-agents with isolated context,
configurable timeouts, and recursion depth limits.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger

from .base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.config import Config
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class AgentTool(Tool):
  """Tool for spawning sub-agents with isolated context.

  Creates a new agent instance with fresh context, runs it with the
  provided prompt, and returns the final response. Supports:

  - Recursion depth tracking (internal, not exposed to LLM)
  - Timeout handling for long-running subagents
  - Context isolation (subagents get fresh context)
  - Per-agent model configuration

  The recursion depth is tracked internally and enforced via errors.
  The LLM cannot control the depth limit - it's configured in the
  harness configuration.
  """

  # Defaults enforced when parameters are omitted
  DEFAULT_TIMEOUT_SECONDS: int = 300  # 5 minutes
  ABSOLUTE_MAX_TIMEOUT_SECONDS: int = 3600  # 1 hour

  def __init__(
    self,
    guardrail: "Guardrail | None" = None,
    parent_agent: "Agent | None" = None,
  ) -> None:
    """Initialize AgentTool with optional guardrail and parent agent.

    Args:
      guardrail: Optional guardrail for parameter validation.
      parent_agent: The parent agent that owns this tool (for context).
    """
    super().__init__(guardrail=guardrail)
    self._parent_agent = parent_agent

  @property
  def name(self) -> str:
    return "agent"

  @property
  def description(self) -> str:
    return (
      "Spawn a sub-agent to perform a specific task. "
      "The sub-agent has isolated context and can use available tools. "
      "Returns the sub-agent's final response."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the agent tool."""
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "agent_path": {
              "type": "string",
              "description": (
                "Path to the agent definition file (Markdown with YAML frontmatter). "
                "The agent definition specifies the tools and system prompt."
              ),
            },
            "prompt": {
              "type": "string",
              "description": (
                "The task or question for the sub-agent to process. "
                "Be specific and provide necessary context."
              ),
            },
            "timeout_seconds": {
              "type": "integer",
              "description": (
                f"Maximum time for sub-agent execution in seconds. "
                f"Defaults to {self.DEFAULT_TIMEOUT_SECONDS} seconds."
              ),
              "minimum": 1,
              "maximum": self.ABSOLUTE_MAX_TIMEOUT_SECONDS,
            },
          },
          "required": ["agent_path", "prompt"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Spawn a sub-agent and return its response.

    Args:
      **kwargs: Must contain 'agent_path' and 'prompt'.
        May contain 'timeout_seconds'.

    Returns:
      ToolResult with the sub-agent's final response or error message.
    """
    ...
```

### 1.2 Parameter Design

| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `agent_path` | string | Yes | - | Must be a valid agent definition file |
| `prompt` | string | Yes | - | Non-empty string |
| `timeout_seconds` | integer | No | 300 | Clamped to `[1, ABSOLUTE_MAX_TIMEOUT_SECONDS]` |

**Parameter Semantics**:

| Parameter | Description |
|-----------|-------------|
| `agent_path` | Path to a Markdown file with YAML frontmatter defining the subagent. The file specifies system prompt, available tools, and optionally the model. |
| `prompt` | The task or question for the subagent. This becomes the user message in the subagent's fresh context. |
| `timeout_seconds` | Maximum execution time. If exceeded, the subagent is terminated and an error is returned. |

**Note on Recursion Depth**:
- Recursion depth is **NOT** a parameter exposed to the LLM
- It's tracked internally in the Agent class
- The harness configuration sets `max_recursion_depth`
- Attempts to spawn beyond the limit return an error

### 1.3 Return Format Design

On success, returns the subagent's final response as a string:

```json
{
  "success": true,
  "result": "I found 5 files matching the pattern 'TODO'. Here are the details:\n..."
}
```

**For structured results**, the subagent should format its response appropriately:

```json
{
  "success": true,
  "result": "## Analysis Results\n\n### Files Found\n- src/main.py: 3 TODOs\n- src/utils.py: 1 TODO\n\n### Recommendations\n1. Address critical TODOs first\n2. ..."
}
```

On error, returns a descriptive error message:

```json
{
  "success": false,
  "error": "Maximum recursion depth (3) exceeded. Cannot spawn sub-agent.",
  "result": ""
}
```

### 1.4 Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| Missing agent_path | `agent_path` not provided | `Missing required parameter: agent_path` |
| Missing prompt | `prompt` not provided | `Missing required parameter: prompt` |
| Agent file not found | Path does not exist | `Agent definition not found: {path}` |
| Invalid agent definition | Frontmatter parse error | `Invalid agent definition: {error}` |
| Recursion depth exceeded | `current_depth >= max_depth` | `Maximum recursion depth ({max_depth}) exceeded` |
| Timeout exceeded | Execution exceeds timeout | `Sub-agent timed out after {timeout} seconds` |
| Tool not available | Agent definition lists unavailable tool | `Agent definition references unavailable tool: {tool_name}` |

**ToolResult for errors**:
```python
ToolResult(success=False, result="", error="Maximum recursion depth (3) exceeded")
```

---

## 2. Recursion Depth Tracking

### 2.1 Internal Tracking Design

Recursion depth is **internal state** that the LLM cannot control:

```python
# In Agent class
class Agent:
  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    # ... other params ...
    _recursion_depth: int = 0,  # Internal, not exposed to LLM
  ) -> None:
    self._recursion_depth = _recursion_depth
    self._max_recursion_depth = config.harness.max_recursion_depth if config else 3
```

### 2.2 Depth Enforcement

The AgentTool checks depth before spawning:

```python
def execute(self, **kwargs: Any) -> ToolResult:
  # ... parameter validation ...

  # Check recursion depth
  if self._parent_agent is not None:
    current_depth = self._parent_agent._recursion_depth
    max_depth = self._parent_agent._max_recursion_depth

    if current_depth >= max_depth:
      return ToolResult(
        success=False,
        result="",
        error=f"Maximum recursion depth ({max_depth}) exceeded",
      )

  # Spawn subagent with incremented depth
  subagent = self._spawn_subagent(
    agent_path=agent_path,
    prompt=prompt,
    depth=current_depth + 1,
  )
  ...
```

### 2.3 Configuration Schema

Recursion depth is configured in the harness configuration:

```toml
# yoker.toml
[harness]
max_recursion_depth = 3  # Maximum nesting of sub-agents

[tools.agent]
enabled = true
timeout_seconds = 300
```

**Default values**:
| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `max_recursion_depth` | 3 | 1-10 | Maximum sub-agent nesting level |
| `timeout_seconds` | 300 | 1-3600 | Maximum sub-agent execution time |

---

## 3. Context Isolation Design

### 3.1 Fresh Context for Subagents

Subagents receive a **fresh, empty context** - no pollution from parent:

```python
def _spawn_subagent(
  self,
  agent_path: Path,
  prompt: str,
  depth: int,
) -> "Agent":
  """Create a sub-agent with fresh context."""

  # Load agent definition
  from yoker.agents import load_agent_definition
  agent_def = load_agent_definition(agent_path)

  # Create fresh context manager
  from yoker.context import BasicPersistenceContextManager
  fresh_context = BasicPersistenceContextManager(
    storage_path=self._parent_agent.context._storage_path,
    session_id=f"{self._parent_agent.context.get_session_id()}_sub_{depth}",
  )

  # Create sub-agent with incremented depth
  subagent = Agent(
    model=agent_def.model or self._parent_agent.model,
    config=self._parent_agent.config,
    agent_definition=agent_def,
    context_manager=fresh_context,
    _recursion_depth=depth,
  )

  return subagent
```

### 3.2 Context Isolation Principles

| Principle | Implementation |
|-----------|----------------|
| **No message inheritance** | Sub-agent starts with empty context |
| **No tool result leakage** | Sub-agent cannot see parent's tool results |
| **No thinking trace** | Sub-agent's thinking is independent |
| **Isolated session ID** | Sub-agent gets new session ID |

### 3.3 Parent-Child Communication

The only communication from parent to subagent is:
1. **System prompt** - From agent definition file
2. **User message** - The `prompt` parameter
3. **Tool availability** - Subset specified in agent definition

The subagent cannot:
- Access parent's conversation history
- See parent's tool calls or results
- Modify parent's context

---

## 4. Timeout Handling

### 4.1 Timeout Implementation

Timeouts prevent runaway subagents:

```python
import signal
from contextlib import contextmanager
from typing import Generator


class TimeoutError(Exception):
  """Raised when sub-agent execution exceeds timeout."""
  pass


@contextmanager
def timeout_context(seconds: int) -> Generator[None, None, None]:
  """Context manager for timeout enforcement."""
  def timeout_handler(signum: int, frame: Any) -> None:
    raise TimeoutError(f"Execution timed out after {seconds} seconds")

  # Set signal handler (Unix only)
  old_handler = signal.signal(signal.SIGALRM, timeout_handler)
  signal.alarm(seconds)
  try:
    yield
  finally:
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old_handler)
```

### 4.2 Timeout in AgentTool

```python
def execute(self, **kwargs: Any) -> ToolResult:
  # ... parameter validation ...

  timeout_seconds = self._clamp(
    int(kwargs.get("timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)),
    1,
    self.ABSOLUTE_MAX_TIMEOUT_SECONDS,
  )

  try:
    with timeout_context(timeout_seconds):
      response = self._run_subagent(subagent, prompt)
    return ToolResult(success=True, result=response)
  except TimeoutError:
    return ToolResult(
      success=False,
      result="",
      error=f"Sub-agent timed out after {timeout_seconds} seconds",
    )
```

### 4.3 Timeout Considerations

| Platform | Implementation | Notes |
|----------|---------------|-------|
| Unix/Linux/macOS | `signal.SIGALRM` | Full timeout support |
| Windows | `threading.Timer` + `ctypes` | Limited support, may not interrupt |

For cross-platform compatibility, consider using `multiprocessing` with timeout or `asyncio` with `asyncio.wait_for`.

---

## 5. Agent Definition Loading

### 5.1 Agent Definition Format

Subagents are defined in Markdown files with YAML frontmatter:

```markdown
---
name: researcher
description: Research assistant for finding and reading files
model: llama3.2:latest
tools:
  - List
  - Read
  - Search
---

You are a research assistant specialized in finding and analyzing information.

## Workflow

1. Use Search to find relevant files
2. Use Read to examine file contents
3. Compile findings into a structured report

## Constraints

- Only read files within allowed paths
- Report findings concisely
- Note any files that couldn't be accessed
```

### 5.2 Tool Availability Filtering

The subagent only has access to tools listed in its definition:

```python
# In Agent class
def _build_tool_registry(self) -> ToolRegistry:
  """Build tool registry filtered by agent definition."""
  registry = ToolRegistry()

  # Create tools with guardrail
  tools: list[Tool] = [
    ReadTool(guardrail=self._guardrail),
    ListTool(guardrail=self._guardrail),
    WriteTool(guardrail=self._guardrail),
    UpdateTool(guardrail=self._guardrail),
    SearchTool(guardrail=self._guardrail),
    AgentTool(guardrail=self._guardrail, parent_agent=self),  # Recursive!
  ]

  if self.agent_definition is not None:
    # Filter by agent definition's tool list
    allowed_tools = {t.lower() for t in self.agent_definition.tools}
    for tool in tools:
      if tool.name.lower() in allowed_tools:
        registry.register(tool)
  else:
    # Register all tools
    for tool in tools:
      registry.register(tool)

  return registry
```

### 5.3 Agent Definition Validation

Agent definitions are validated at load time:

```python
# In agents/loader.py
def validate_agent_definition(definition: AgentDefinition) -> list[str]:
  """Validate agent definition returns list of warnings/errors."""
  warnings = []

  # Check tools exist
  available_tools = {"read", "list", "write", "update", "search", "agent"}
  for tool_name in definition.tools:
    if tool_name.lower() not in available_tools:
      warnings.append(f"Unknown tool '{tool_name}' in agent definition")

  # Check model exists (optional, may not be loaded yet)
  # Check permissions don't exceed parent's permissions (Phase 2)

  return warnings
```

---

## 6. Integration with Agent Class

### 6.1 Agent Class Modifications

The Agent class needs minimal modifications to support subagent spawning:

```python
# In src/yoker/agent.py

class Agent:
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
    _recursion_depth: int = 0,  # Internal parameter for sub-agent tracking
  ) -> None:
    # ... existing initialization ...

    # Track recursion depth (internal, not exposed to LLM)
    self._recursion_depth = _recursion_depth
    self._max_recursion_depth = config.harness.max_recursion_depth if config else 3

    # ... rest of initialization ...
```

### 6.2 AgentTool Registration

The AgentTool needs a reference to the parent agent for context creation:

```python
# In Agent._build_tool_registry()

# Create AgentTool with parent reference
agent_tool = AgentTool(
  guardrail=self._guardrail,
  parent_agent=self,  # Pass parent for context creation
)
registry.register(agent_tool)
```

### 6.3 Subagent Execution Flow

```
Parent Agent (depth: 0)
│
├─ process("Research TODO items")
│   │
│   ├─ Tool call: agent(agent_path="researcher.md", prompt="...")
│   │   │
│   │   └─ AgentTool.execute()
│   │       │
│   │       ├─ Check recursion depth (0 < 3, OK)
│   │       │
│   │       ├─ Load agent definition from "researcher.md"
│   │       │
│   │       ├─ Create fresh context (new session ID)
│   │       │
│   │       ├─ Create sub-agent (depth: 1)
│   │       │
│   │       ├─ Run sub-agent with timeout
│   │       │   │
│   │       │   ├─ Sub-agent processes prompt
│   │       │   │
│   │       │   ├─ Sub-agent may call tools
│   │       │   │
│   │       │   └─ Sub-agent returns final response
│   │       │
│   │       └─ Return response to parent
│   │
│   └─ Continue with response in context
│
└─ Return final response
```

---

## 7. Ollama Function Schema

The complete schema returned by `get_schema()`:

```json
{
  "type": "function",
  "function": {
    "name": "agent",
    "description": "Spawn a sub-agent to perform a specific task. The sub-agent has isolated context and can use available tools. Returns the sub-agent's final response.",
    "parameters": {
      "type": "object",
      "properties": {
        "agent_path": {
          "type": "string",
          "description": "Path to the agent definition file (Markdown with YAML frontmatter). The agent definition specifies the tools and system prompt."
        },
        "prompt": {
          "type": "string",
          "description": "The task or question for the sub-agent to process. Be specific and provide necessary context."
        },
        "timeout_seconds": {
          "type": "integer",
          "description": "Maximum time for sub-agent execution in seconds. Defaults to 300 seconds.",
          "minimum": 1,
          "maximum": 3600
        }
      },
      "required": ["agent_path", "prompt"]
    }
  }
}
```

---

## 8. Security Considerations

### 8.1 Recursion Depth Protection

| Attack Vector | Mitigation |
|---------------|------------|
| Infinite recursion | Hard depth limit enforced internally |
| Depth manipulation | Depth is internal state, not exposed to LLM |
| Recursive spawning loops | Maximum depth check before spawn |

### 8.2 Timeout Protection

| Attack Vector | Mitigation |
|---------------|------------|
| Infinite loops | Timeout enforcement via signal |
| Long-running operations | Default 5-minute timeout, configurable max |
| Resource exhaustion | Maximum timeout cap at 1 hour |

### 8.3 Context Isolation

| Attack Vector | Mitigation |
|---------------|------------|
| Context pollution | Fresh context per subagent |
| Tool result leakage | Isolated context, no inheritance |
| Session ID collision | Unique session ID generation |

### 8.4 Agent Definition Security

| Attack Vector | Mitigation |
|---------------|------------|
| Invalid agent file | Validation at load time |
| Path traversal | Agent path validated against allowed paths |
| Tool escalation | Tool list filtered by agent definition |

---

## 9. Comparison with Other Tools

### 9.1 Consistency Analysis

| Aspect | ReadTool | ListTool | SearchTool | AgentTool | Consistent? |
|--------|----------|----------|------------|-----------|-------------|
| Base class | `Tool` | `Tool` | `Tool` | `Tool` | Yes |
| Property pattern | `@property name/description` | Same | Same | Same | Yes |
| Schema format | OpenAI function-calling | Same | Same | Same | Yes |
| Error handling | Try/except | Same | Same | Same | Yes |
| Return type | `ToolResult` | Same | Same | Same | Yes |
| Guardrail integration | Optional | Optional | Optional | Optional | Yes |
| Parent reference | None | None | None | `parent_agent` | No (unique) |

### 9.2 Key Differences

| Aspect | Other Tools | AgentTool |
|---------|-------------|-----------|
| Operation | File system operation | Agent spawning |
| Return | Structured data or error | Final response text |
| Side effects | File system changes | Sub-agent execution |
| Context | None needed | Parent agent reference |
| Timeout | Not applicable | Required |
| Depth tracking | N/A | Required internally |

---

## 10. Implementation Sketch

### 10.1 Core execute Logic

```python
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.exceptions import AgentDefinitionError, RecursionDepthError

from .base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent

log = get_logger(__name__)


class AgentTool(Tool):
  DEFAULT_TIMEOUT_SECONDS: int = 300
  ABSOLUTE_MAX_TIMEOUT_SECONDS: int = 3600

  def __init__(
    self,
    guardrail: "Guardrail | None" = None,
    parent_agent: "Agent | None" = None,
  ) -> None:
    super().__init__(guardrail=guardrail)
    self._parent_agent = parent_agent

  @property
  def name(self) -> str:
    return "agent"

  @property
  def description(self) -> str:
    return (
      "Spawn a sub-agent to perform a specific task. "
      "The sub-agent has isolated context and can use available tools. "
      "Returns the sub-agent's final response."
    )

  def get_schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "agent_path": {
              "type": "string",
              "description": "Path to agent definition file (Markdown with YAML frontmatter)",
            },
            "prompt": {
              "type": "string",
              "description": "Task or question for the sub-agent",
            },
            "timeout_seconds": {
              "type": "integer",
              "description": f"Maximum execution time in seconds (default: {self.DEFAULT_TIMEOUT_SECONDS})",
              "minimum": 1,
              "maximum": self.ABSOLUTE_MAX_TIMEOUT_SECONDS,
            },
          },
          "required": ["agent_path", "prompt"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    # Validate required parameters
    agent_path_str = kwargs.get("agent_path", "")
    if not agent_path_str:
      return ToolResult(success=False, result="", error="Missing required parameter: agent_path")

    prompt = kwargs.get("prompt", "")
    if not prompt:
      return ToolResult(success=False, result="", error="Missing required parameter: prompt")

    # Parse timeout
    try:
      timeout_seconds = self._clamp(
        int(kwargs.get("timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)),
        1,
        self.ABSOLUTE_MAX_TIMEOUT_SECONDS,
      )
    except (ValueError, TypeError):
      return ToolResult(success=False, result="", error="Invalid numeric parameter: timeout_seconds")

    # Check recursion depth
    if self._parent_agent is not None:
      current_depth = self._parent_agent._recursion_depth
      max_depth = self._parent_agent._max_recursion_depth

      if current_depth >= max_depth:
        return ToolResult(
          success=False,
          result="",
          error=f"Maximum recursion depth ({max_depth}) exceeded. Cannot spawn sub-agent.",
        )

    # Validate agent path exists
    agent_path = Path(agent_path_str)
    if not agent_path.exists():
      return ToolResult(success=False, result="", error=f"Agent definition not found: {agent_path_str}")

    if not agent_path.is_file():
      return ToolResult(success=False, result="", error=f"Agent path is not a file: {agent_path_str}")

    try:
      # Create sub-agent
      subagent = self._create_subagent(agent_path, current_depth + 1 if self._parent_agent else 1)

      # Run with timeout
      response = self._run_with_timeout(subagent, prompt, timeout_seconds)

      return ToolResult(success=True, result=response)

    except TimeoutError:
      return ToolResult(
        success=False,
        result="",
        error=f"Sub-agent timed out after {timeout_seconds} seconds",
      )
    except AgentDefinitionError as e:
      return ToolResult(success=False, result="", error=f"Invalid agent definition: {e}")
    except Exception as e:
      log.error("subagent_error", error=str(e))
      return ToolResult(success=False, result="", error=f"Sub-agent error: {e}")

  def _clamp(self, value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))

  def _create_subagent(self, agent_path: Path, depth: int) -> "Agent":
    """Create a sub-agent with fresh context."""
    from yoker.agent import Agent
    from yoker.agents import load_agent_definition
    from yoker.context import BasicPersistenceContextManager

    # Load agent definition
    agent_def = load_agent_definition(agent_path)

    # Create fresh context
    parent_context = self._parent_agent.context if self._parent_agent else None
    parent_session = parent_context.get_session_id() if parent_context else "root"

    fresh_context = BasicPersistenceContextManager(
      storage_path=self._parent_agent.config.context.storage_path if self._parent_agent else Path("./context"),
      session_id=f"{parent_session}_sub_{depth}",
    )

    # Create sub-agent
    subagent = Agent(
      model=agent_def.model or (self._parent_agent.model if self._parent_agent else None),
      config=self._parent_agent.config if self._parent_agent else None,
      agent_definition=agent_def,
      context_manager=fresh_context,
      _recursion_depth=depth,
    )

    return subagent

  def _run_with_timeout(self, agent: "Agent", prompt: str, timeout_seconds: int) -> str:
    """Run sub-agent with timeout enforcement."""
    import signal

    def timeout_handler(signum: int, frame: Any) -> None:
      raise TimeoutError(f"Sub-agent execution timed out after {timeout_seconds} seconds")

    # Set signal handler (Unix only)
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)

    try:
      response = agent.process(prompt)
      return response
    finally:
      signal.alarm(0)
      signal.signal(signal.SIGALRM, old_handler)
```

### 10.2 Package Registration

Update `src/yoker/tools/__init__.py`:

```python
from .agent import AgentTool

__all__ = [
  # ... existing exports ...
  "AgentTool",
]

def create_default_registry(parent_agent: "Agent | None" = None) -> ToolRegistry:
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(WriteTool())
  registry.register(UpdateTool())
  registry.register(SearchTool())
  registry.register(AgentTool(parent_agent=parent_agent))  # Add this
  return registry
```

**Note**: The AgentTool needs the parent agent reference. This requires modifying how tools are created in the Agent class:

```python
# In Agent._build_tool_registry()
def _build_tool_registry(self) -> ToolRegistry:
  registry = ToolRegistry()

  tools: list[Tool] = [
    ReadTool(guardrail=self._guardrail),
    ListTool(guardrail=self._guardrail),
    WriteTool(guardrail=self._guardrail),
    UpdateTool(guardrail=self._guardrail),
    SearchTool(guardrail=self._guardrail),
    AgentTool(guardrail=self._guardrail, parent_agent=self),  # Pass parent
  ]

  # ... rest of method ...
```

---

## 11. Test Design

### 11.1 Test File Location

`tests/test_tools/test_agent.py`

### 11.2 Test Cases

#### Recursion Depth Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Spawn at depth 0 | `agent_path="researcher.md", prompt="..."` | Success, spawns subagent |
| Spawn at max depth - 1 | Depth at limit - 1 | Success, spawns subagent |
| Spawn at max depth | Depth at limit | `success=False`, "Maximum recursion depth exceeded" |
| Depth beyond max | Depth > limit | `success=False`, "Maximum recursion depth exceeded" |

#### Timeout Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Default timeout | No `timeout_seconds` | Uses 300 second default |
| Custom timeout | `timeout_seconds=60` | Times out after 60 seconds |
| Timeout too small | `timeout_seconds=0` | Clamped to 1 second |
| Timeout too large | `timeout_seconds=9999` | Clamped to 3600 seconds |
| Timeout exceeded | Slow subagent | `success=False`, "timed out" |

#### Agent Definition Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Valid agent definition | Path to valid .md file | Spawns subagent |
| Invalid YAML frontmatter | Malformed YAML | `success=False`, "Invalid agent definition" |
| Missing agent file | Nonexistent path | `success=False`, "Agent definition not found" |
| Agent path is directory | Directory path | `success=False`, "Agent path is not a file" |

#### Context Isolation Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Fresh context | Spawn subagent | Subagent has empty context |
| Different model | Subagent with different model | Subagent uses specified model |
| Tool filtering | Agent with subset of tools | Subagent has only listed tools |
| Parent context not leaked | Subagent processes prompt | No parent messages in context |

#### Parameter Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Missing agent_path | No `agent_path` | `success=False`, "Missing required parameter" |
| Missing prompt | No `prompt` | `success=False`, "Missing required parameter" |
| Invalid timeout | `timeout_seconds="abc"` | `success=False`, "Invalid numeric parameter" |

### 11.3 Fixtures

```python
import pytest
from pathlib import Path
from yoker.agent import Agent
from yoker.config import Config


@pytest.fixture
def temp_agent_file(tmp_path: Path) -> Path:
  """Create a temporary agent definition file."""
  agent_file = tmp_path / "researcher.md"
  agent_file.write_text("""---
name: researcher
description: Test researcher agent
model: llama3.2:latest
tools:
  - List
  - Read
  - Search
---

You are a research assistant. Find and summarize information.
""")
  return agent_file


@pytest.fixture
def parent_agent() -> Agent:
  """Create a parent agent for testing."""
  config = Config()
  config.harness.max_recursion_depth = 3
  return Agent(config=config, _recursion_depth=0)


@pytest.fixture
def mock_slow_agent(monkeypatch):
  """Mock agent.process to simulate slow execution."""
  import time

  def slow_process(self, message: str) -> str:
    time.sleep(5)  # Simulate slow processing
    return "Done"

  monkeypatch.setattr(Agent, "process", slow_process)
```

### 11.4 Test Implementation Sketch

```python
import pytest
from yoker.tools.agent import AgentTool
from yoker.agent import Agent


def test_spawn_subagent_success(temp_agent_file, parent_agent):
  """Test successful subagent spawning."""
  tool = AgentTool(parent_agent=parent_agent)
  result = tool.execute(
    agent_path=str(temp_agent_file),
    prompt="Find TODOs",
  )

  assert result.success
  assert len(result.result) > 0


def test_recursion_depth_exceeded(parent_agent):
  """Test that recursion depth is enforced."""
  # Set parent to max depth
  parent_agent._recursion_depth = 3

  tool = AgentTool(parent_agent=parent_agent)
  result = tool.execute(
    agent_path="researcher.md",
    prompt="Find TODOs",
  )

  assert not result.success
  assert "Maximum recursion depth" in result.error


def test_timeout_exceeded(temp_agent_file, parent_agent, mock_slow_agent):
  """Test timeout enforcement."""
  tool = AgentTool(parent_agent=parent_agent)
  result = tool.execute(
    agent_path=str(temp_agent_file),
    prompt="Find TODOs",
    timeout_seconds=1,  # 1 second timeout
  )

  assert not result.success
  assert "timed out" in result.error


def test_missing_agent_path(parent_agent):
  """Test error when agent_path is missing."""
  tool = AgentTool(parent_agent=parent_agent)
  result = tool.execute(prompt="Test")

  assert not result.success
  assert "Missing required parameter" in result.error


def test_context_isolation(temp_agent_file, parent_agent):
  """Test that subagent gets fresh context."""
  # Add some messages to parent context
  parent_agent.context.add_message("user", "Parent message")

  tool = AgentTool(parent_agent=parent_agent)

  # Mock the subagent creation to capture context
  created_contexts = []

  original_create = tool._create_subagent
  def mock_create(agent_path, depth):
    subagent = original_create(agent_path, depth)
    created_contexts.append(subagent.context)
    return subagent

  tool._create_subagent = mock_create

  result = tool.execute(
    agent_path=str(temp_agent_file),
    prompt="Test prompt",
  )

  # Subagent context should be empty (fresh)
  assert result.success
  # Parent context should still have its message
  assert len(parent_agent.context.get_messages()) > 0
```

---

## 12. Action Items

### 12.1 Implementation Tasks

| Priority | Task | File(s) |
|----------|------|---------|
| High | Create `AgentTool` class | `src/yoker/tools/agent.py` |
| High | Add `_recursion_depth` to Agent class | `src/yoker/agent.py` |
| High | Modify `_build_tool_registry` to pass parent reference | `src/yoker/agent.py` |
| High | Add `max_recursion_depth` to Config | `src/yoker/config/schema.py` |
| High | Register `AgentTool` in package exports | `src/yoker/tools/__init__.py` |
| Medium | Implement timeout handling | `src/yoker/tools/agent.py` |
| Medium | Write unit tests | `tests/test_tools/test_agent.py` |
| Low | Update documentation | `docs/tools.md` (if exists) |

### 12.2 Cross-Task Considerations

- **Task 4.3 (Hierarchical Spawning)**: This task provides the foundation for hierarchical spawning. Task 4.3 will build on this for full integration.
- **Task 3.2 (Tool Call Processing)**: The tool dispatcher will call `AgentTool.execute()` after guardrail validation.
- **Config Schema**: Need to add `max_recursion_depth` to harness configuration.

### 12.3 Documentation Updates

- Update `analysis/architecture.md` to mark AgentTool as implemented
- Update `CLAUDE.md` Current State to include AgentTool
- Add `max_recursion_depth` to configuration documentation

---

## 13. Summary of Design Decisions

1. **Tool name**: `"agent"` - Clear, matches architecture document
2. **Recursion depth internal**: Not exposed to LLM, tracked in Agent class
3. **Fresh context for subagents**: Each subagent starts with empty context
4. **Timeout enforcement**: Default 5 minutes, configurable, max 1 hour
5. **Agent definition validation**: Validate at spawn time, not registration
6. **Parent reference passed**: AgentTool receives parent agent for context creation
7. **Tool filtering by definition**: Subagent only has tools listed in its definition
8. **Error handling**: Clear error messages for depth, timeout, and validation failures
9. **Session ID hierarchy**: Subagent session IDs include parent session ID
10. **Configurable max depth**: Global setting, not per-tool parameter