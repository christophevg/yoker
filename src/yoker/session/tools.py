"""Session-injected tools: ``agent``, ``send_message``, and ``release_agent``

``agent``, ``send_message``, and ``release_agent`` are
Session-injected tools — the :class:`yoker.session.Session` captures itself
in the closure (back-reference) and registers the tools on Agents it owns.
They are NOT registered by the Agent itself and are not part of the Agent's
static tool set loaded from plugins.

``agent``
  - Calls ``session._spawn_internal(name, requester=<calling agent>)``,
    runs the spawned agent's ``process(prompt)`` with a timeout.
  - When ``ephemeral=True``, the agent is automatically released after its
    response (single-shot, no follow-up possible, no agent_id returned).
  - When ``ephemeral=False`` (default), the agent remains in the session's
    active map so the parent can send follow-up messages via
    ``send_message``. The session's ``__aexit__`` cleans up all agents on
    exit.
  - Returns a ``ToolResult`` carrying the spawned agent's unique id (when
    persistent) and its response string.
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
    target is no longer active.

``release_agent``
  - Releases a persistent spawned agent, freeing session capacity.
  - Calls ``session.release(agent)``, which emits AGENT_FINISHED, cancels
    the agent's consumer task, and removes it from the active map.
  - After release, ``send_message`` to that agent will fail ("No active
    agent with id ...").
  - Useful for freeing session capacity when a persistent agent's work is
    complete (e.g. after implementation + review feedback iteration is
    done).
"""

import asyncio
import time
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.agents.schema import ALL_AGENTS
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


