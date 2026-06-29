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
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.tools.annotations import Text
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.agents import AgentDefinition

logger = get_logger(__name__)

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
        logger.warning(
          "recursion_depth_exceeded",
          current_depth=current_depth,
          max_depth=max_depth,
        )
        return ToolResult(
          success=False,
          error=f"Maximum recursion depth ({max_depth}) exceeded. Cannot spawn sub-agent.",
        )

    try:
      if parent_agent is None:
        return ToolResult(success=False, error="No parent agent available to resolve sub-agent")
      agent_definition = parent_agent.agents.resolve(agent_name)
    except ValueError as e:
      available_names = parent_agent.agents.names if parent_agent is not None else []
      hint = ", ".join(available_names) if available_names else "(none loaded)"
      return ToolResult(
        success=False,
        error=f"{e}. Available agents: {hint}",
      )
    except Exception as e:
      logger.error("agent_resolution_error", agent_name=agent_name, error=str(e))
      return ToolResult(success=False, error=f"Agent resolution failed: {e}")

    try:
      subagent = _create_subagent(parent_agent, agent_definition)
      response = await _run_with_timeout(subagent, prompt, timeout_seconds)
      logger.info("sub agent response", response=response)
      return ToolResult(success=True, result=response)
    except TimeoutError:
      logger.warning("subagent_timeout", agent_name=agent_name, timeout_seconds=timeout_seconds)
      return ToolResult(success=False, error=f"Sub-agent timed out after {timeout_seconds} seconds")
    except Exception as e:
      logger.error(
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
  from dataclasses import replace

  from yoker.agent import Agent
  from yoker.config import Config

  depth = 1
  if parent_agent is not None:
    depth = parent_agent.recursion_depth + 1

  parent_session = "root"
  # storage_path = Path("./context")

  if parent_agent is not None:
    parent_session = parent_agent.context.get_session_id()
    # TODO: the agent tool had a hardcoded dependency on Persistence Context Manager
    #       this created a bad context. Simple Context Manager is doing a better job
    #       -> we need to create a better way to selecting a good context manager, for
    #          all agents. Idea: create the same as the parent, which should come from
    #          configuration, which is currently also not yet the case.
    # storage_path = Path(parent_agent.config.context.storage_path)

  fresh_session_id = f"{parent_session}_{str(uuid.uuid4())[:8]}"

  model = agent_definition.model
  parent_config = parent_agent.config if parent_agent else None

  config: Config | None = None
  if model is not None:
    if parent_config is not None:
      # Inline with_model logic: create provider-agnostic config copy with model override
      # Get the active provider's config using the generic property
      from yoker.config import AnthropicConfig, OllamaConfig, OpenAIConfig

      sub_config = parent_config.backend.config
      if sub_config is None:
        raise ValueError(f"No config for provider: {parent_config.backend.provider}")

      # Override model on the sub-config
      new_sub_config = replace(sub_config, model=model)

      # Create new BackendConfig with updated sub-config
      # Use conditional logic to satisfy mypy's type checker
      provider = parent_config.backend.provider
      if provider == "ollama" and isinstance(new_sub_config, OllamaConfig):
        backend = replace(parent_config.backend, ollama=new_sub_config)
      elif provider == "openai" and isinstance(new_sub_config, OpenAIConfig):
        backend = replace(parent_config.backend, openai=new_sub_config)
      elif provider == "anthropic" and isinstance(new_sub_config, AnthropicConfig):
        backend = replace(parent_config.backend, anthropic=new_sub_config)
      else:
        # Unknown provider or type mismatch - shouldn't happen in practice
        raise ValueError(f"Unknown provider or type mismatch: {provider}")

      config = replace(
        parent_config,
        backend=backend,
      )
    else:
      # This should not happen in practice - parent_agent is validated earlier
      raise RuntimeError("parent_config is None when model is specified - this should not happen")
  else:
    config = parent_config

  subagent = Agent(
    config=config,
    agent_definition=agent_definition,
    _recursion_depth=depth,
  )

  # Get model from the active provider's config for logging
  active_model = model
  if active_model is None and config:
    # Use the generic config property
    sub_config = config.backend.config
    if sub_config is not None:
      active_model = sub_config.model
    else:
      active_model = "default"

  logger.info(
    "subagent_created",
    agent_name=agent_definition.name,
    depth=depth,
    session_id=fresh_session_id,
    source_path=agent_definition.source_path,
    model=active_model or "default",
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
