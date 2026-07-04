"""Agent tool implementation for Yoker (transitional — Phase 4 replaces with SpawnAgent).

This module provides ``make_agent_tool``, the sub-agent spawning tool. As of
MBI-007 Phase 2:

  - The ``Agent`` class no longer holds an ``AgentRegistry`` (Decision 10) —
    the :class:`yoker.session.Session` owns it.
  - The ``Agent`` class no longer tracks ``recursion_depth`` /
    ``max_recursion_depth`` — the Session tracks depth per spawned agent.
  - ``make_agent_tool`` is **no longer registered by ``Agent.__init__````.
    The tool is kept here for tests and as a transitional home until Phase 4
    replaces it with the Session-injected ``SpawnAgent`` tool (PR #43
    Clarification 2). The tool delegates to ``session.spawn()`` when a
    session is available on the parent agent.

The Phase 4 rewrite (7.8.3) will: rename the tool to ``SpawnAgent``, capture
the Session via closure (``make_spawn_agent_tool(session)``), return both the
spawned agent's unique id and the response in the ``ToolResult`` (PR #43
Clarification 5), and remove ``_create_subagent`` / ``_run_with_timeout`` /
``_clamp`` (their logic now lives on :class:`Session`).
"""

from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.tools.annotations import Text
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS: int = 300
ABSOLUTE_MAX_TIMEOUT_SECONDS: int = 3600


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def make_agent_tool(parent_agent: "Agent | None" = None) -> Any:
  """Create the agent subagent tool callable (transitional).

  The tool delegates to ``parent_agent._session.spawn(...)`` when a session
  is available. When no session is set the tool returns an error result
  (the agent has no registry to resolve names against — Decision 10).

  The available agent names (for the parameter description) are read from
  ``parent_agent._session.agents`` when present.
  """
  session = getattr(parent_agent, "_session", None) if parent_agent is not None else None
  available = session.agents.names if session is not None else []
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

    if session is None:
      return ToolResult(
        success=False,
        error="No session available to resolve and spawn sub-agents.",
      )

    try:
      response = await session.spawn(
        agent_name,
        prompt,
        requester=parent_agent,
        timeout_seconds=timeout_seconds,
      )
      logger.info("sub agent response", response=response)
      return ToolResult(success=True, result=response)
    except TimeoutError as e:
      logger.warning("subagent_timeout", agent_name=agent_name, timeout_seconds=timeout_seconds)
      return ToolResult(success=False, error=str(e))
    except ValueError as e:
      # Allowlist rejection, unknown agent, depth/capacity violation.
      logger.warning("subagent_rejected", agent_name=agent_name, error=str(e))
      available_names = session.agents.names
      hint = ", ".join(available_names) if available_names else "(none loaded)"
      return ToolResult(success=False, error=f"{e}. Available agents: {hint}")
    except Exception as e:
      logger.error(
        "subagent_error",
        agent_name=agent_name,
        error=str(e),
      )
      return ToolResult(success=False, error=f"Sub-agent error: {e}")

  return agent


__all__ = ["make_agent_tool"]