async def _process_excluding_approval_wait(
  child: "Agent",
  prompt: str,
  session: "Session",
  approval_wait_baseline: float,
  timeout_seconds: int,
) -> str:
  """Run ``child.process(prompt)`` with a timeout that excludes approval-wait time.

  The effective budget is ``timeout_seconds`` of *work* time — time the
  user spends on approval prompts (tracked on the session) does not count.
  This prevents the sub-agent from timing out while blocked on user input.

  The coroutine polls every 0.5s: if the work-time budget is exhausted,
  it cancels the underlying ``process`` task and raises ``asyncio.TimeoutError``.
  """
  task = asyncio.create_task(child.process(prompt))
  start = time.monotonic()

  while True:
    try:
      # Wait for the task to complete, or poll after a short interval.
      await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
      return task.result()
    except asyncio.TimeoutError:
      # Task didn't finish in 0.5s — check the *work-time* budget.
      approval_wait = session.approval_wait_seconds - approval_wait_baseline
      work_time = time.monotonic() - start - approval_wait
      if work_time >= timeout_seconds:
        task.cancel()
        try:
          await task
        except (asyncio.CancelledError, Exception):
          pass
        raise asyncio.TimeoutError() from None
    except asyncio.CancelledError:
      task.cancel()
      try:
        await task
      except (asyncio.CancelledError, Exception):
        pass
      raise


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
  allowlist = requester.definition.agents
  registry_names = set(session.agents.names) if session.agents else set()
  if allowlist is ALL_AGENTS:
    # Any registered agent may be spawned — show the full registry.
    available = sorted(registry_names)
  else:
    available = [n for n in allowlist if n in registry_names]
  if not available:
    # Fall back to the full allowlist when the registry isn't populated yet
    # (e.g. agents loaded lazily). The allowlist is the authoritative gate.
    available = list(allowlist) if allowlist is not ALL_AGENTS else []

  label = "Name of the agent to spawn"
  if available:
    label += f" (available: {', '.join(available)})"

  async def spawn_agent(
    agent_name: Annotated[str, Text(label)],
    prompt: Annotated[str, Text("Task for the spawned agent")],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ephemeral: Annotated[
      bool,
      Text(
        "When True, the agent is automatically released after its response "
        "(single-shot, no follow-up possible). When False (default), the agent "
        "stays active and can be addressed via send_message for follow-up work."
      ),
    ] = False,
  ) -> ToolResult:
    """Spawn a sub-agent to perform a specific task.

    When ephemeral=False (default), returns the spawned agent's unique id
    and its response so you can address it later via send_message.
    When ephemeral=True, the agent is released after responding and no
    agent_id is returned (single-shot, no follow-up possible).
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

      # Record approval-wait baseline so we can exclude time the user spent
      # deliberating on approval prompts from the sub-agent's wall-clock
      # timeout.  Without this, a 300s timeout can fire while the agent is
      # blocked waiting for the user to approve a git push.
      approval_wait_before = session.approval_wait_seconds
      try:
        response = await asyncio.wait_for(
          _process_excluding_approval_wait(
            child, prompt, session, approval_wait_before, timeout_seconds
          ),
          timeout=timeout_seconds + 3600,  # generous hard ceiling; real check is inside
        )
      except asyncio.TimeoutError as e:
        raise TimeoutError(
          f"Sub-agent '{agent_id}' timed out after {timeout_seconds} seconds"
        ) from e

      if ephemeral:
        # Single-shot: release the agent immediately after its response.
        # No agent_id is returned since the agent is no longer addressable.
        await session.release(child)
        logger.info("spawn_agent ephemeral response", agent_name=agent_name, response=response)
        return ToolResult(success=True, result=response)

      # Persistent: keep the agent in the active map so the parent can send
      # follow-up messages via send_message. The session's __aexit__ cleans
      # up all agents on exit.
      logger.info("spawn_agent response", agent_id=agent_id, response=response)
      rendered = f"agent_id: {agent_id}\n\n{response}" if agent_id else response
      return ToolResult(success=True, result=rendered)
    except TimeoutError as e:
      logger.warning("spawn_agent timeout", agent_name=agent_name, timeout_seconds=timeout_seconds)
      return ToolResult(success=False, error=str(e))
    except ValueError as e:
      # Allowlist rejection, unknown agent, depth/capacity violation.
      logger.warning("spawn_agent rejected", agent_name=agent_name, error=str(e))
      # Show all registered agent names so the LLM can self-correct.
      registry_names = sorted(session.agents.names) if session.agents else []
      hint = ", ".join(registry_names) if registry_names else "(none registered)"
      return ToolResult(
        success=False,
        error=f"{e}. Available agents: {hint}",
      )
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


def make_release_agent_tool(session: "Session") -> Any:
  """Build the Session-injected ``release_agent`` tool.

  ``release_agent`` lets the spawning agent explicitly terminate a
  persistent spawned agent, freeing session capacity. After release,
  the agent's context is lost and ``send_message`` to it will fail.

  Args:
    session: The :class:`Session` that owns the agents (back-reference).

  Returns:
    The ``release_agent`` tool callable (async function).
  """

  async def release_agent(
    agent_id: Annotated[
      str,
      Text(
        "The agent_id of the active agent to release. "
        "The agent's context is lost after release. "
        "Use this to free session capacity when a persistent agent is no longer needed."
      ),
    ],
  ) -> ToolResult:
    """Release a spawned agent, freeing session capacity.

    The agent's conversation context is lost after release.
    Use this when a persistent agent's work is complete and you no longer
    need to send it follow-up messages.
    """
    if not agent_id:
      return ToolResult(success=False, error="Missing required parameter: agent_id")

    target_agent = session._agents_map.get(agent_id)
    if target_agent is None:
      logger.warning("release_agent target not found", agent_id=agent_id)
      return ToolResult(success=False, error=f"No active agent with id '{agent_id}'.")

    try:
      await session.release(target_agent)
      logger.info("release_agent released", agent_id=agent_id)
      return ToolResult(success=True, result=f"Agent '{agent_id}' released.")
    except Exception as e:
      logger.error("release_agent error", agent_id=agent_id, error=str(e))
      return ToolResult(success=False, error=f"Release agent error: {e}")

  release_agent.__name__ = "release_agent"
  release_agent.__yoker_name__ = "release_agent"  # type: ignore[attr-defined]
  return release_agent


__all__ = [
  "DEFAULT_TIMEOUT_SECONDS",
  "ABSOLUTE_MAX_TIMEOUT_SECONDS",
  "make_spawn_agent_tool",
  "make_send_message_tool",
  "make_release_agent_tool",
]
