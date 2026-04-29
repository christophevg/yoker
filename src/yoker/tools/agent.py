"""Agent tool implementation for Yoker.

Provides the AgentTool for spawning sub-agents with isolated context,
configurable timeouts, and recursion depth limits.
"""

import signal
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent
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
    """Return Ollama-compatible schema for the agent tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
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
    # Validate required parameters
    agent_path_str = kwargs.get("agent_path", "")
    if not agent_path_str:
      return ToolResult(
        success=False,
        result="",
        error="Missing required parameter: agent_path",
      )

    prompt = kwargs.get("prompt", "")
    if not prompt:
      return ToolResult(
        success=False,
        result="",
        error="Missing required parameter: prompt",
      )

    # Parse timeout (with clamping)
    try:
      timeout_seconds = self._clamp(
        int(kwargs.get("timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)),
        1,
        self.ABSOLUTE_MAX_TIMEOUT_SECONDS,
      )
    except (ValueError, TypeError):
      return ToolResult(
        success=False,
        result="",
        error="Invalid numeric parameter: timeout_seconds",
      )

    # Check recursion depth
    if self._parent_agent is not None:
      current_depth = self._parent_agent._recursion_depth
      max_depth = self._parent_agent._max_recursion_depth

      if current_depth >= max_depth:
        log.warning(
          "recursion_depth_exceeded",
          current_depth=current_depth,
          max_depth=max_depth,
        )
        return ToolResult(
          success=False,
          result="",
          error=f"Maximum recursion depth ({max_depth}) exceeded. Cannot spawn sub-agent.",
        )

    # Validate agent path exists
    agent_path = Path(agent_path_str)
    if not agent_path.exists():
      return ToolResult(
        success=False,
        result="",
        error=f"Agent definition not found: {agent_path_str}",
      )

    if not agent_path.is_file():
      return ToolResult(
        success=False,
        result="",
        error=f"Agent path is not a file: {agent_path_str}",
      )

    # Security: Validate path is within allowed directory
    allowed_dir = self._get_allowed_agents_directory()
    try:
      resolved_path = agent_path.resolve()
      allowed_resolved = allowed_dir.resolve()

      if not str(resolved_path).startswith(str(allowed_resolved)):
        log.warning(
          "path_traversal_attempt",
          requested_path=str(agent_path),
          allowed_dir=str(allowed_dir),
        )
        return ToolResult(
          success=False,
          result="",
          error=f"Agent path not in allowed directory: {allowed_dir}",
        )
    except Exception as e:
      log.error(
        "path_validation_error",
        path=str(agent_path),
        error=str(e),
      )
      return ToolResult(
        success=False,
        result="",
        error=f"Path validation failed: {e}",
      )

    try:
      # Create sub-agent with fresh context
      subagent = self._create_subagent(agent_path)

      # Run with timeout
      response = self._run_with_timeout(subagent, prompt, timeout_seconds)

      return ToolResult(success=True, result=response)

    except TimeoutError:
      log.warning(
        "subagent_timeout",
        agent_path=str(agent_path),
        timeout_seconds=timeout_seconds,
      )
      return ToolResult(
        success=False,
        result="",
        error=f"Sub-agent timed out after {timeout_seconds} seconds",
      )
    except Exception as e:
      log.error(
        "subagent_error",
        agent_path=str(agent_path),
        error=str(e),
        traceback=traceback.format_exc(),
      )
      return ToolResult(success=False, result="", error=f"Sub-agent error: {e}")

  def _clamp(self, value: int, minimum: int, maximum: int) -> int:
    """Clamp a value to a range.

    Args:
      value: Value to clamp.
      minimum: Minimum value.
      maximum: Maximum value.

    Returns:
      Clamped value.
    """
    return max(minimum, min(value, maximum))

  def _get_allowed_agents_directory(self) -> Path:
    """Get allowed directory for agent definitions.

    Returns:
      Path to the allowed agents directory.
    """
    # Check if config specifies an agents directory
    if self._parent_agent is not None:
      agents_dir = self._parent_agent.config.agents.directory
      if agents_dir:
        return Path(agents_dir)

    # Default to examples/agents in the current working directory
    return Path.cwd() / "examples" / "agents"

  def _create_subagent(self, agent_path: Path) -> "Agent":
    """Create a sub-agent with fresh context.

    Args:
      agent_path: Path to the agent definition file.

    Returns:
      New Agent instance with fresh context.

    Raises:
      ConfigurationError: If agent definition is invalid.
    """
    from yoker.agent import Agent
    from yoker.agents import load_agent_definition
    from yoker.context import BasicPersistenceContextManager

    # Load agent definition
    agent_def = load_agent_definition(agent_path)

    # Calculate depth for subagent
    depth = 1
    if self._parent_agent is not None:
      depth = self._parent_agent._recursion_depth + 1

    # Create fresh context with isolated session ID
    parent_session = "root"
    storage_path = Path("./context")

    if self._parent_agent is not None:
      parent_session = self._parent_agent.context.get_session_id()
      storage_path = Path(self._parent_agent.config.context.storage_path)

    # Security: Use UUID4 for unpredictable session IDs
    fresh_session_id = f"{parent_session}_{str(uuid.uuid4())[:8]}"

    fresh_context = BasicPersistenceContextManager(
      storage_path=storage_path,
      session_id=fresh_session_id,
    )

    # Determine model (use agent's model or parent's model)
    model = agent_def.model
    if model is None and self._parent_agent is not None:
      model = self._parent_agent.model

    # Create sub-agent with incremented depth
    subagent = Agent(
      model=model,
      config=self._parent_agent.config if self._parent_agent else None,
      agent_definition=agent_def,
      context_manager=fresh_context,
      _recursion_depth=depth,
    )

    log.info(
      "subagent_created",
      agent_name=agent_def.name,
      depth=depth,
      session_id=fresh_session_id,
      model=model,
    )

    return subagent

  def _run_with_timeout(self, agent: "Agent", prompt: str, timeout_seconds: int) -> str:
    """Run sub-agent with timeout enforcement.

    Uses signal.SIGALRM for timeout on Unix systems.

    Args:
      agent: The sub-agent to run.
      prompt: The prompt for the sub-agent.
      timeout_seconds: Maximum execution time in seconds.

    Returns:
      The sub-agent's response.

    Raises:
      TimeoutError: If execution exceeds timeout.
    """
    import sys

    # Only use signal-based timeout on Unix systems
    if sys.platform != "win32":

      def timeout_handler(signum: int, frame: Any) -> None:
        raise TimeoutError(f"Sub-agent execution timed out after {timeout_seconds} seconds")

      # Set signal handler
      old_handler = signal.signal(signal.SIGALRM, timeout_handler)
      signal.alarm(timeout_seconds)

      try:
        response = agent.process(prompt)
        return response
      finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    else:
      # On Windows, run without timeout enforcement (limitation)
      log.warning(
        "windows_timeout_limitation",
        message="Timeout enforcement not available on Windows",
      )
      response = agent.process(prompt)
      return response
