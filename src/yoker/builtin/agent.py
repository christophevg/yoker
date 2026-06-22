"""Agent tool implementation for Yoker.

Provides the ``make_agent_tool`` factory that returns a callable for
spawning sub-agents with isolated context and recursion depth limits.

The tool spawns a sub-agent by NAME, looking it up in the parent agent's
``AgentRegistry`` (populated at startup from configured directories and
loaded plugins). A bare name (no namespace) matches a unique
``simple_name`` across namespaces; a namespaced name (``pkg:agent``)
matches exactly. Ambiguous or unknown names raise ``ValueError``.
"""

import asyncio
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.annotations import Text
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.agents import AgentDefinition

log = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS: int = 300
ABSOLUTE_MAX_TIMEOUT_SECONDS: int = 3600


def make_agent_tool(parent_agent: "Agent | None" = None) -> Any:
  """Create the agent subagent tool callable.

  The available agent names are baked into the tool's parameter description
  so the model can address them directly.
  """
  available = parent_agent.agents.names if parent_agent is not None else []
  label = "Name of the agent to spawn"
  if available:
    label += f" (available: {', '.join(available)})"

  async def agent(
    agent_name: Annotated[str, Text(label)],
    prompt: Annotated[str, Text("Task for the sub-agent")],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
  ) -> ToolResult:
    """Spawn a sub-agent to perform a specific task."""
    if not agent_name:
      return ToolResult(success=False, error="Missing required parameter: agent_name")

    if not prompt:
      return ToolResult(success=False, error="Missing required parameter: prompt")

    try:
      timeout_seconds = _clamp(int(timeout_seconds), 1, ABSOLUTE_MAX_TIMEOUT_SECONDS)
    except (ValueError, TypeError):
      return ToolResult(success=False, error="Invalid numeric parameter: timeout_seconds")

    if parent_agent is not None:
      current_depth = parent_agent.recursion_depth
      max_depth = parent_agent.max_recursion_depth

      if current_depth >= max_depth:
        log.warning(
          "recursion_depth_exceeded",
          current_depth=current_depth,
          max_depth=max_depth,
        )
        return ToolResult(
          success=False,
          error=f"Maximum recursion depth ({max_depth}) exceeded. Cannot spawn sub-agent.",
        )

    try:
      agent_definition = parent_agent.agents.resolve(agent_name)
    except ValueError as e:
      available_names = parent_agent.agents.names if parent_agent is not None else []
      hint = ", ".join(available_names) if available_names else "(none loaded)"
      return ToolResult(
        success=False,
        error=f"{e}. Available agents: {hint}",
      )
    except Exception as e:
      log.error("agent_resolution_error", agent_name=agent_name, error=str(e))
      return ToolResult(success=False, error=f"Agent resolution failed: {e}")

    try:
      subagent = _create_subagent(parent_agent, agent_definition)
      response = await _run_with_timeout(subagent, prompt, timeout_seconds)
      return ToolResult(success=True, result=response)
    except TimeoutError:
      log.warning("subagent_timeout", agent_name=agent_name, timeout_seconds=timeout_seconds)
      return ToolResult(success=False, error=f"Sub-agent timed out after {timeout_seconds} seconds")
    except Exception as e:
      log.error(
        "subagent_error",
        agent_name=agent_name,
        error=str(e),
        traceback=traceback.format_exc(),
      )
      return ToolResult(success=False, error=f"Sub-agent error: {e}")

  return agent


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def _create_subagent(parent_agent: "Agent | None", agent_definition: "AgentDefinition") -> "Agent":
  """Create a sub-agent with fresh context."""
  from yoker.agent import Agent
  from yoker.context import PersistenceContextManager

  depth = 1
  if parent_agent is not None:
    depth = parent_agent.recursion_depth + 1

  parent_session = "root"
  storage_path = Path("./context")

  if parent_agent is not None:
    parent_session = parent_agent.context.get_session_id()
    storage_path = Path(parent_agent.config.context.storage_path)

  fresh_session_id = f"{parent_session}_{str(uuid.uuid4())[:8]}"

  fresh_context = PersistenceContextManager(
    storage_path=storage_path,
    session_id=fresh_session_id,
  )

  model = agent_definition.model
  parent_config = parent_agent.config if parent_agent else None

  from yoker.config import BackendConfig, Config, OllamaConfig

  config: Config | None = None
  if model is not None:
    if parent_config is not None:
      config = Config(
        harness=parent_config.harness,
        backend=BackendConfig(
          provider=parent_config.backend.provider,
          ollama=OllamaConfig(
            base_url=parent_config.backend.ollama.base_url,
            model=model,
            timeout_seconds=parent_config.backend.ollama.timeout_seconds,
            parameters=parent_config.backend.ollama.parameters,
          ),
        ),
        context=parent_config.context,
        permissions=parent_config.permissions,
        tools=parent_config.tools,
        agents=parent_config.agents,
        skills=parent_config.skills,
        logging=parent_config.logging,
      )
    else:
      config = Config(backend=BackendConfig(ollama=OllamaConfig(model=model)))
  else:
    config = parent_config

  subagent = Agent(
    config=config,
    agent_definition=agent_definition,
    context_manager=fresh_context,
    _recursion_depth=depth,
  )

  log.info(
    "subagent_created",
    agent_name=agent_definition.name,
    depth=depth,
    session_id=fresh_session_id,
    source_path=agent_definition.source_path,
    model=model or (config.backend.ollama.model if config else "default"),
  )

  return subagent


async def _run_with_timeout(agent: "Agent", prompt: str, timeout_seconds: int) -> str:
  """Run sub-agent with timeout enforcement."""
  try:
    response = await asyncio.wait_for(
      agent.process(prompt),
      timeout=timeout_seconds,
    )
    return response
  except asyncio.TimeoutError as e:
    raise TimeoutError(f"Sub-agent execution timed out after {timeout_seconds} seconds") from e


__all__ = ["make_agent_tool"]
