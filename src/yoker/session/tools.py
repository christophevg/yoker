"""Session-injected tools: ``agent`` and ``send_message`` (MBI-007 Phase 4).

PR #43 Clarifications 2 & 4: ``agent`` and ``send_message`` are
Session-injected tools — the :class:`yoker.session.Session` captures itself
in the closure (back-reference) and registers the tools on Agents it owns.
They are NOT registered by the Agent itself and are not part of the Agent's
static tool set loaded from plugins.

``agent`` (7.8.3, PR #43 Clarifications 2 & 5):
  - Calls ``session.spawn(name, prompt, timeout, requester=<calling agent>)``.
  - Returns a ``ToolResult`` carrying both the spawned agent's unique id and
    its response string (so the model can address the child later via
    ``send_message``).
  - Available agent names are baked into the tool description from the
    calling agent's ``AgentDefinition.agents`` allowlist (intersected with
    ``session.agents.names``) — only allowlisted names are shown.

``send_message`` (7.8.6, PR #43 Clarification 4):
  - Builds a :class:`yoker.session.Message` and calls ``session.send(...)``.
  - ``from_id`` is the calling agent's runtime name (captured at injection
    time).
  - Returns the target agent's response string, or an error result when the
    target is no longer active (PR #43 Clarification 7 — finished agents are
    removed from the active map).

``ListAgents`` is deferred to a follow-up MBI (PR #43 Clarification 6) and is
NOT injected here.
"""

from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.session.message import Message
from yoker.session.spawn_result import SpawnResult
from yoker.tools.annotations import Text
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.session import Session

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS: int = 300
ABSOLUTE_MAX_TIMEOUT_SECONDS: int = 3600


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def _render_spawn_result(result: SpawnResult) -> str:
  """Render a SpawnResult into a model-readable string.

  The contract (PR #43 Clarification 5) is "the model can read the spawned
  agent's id from the result". Both fields are rendered so the model can
  extract the id and the response.
  """
  if result.agent_id:
    return f"agent_id: {result.agent_id}\n\n{result.response}"
  return result.response


def make_spawn_agent_tool(session: "Session", requester: "Agent") -> Any:
  """Build the Session-injected ``agent`` tool for a specific agent.

  PR #43 Clarification 2: the Session captures itself in the closure and
  registers the tool on Agents it owns. The requesting agent is also
  captured so the allowlist check (PR #43 Clarification 3) fires inside
  ``session.spawn``.

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
      result: SpawnResult = await session.spawn(
        agent_name,
        prompt,
        requester=requester,
        timeout_seconds=timeout_seconds,
      )
      logger.info("spawn_agent response", agent_id=result.agent_id, response=result.response)
      return ToolResult(success=True, result=_render_spawn_result(result))
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

  PR #43 Clarification 4: ``send_message`` enables inter-agent messaging via
  tool calls. The Session captures itself in the closure; the calling
  agent's runtime name (``from_id``) is captured at injection time so the
  tool can build a :class:`Message` with the correct ``from_id``.

  Args:
    session: The :class:`Session` that owns the agent (back-reference).
    from_id: The calling agent's session-assigned runtime id (Decision 2).
      Used as ``Message.from_id``.

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

    msg = Message(from_id=from_id, to_id=to, content=message)
    try:
      response = await session.send(msg)
      return ToolResult(success=True, result=response)
    except ValueError as e:
      # Unknown target — finished agents are removed from the active map
      # (PR #43 Clarification 7).
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
