"""Session class — async context manager owning a team of agents.

A :class:`Session` is the container+coordinator for a team of agents. It owns:
  - the session id namespace
  - the name→agent map
  - the :class:`yoker.agents.AgentRegistry`
  - recursion depth tracking
  - event aggregation handlers
  - shared backends
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from typing import TYPE_CHECKING

from structlog import get_logger

from yoker.agents import AgentDefinition, AgentRegistry, load_agent_definitions
from yoker.backends import ModelBackend, create_backend
from yoker.config import Config
from yoker.events import (
  AgentFinishedEvent,
  AgentMessageEvent,
  AgentSpawnedEvent,
  Event,
  EventCallback,
  EventType,
  SessionEndEvent,
  SessionEvent,
  SessionStartEvent,
)
from yoker.session.message import Message
from yoker.session.spawn_result import SpawnResult
from yoker.session.tools import make_send_message_tool, make_spawn_agent_tool

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
    self.id: str = session_id if session_id is not None else uuid.uuid4().hex

    # name → Agent instance. Populated by spawn().
    self._agents_map: dict[str, Agent] = {}
    # Shared agent definitions registry. Populated from config directories and plugins
    self.agents: AgentRegistry = AgentRegistry()
    # agent name → current recursion depth. Tracked in spawn().
    self._recursion_depths: dict[str, int] = {}
    # Session-scoped event handlers. Replaces agent.add_event_handler
    # for session-scoped consumers.
    self._event_handlers: list[EventCallback] = []
    # Shared backends keyed by provider config signature.
    self._backends: dict[str, ModelBackend] = {}
    # Outstanding spawned agent tasks, cancelled on __aexit__.
    self._tasks: set[asyncio.Task] = set()
    # Tracks disambiguation suffix counters per definition name.
    self._name_counters: dict[str, int] = {}

    # Load agent definitions from configured directories.
    self._load_agents()

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

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register a session-scoped event handler.

    Handlers receive events emitted by the Session (session-level events)
    and, once event aggregation lands, agent events wrapped in a
    ``SessionEvent`` envelope.
    """
    self._event_handlers.append(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a previously registered event handler."""
    try:
      self._event_handlers.remove(handler)
    except ValueError:
      logger.warning("remove_event_handler: handler not registered")

  def _emit(self, event: Event | SessionEvent) -> None:
    """Fan an event out to all registered session handlers.

    Both sync and async handlers are supported. Async handlers are
    scheduled on the running loop without awaiting (fire-and-forget);
    sync handlers are invoked directly. ``event`` may be a bare session
    event (``SessionStartEvent``, ``AgentSpawnedEvent``, ...) or a
    :class:`SessionEvent` envelope wrapping an agent-emitted event
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

  def _load_agents(self) -> None:
    """Load agent definitions from configured directories into the registry.

    Relocated from ``Agent._load_agents``. The Session loads
    definitions before any Agent is constructed so agents can resolve their
    own definition through ``session.agents``.
    """
    for directory in self.config.agents.directories:
      try:
        new_agents = load_agent_definitions(directory).items()
        for _, agent in new_agents:
          self.agents.register(agent)
        logger.info("agents loaded", count=len(new_agents), source=directory)
      except Exception as e:
        logger.warning("loading agents failed", directory=directory, error=str(e))

  def get_agent(self, name: str) -> Agent | None:
    """Look up an active agent by its session-assigned name.

    Returns ``None`` when no active agent has the given name (including
    when the agent has finished and been removed.
    """
    return self._agents_map.get(name)

  def _generate_agent_name(self, definition_name: str) -> str:
    """Disambiguate a definition name into a unique session agent name.

    The first spawn of ``definition_name`` returns the name unchanged.
    Subsequent spawns are suffixed ``-2``, ``-3``, ...
    """
    count = self._name_counters.get(definition_name, 0) + 1
    self._name_counters[definition_name] = count
    if count == 1:
      return definition_name
    return f"{definition_name}-{count}"

  def get_backend(self, config: Config) -> ModelBackend:
    """Return a shared or fresh backend for the given config.

    Backends are cached by provider config signature. Agents
    that share the same active provider config reuse the same backend
    instance. Per-agent model/provider overrides produce a different
    signature and therefore a fresh backend.
    """
    key = self._backend_key(config)
    backend = self._backends.get(key)
    if backend is None:
      backend = create_backend(config)
      self._backends[key] = backend
    return backend

  @staticmethod
  def _backend_key(config: Config) -> str:
    """Compute a stable cache key for a config's active provider settings."""
    provider = config.backend.provider
    sub = config.backend.config
    return "|".join(
      (
        provider,
        getattr(sub, "model", "") or "",
        getattr(sub, "base_url", "") or "",
        getattr(sub, "api_key", "") or "",
      )
    )

  async def spawn(
    self,
    name: str,
    prompt: str,
    *,
    requester: Agent | None = None,
    timeout_seconds: int = 300,
  ) -> SpawnResult:
    """Spawn a child agent by name and run it to completion.

    enforces the requester's :attr:`AgentDefinition.agents` allowlist before
    resolving/spawning, resolves the definition from ``session.agents``,
    checks recursion depth and ``max_agents`` limits, creates a child
    :class:`Agent` with a session-injected backend, injects the
    Session-injected tools (``agent`` and ``send_message``) on the
    child, runs it with a timeout, and returns a :class:`SpawnResult`
    carrying both the spawned agent's unique id and its response string.

    Args:
      name: Agent definition name (bare or namespaced) to spawn.
      prompt: The prompt to send to the spawned agent.
      requester: The requesting :class:`Agent` (for allowlist enforcement).
        When ``None`` (top-level spawn) the allowlist check is bypassed.
      timeout_seconds: Maximum seconds the spawned agent may run.

    Returns:
      A :class:`SpawnResult` with ``agent_id`` (the spawned agent's unique
      session-assigned id) and ``response`` (the agent's reply string, or
      an error message on timeout/exception).

    Raises:
      ValueError: On allowlist violation, unknown agent, or capacity
        (depth / max_agents) exceeded.
      TimeoutError: When the spawned agent does not finish in time.
    """
    # Allowlist enforcement — before any other check.
    if requester is not None:
      allowed = requester.definition.agents
      if len(allowed) == 0:
        raise ValueError(f"Agent '{requester.definition.name}' has no allowed spawns.")
      if name not in allowed:
        raise ValueError(f"Agent '{name}' is not in '{requester.definition.name}' allowlist.")

    # Resolve agent definition from the session registry.
    try:
      agent_definition: AgentDefinition = self.agents.resolve(name)
    except ValueError:
      raise
    except Exception as e:
      raise ValueError(f"Agent resolution failed for '{name}': {e}") from e

    # Recursion depth check). Top-level spawn (requester is None) starts
    # at depth 1; nested spawns derive depth from the requester's tracked
    # depth in this session.
    parent_depth = 0
    if requester is not None:
      # Look up the requester's depth by matching its session-assigned name.
      # Fall back to 0 if the requester isn't tracked (e.g. primary agent).
      parent_depth = next(
        (d for n, d in self._recursion_depths.items() if self._agents_map.get(n) is requester),
        0,
      )
    child_depth = parent_depth + 1
    if child_depth > self.config.tools.agent.max_recursion_depth:
      raise ValueError(
        f"Maximum recursion depth ({self.config.tools.agent.max_recursion_depth}) exceeded. Cannot spawn sub-agent."
      )

    # max_agents cap
    if len(self._agents_map) >= self.config.session.max_agents:
      raise ValueError(f"Session max_agents limit ({self.config.session.max_agents}) reached.")

    # Derive config with model override if the definition specifies one.
    child_config = self._derive_config(self.config, agent_definition)

    # Backend: shared when same provider config, fresh when overridden (D9).
    backend = self.get_backend(child_config)

    # Unique session-assigned agent name (D2).
    agent_id = self._generate_agent_name(agent_definition.simple_name or name)

    # Construct the child Agent with a session reference
    from yoker.agent import Agent as _Agent

    child = _Agent(
      config=child_config,
      agent_definition=agent_definition,
      backend=backend,
      session=self,
      console_logging=False,
    )

    # Register in the active map and track depth.
    self._agents_map[agent_id] = child
    self._recursion_depths[agent_id] = child_depth

    # Inject Session tools ``agent`` and ``send_message`` are
    # registered on the child by the Session (closure capture).
    self.inject_tools(child, agent_id)

    # Event aggregation: register a forwarding
    # handler on the child so its events reach session-level handlers
    # wrapped in a SessionEvent envelope. Suppressed when the caller opts
    # out via ``config.session.event_aggregation``.
    if self.config.session.event_aggregation:
      child.add_event_handler(self._make_forwarding_handler(agent_id))

    # Lifecycle signal: AGENT_SPAWNED is emitted after registration so
    # handlers observe the agent in the active map.
    self._emit(
      AgentSpawnedEvent(
        type=EventType.AGENT_SPAWNED,
        session_id=self.id,
        agent_id=agent_id,
        definition_name=agent_definition.simple_name or name,
      )
    )

    try:
      response = await asyncio.wait_for(
        child.process(prompt),
        timeout=timeout_seconds,
      )
      return SpawnResult(agent_id=agent_id, response=response)
    except asyncio.TimeoutError as e:
      raise TimeoutError(f"Sub-agent '{agent_id}' timed out after {timeout_seconds} seconds") from e
    finally:
      # AGENT_FINISHED is emitted as a lifecycle signal,
      # then the agent is removed from the active list. There is no
      # `finished` state — visible states are {idle, running} only.
      self._emit(
        AgentFinishedEvent(
          type=EventType.AGENT_FINISHED,
          session_id=self.id,
          agent_id=agent_id,
        )
      )
      self._agents_map.pop(agent_id, None)
      self._recursion_depths.pop(agent_id, None)

  def inject_tools(self, agent: Agent, agent_id: str) -> None:
    """Inject Session-injected tools onto an agent

    Registers ``agent`` and ``send_message`` on the agent's tool
    registry. The Session captures itself in the closure (back-reference)
    so the tools can call ``session.spawn`` / ``session.send`` at execution
    time. ``ListAgents`` is deferred (PR #43 Clarification 6) and is NOT
    injected.

    ``agent`` is gated by ``config.tools.agent.enabled`` (the existing
    global kill-switch). ``send_message`` is always injected when an agent
    is part of a session.

    Args:
      agent: The :class:`Agent` to inject tools onto.
      agent_id: The agent's session-assigned runtime id (used as
        ``Message.from_id`` by ``send_message``).
    """
    if self.config.tools.agent.enabled:
      agent.tools.register(
        make_spawn_agent_tool(self, agent),
        namespace="yoker",
        name="agent",
      )
    agent.tools.register(
      make_send_message_tool(self, agent_id),
      namespace="yoker",
      name="send_message",
    )

  def register_primary_agent(self, agent: Agent) -> str:
    """Register the primary Agent with the session and inject Session tools.

    The primary agent is constructed by the caller (e.g. ``__main__.py``)
    rather than via ``spawn()``. This method assigns it a session-scoped
    id, adds it to the active map at recursion depth 0, and injects the
    Session-injected tools (``agent`` and ``send_message``) so the
    primary agent can spawn sub-agents and send inter-agent messages.

    Args:
      agent: The primary :class:`Agent` constructed within this session.

    Returns:
      The session-assigned agent id.
    """
    definition_name = agent.definition.simple_name or "primary"
    agent_id = self._generate_agent_name(definition_name)
    self._agents_map[agent_id] = agent
    self._recursion_depths[agent_id] = 0
    self.inject_tools(agent, agent_id)
    return agent_id

  def _make_forwarding_handler(self, agent_id: str) -> EventCallback:
    """Build a handler that wraps agent events in :class:`SessionEvent`.

    The returned handler is async: it wraps each emitted :class:`Event` in
    a :class:`SessionEvent` envelope tagged with ``agent_id`` and forwards
    it to ``session._event_handlers`` (PR #43 Clarification 9). Existing
    event dataclasses and their construction sites are untouched.
    """

    async def forward(event: Event | SessionEvent) -> None:
      # Agents emit bare events; envelopes do not reach agent handlers.
      assert not isinstance(event, SessionEvent)
      self._emit(SessionEvent(agent_id=agent_id, event=event))

    forward.__name__ = f"session_forward_{agent_id}"
    return forward

  async def send(self, message: Message) -> str:
    """Route an inter-agent message to its target agent and return the reply.

    Looks up the target agent by ``message.to_id`` in the active map,
    emits an :class:`AgentMessageEvent` carrying the message, then calls
    ``await target_agent.process(message.content)``. Request-response only
    — content is a plain string and the response is a plain string (D3,
    §6.6; no streaming).

    Args:
      message: The :class:`Message` to route. ``to_id`` must match an
        active agent's session-assigned id.

    Returns:
      The target agent's response string. When the target agent raises,
      the exception is caught and an error string is returned (preserving
        the ``agent`` tool's behaviour of not propagating exceptions).

    Raises:
      ValueError: When no active agent has the id ``message.to_id``.
    """
    target = self._agents_map.get(message.to_id)
    if target is None:
      raise ValueError(f"No active agent with id '{message.to_id}' in session '{self.id}'.")

    self._emit(
      AgentMessageEvent(
        type=EventType.AGENT_MESSAGE,
        session_id=self.id,
        from_id=message.from_id,
        to_id=message.to_id,
        content=message.content,
      )
    )

    try:
      return await target.process(message.content)
    except Exception as e:
      logger.warning(
        "session_send_failed",
        from_id=message.from_id,
        to_id=message.to_id,
        error=str(e),
      )
      return f"Error: agent '{message.to_id}' failed: {e}"

  @staticmethod
  def _derive_config(parent_config: Config, agent_definition: AgentDefinition) -> Config:
    """Build a child config with the agent definition's model override applied.

    When the definition has no ``model`` override the parent config is
    returned unchanged (so the backend is shared). When a model override
    exists, a derived config is produced via ``dataclasses.replace`` on the
    active provider's sub-config.
    """
    model = agent_definition.model
    if model is None:
      return parent_config
    sub_config = parent_config.backend.config
    new_sub = dataclasses.replace(sub_config, model=model)
    provider = parent_config.backend.provider
    # ``BackendConfig`` is a frozen dataclass; ``dataclasses.replace`` builds
    # a new instance with the overridden provider sub-config. We pass the
    # provider field via a single-key dict so the call stays provider-agnostic
    # The ``# type: ignore`` is needed because
    # mypy can't narrow the union of provider sub-config types to the named
    # field from a dynamic key.
    new_backend = dataclasses.replace(parent_config.backend, **{provider: new_sub})  # type: ignore[arg-type]
    return dataclasses.replace(parent_config, backend=new_backend)


__all__ = ["Session"]
