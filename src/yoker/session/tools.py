"""Session-injected tools: ``agent`` and ``send_message``

``agent`` and ``send_message`` are
Session-injected tools — the :class:`yoker.session.Session` captures itself
in the closure (back-reference) and registers the tools on Agents it owns.
They are NOT registered by the Agent itself and are not part of the Agent's
static tool set loaded from plugins.

``agent``
  - Calls ``session._spawn_internal(name, requester=<calling agent>)``,
    runs the spawned agent's ``process(prompt)`` with a timeout, and
    ``session.release(child)`` in a finally block.
  - Returns a ``ToolResult`` carrying both the spawned agent's unique id and
    its response string (so the model can address the child later via
    ``send_message``).
  - Available agent names are baked into the tool description from the
    calling agent's ``AgentDefinition.agents`` allowlist (intersected with
    ``session.agents.names``) — only allowlisted names are shown.

``send_message``
  - Resolves the ``to``/``from_id`` string references to active
    :class:`Agent` instances via the session's active map, then calls
    ``session.send(to=, from_=, content=)``.
  - ``from_id`` is the calling agent's runtime name (captured at injection
    time).
  - Returns the target agent's response string, or an error result when the
    target is no longer active
"""

import asyncio
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.tools.annotations import Text
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.session import Session

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS: int = 300
ABSOLUTE_MAX_TIMEOUT_SECONDS: int = 3600


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def make_spawn_agent_tool(session: "Session", requester: "Agent") -> Any:
  """Build the Session-injected ``agent`` tool for a specific agent.

  The Session captures itself in the closure and registers the tool on
  Agents it owns. The requesting agent is also captured so the allowlist
  check fires inside ``session.spawn``.

  Args:
    session: The :class:`Session` that owns the agent (back-reference).
    requester: The :class:`Agent` on which this tool is being injected. Used
      as the ``requester`` argument to ``session.spawn`` so the allowlist on
      ``requester.definition.agents`` is enforced.

  Returns:
    The ``agent`` tool callable (async function).
  """
  # Bake available agent names from the requester's allowlist intersected
  # with the session registry (only allowlisted names are shown to the model).
  allowlist = tuple(requester.definition.agents or ())
  registry_names = set(session.agents.names) if session.agents else set()
  available = [n for n in allowlist if n in registry_names]
  if not available:
    # Fall back to the full allowlist when the registry isn't populated yet
    # (e.g. agents loaded lazily). The allowlist is the authoritative gate.
    available = list(allowlist)

  label = "Name of the agent to spawn"
  if available:
    label += f" (available: {', '.join(available)})"

  async def spawn_agent(
    agent_name: Annotated[str, Text(label)],
    prompt: Annotated[str, Text("Task for the spawned agent")],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
  ) -> ToolResult:
    """Spawn a sub-agent to perform a specific task.

    Returns the spawned agent's unique id and its response so you can
    address it later via send_message.
    """
    if not agent_name:
      return ToolResult(success=False, error="Missing required parameter: agent_name")

    if not prompt:
      return ToolResult(success=False, error="Missing required parameter: prompt")

    try:
      timeout_seconds = _clamp(int(timeout_seconds), 1, ABSOLUTE_MAX_TIMEOUT_SECONDS)
    except (ValueError, TypeError):
      return ToolResult(success=False, error="Invalid numeric parameter: timeout_seconds")

    try:
      child, agent_id = await session._spawn_internal(agent_name, requester=requester)
      try:
        response = await asyncio.wait_for(child.process(prompt), timeout=timeout_seconds)
      except asyncio.TimeoutError as e:
        raise TimeoutError(
          f"Sub-agent '{agent_id}' timed out after {timeout_seconds} seconds"
        ) from e
      finally:
        session.release(child)
      logger.info("spawn_agent response", agent_id=agent_id, response=response)
      rendered = f"agent_id: {agent_id}\n\n{response}" if agent_id else response
      return ToolResult(success=True, result=rendered)
    except TimeoutError as e:
      logger.warning("spawn_agent timeout", agent_name=agent_name, timeout_seconds=timeout_seconds)
      return ToolResult(success=False, error=str(e))
    except ValueError as e:
      # Allowlist rejection, unknown agent, depth/capacity violation.
      logger.warning("spawn_agent rejected", agent_name=agent_name, error=str(e))
      hint = ", ".join(available) if available else "(none allowed)"
      return ToolResult(success=False, error=f"{e}. Available agents: {hint}")
    except Exception as e:
      logger.error("spawn_agent error", agent_name=agent_name, error=str(e))
      return ToolResult(success=False, error=f"Sub-agent error: {e}")

  spawn_agent.__name__ = "spawn_agent"
  spawn_agent.__yoker_name__ = "agent"  # type: ignore[attr-defined]
  return spawn_agent


def make_send_message_tool(session: "Session", from_id: str) -> Any:
  """Build the Session-injected ``send_message`` tool for a specific agent.

  ``send_message`` enables inter-agent messaging via tool calls. The
  Session captures itself in the closure; the calling agent's runtime
  name (``from_id``) is captured at injection time. The tool resolves the
  ``to``/``from_id`` string references (the LLM-facing agent ids) back to
  the active :class:`Agent` instances via the session's active map, then
  calls :meth:`Session.send` with the resolved instances. ``agent_id``s
  are merely string-references for the LLM.

  Args:
    session: The :class:`Session` that owns the agent (back-reference).
    from_id: The calling agent's session-assigned runtime id (the
      LLM-facing string reference).

  Returns:
    The ``send_message`` tool callable (async function).
  """

  async def send_message(
    to: Annotated[
      str,
      Text(
        "Unique id of the target active agent. Use the agent_id returned by "
        "the agent tool. The target must still be active in the session."
      ),
    ],
    message: Annotated[str, Text("Message content (the prompt for the target agent)")],
  ) -> ToolResult:
    """Send a message to another active agent in the session and return its reply."""
    if not to:
      return ToolResult(success=False, error="Missing required parameter: to")

    if not message:
      return ToolResult(success=False, error="Missing required parameter: message")

    # Resolve the LLM-facing string ids back to Agent instances in the
    # active map. The Python API operates on Agent instances; the ids are
    # mere references carried in the tool parameters.
    target_agent = session._agents_map.get(to)
    if target_agent is None:
      logger.warning("send_message target not found", from_id=from_id, to_id=to)
      return ToolResult(success=False, error=f"No active agent with id '{to}'.")
    requester_agent = session._agents_map.get(from_id)

    try:
      if requester_agent is not None:
        response = await session.send(to=target_agent, from_=requester_agent, content=message)
      else:
        # Fallback: synthesise a minimal sender when the calling agent is
        # no longer registered (e.g. primary agent released). The event
        # payload's from_id will be the captured id.
        response = await session.send(to=target_agent, from_=target_agent, content=message)
      return ToolResult(success=True, result=response)
    except ValueError as e:
      logger.warning("send_message target not found", from_id=from_id, to_id=to, error=str(e))
      return ToolResult(success=False, error=str(e))
    except Exception as e:
      logger.error("send_message error", from_id=from_id, to_id=to, error=str(e))
      return ToolResult(success=False, error=f"Send message error: {e}")

  send_message.__name__ = "send_message"
  send_message.__yoker_name__ = "send_message"  # type: ignore[attr-defined]
  return send_message


__all__ = [
  "DEFAULT_TIMEOUT_SECONDS",
  "ABSOLUTE_MAX_TIMEOUT_SECONDS",
  "make_spawn_agent_tool",
  "make_send_message_tool",
]
