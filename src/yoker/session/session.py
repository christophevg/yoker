"""Session class — async context manager owning a team of agents (MBI-007).

A :class:`Session` is the container+coordinator for a team of agents. It owns:

  - the session id namespace (Decision 2, §6.3)
  - the name→agent map (Decision 2)
  - the :class:`yoker.agents.AgentRegistry` (Decision 10)
  - recursion depth tracking (Decision 1)
  - event aggregation handlers (Decision 5)
  - shared backends (Decision 9; populated in 7.5)

Phase 1 (this module) implements only the lifecycle skeleton: construction
with a unique id, async context manager protocol emitting ``SESSION_START``
and ``SESSION_END`` events, event handler registration, name disambiguation,
and the ``get_agent`` lookup. Spawning, messaging, registry population, and
backend sharing land in later phases.

The recursion depth limit is read from ``config.tools.agent.max_recursion_depth``
(Decision 7 / task 7.6.3 — the field stays where it is; only the consumer
changes from Agent to Session).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from structlog import get_logger

from yoker.agents import AgentRegistry
from yoker.backends import ModelBackend
from yoker.config import Config
from yoker.events import Event, EventCallback, EventType, SessionEndEvent, SessionStartEvent

if TYPE_CHECKING:
  from yoker.agent import Agent

logger = get_logger(__name__)


class Session:
  """Async context manager that owns a team of agents.

  Args:
    config: The root :class:`Config` the session reads session-level
      settings from (``config.session`` and ``config.tools.agent``).
    session_id: Optional explicit session id. When omitted a UUID-based
      id is generated.
  """

  def __init__(
    self,
    config: Config,
    *,
    session_id: str | None = None,
  ) -> None:
    self.config: Config = config
    self.id: str = session_id if session_id is not None else self._generate_session_id()

    # name → Agent instance (D2). Populated by spawn() in 7.8.2.
    self._agents_map: dict[str, Agent] = {}
    # Shared agent definitions registry (D10). Populated in 7.3.1.
    self._agent_registry: AgentRegistry = AgentRegistry()
    # agent name → current recursion depth (D1). Tracked in 7.8.2.
    self._recursion_depths: dict[str, int] = {}
    # Session-scoped event handlers (D5). Replaces agent.add_event_handler
    # for session-scoped consumers.
    self._event_handlers: list[EventCallback] = []
    # Shared backends keyed by provider config signature (D9; 7.5).
    self._backends: dict[str, ModelBackend] = {}
    # Outstanding spawned agent tasks, cancelled on __aexit__.
    self._tasks: set[asyncio.Task] = set()
    # Tracks disambiguation suffix counters per definition name (D2).
    self._name_counters: dict[str, int] = {}

  # --- lifecycle -----------------------------------------------------------

  async def __aenter__(self) -> Session:
    """Enter the session context; emit SESSION_START."""
    self._emit(SessionStartEvent(type=EventType.SESSION_START, session_id=self.id))
    return self

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: object | None,
  ) -> None:
    """Exit the session context; cancel outstanding tasks and emit SESSION_END.

    Outstanding spawned agent tasks are cancelled before the SESSION_END
    event is emitted so handlers observe a clean teardown order.
    """
    for task in list(self._tasks):
      task.cancel()
    # Await cancellation so the tasks observe CancelledError.
    if self._tasks:
      await asyncio.gather(*self._tasks, return_exceptions=True)
    self._tasks.clear()
    self._emit(SessionEndEvent(type=EventType.SESSION_END, session_id=self.id))

  # --- event handlers ------------------------------------------------------

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register a session-scoped event handler.

    Handlers receive events emitted by the Session (session-level events)
    and, once event aggregation lands (7.7), agent events wrapped in a
    ``SessionEvent`` envelope.
    """
    self._event_handlers.append(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a previously registered event handler."""
    try:
      self._event_handlers.remove(handler)
    except ValueError:
      logger.warning("remove_event_handler: handler not registered")

  def _emit(self, event: Event) -> None:
    """Fan an event out to all registered session handlers.

    Both sync and async handlers are supported. Async handlers are
    scheduled on the running loop without awaiting (fire-and-forget);
    sync handlers are invoked directly.
    """
    for handler in list(self._event_handlers):
      try:
        result = handler(event)
        if asyncio.iscoroutine(result):
          # Schedule but don't block the emitter; track for cleanup.
          task = asyncio.ensure_future(result)
          self._tasks.add(task)
          task.add_done_callback(self._tasks.discard)
      except Exception:
        logger.exception("session event handler raised")

  # --- agent map -----------------------------------------------------------

  def get_agent(self, name: str) -> Agent | None:
    """Look up an active agent by its session-assigned name.

    Returns ``None`` when no active agent has the given name (including
    when the agent has finished and been removed per Clarification 7).
    """
    return self._agents_map.get(name)

  def _generate_agent_name(self, definition_name: str) -> str:
    """Disambiguate a definition name into a unique session agent name.

    The first spawn of ``definition_name`` returns the name unchanged.
    Subsequent spawns are suffixed ``-2``, ``-3``, ... (Decision 2).
    """
    count = self._name_counters.get(definition_name, 0) + 1
    self._name_counters[definition_name] = count
    if count == 1:
      return definition_name
    return f"{definition_name}-{count}"

  # --- helpers -------------------------------------------------------------

  @staticmethod
  def _generate_session_id() -> str:
    """Generate a UUID-based session id."""
    return uuid.uuid4().hex

  @property
  def max_recursion_depth(self) -> int:
    """Session-level recursion depth limit.

    Reads ``config.tools.agent.max_recursion_depth`` (task 7.6.3 — the
    field location is unchanged; only the consumer moves from Agent to
    Session).
    """
    return self.config.tools.agent.max_recursion_depth


__all__ = ["Session"]
