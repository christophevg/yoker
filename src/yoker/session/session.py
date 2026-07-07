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
from yoker.session.tools import make_send_message_tool, make_spawn_agent_tool

if TYPE_CHECKING:
  from yoker.core import Agent

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
    extra_plugins: tuple[str, ...] = (),
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
    # Register plugin-discovered agent definitions (tools/skills are loaded
    # by each Agent; agent defs are a Session concern since the Agent is
    # Session-agnostic).
    from yoker.plugins import register_configured_plugin_agents

    register_configured_plugin_agents(self.agents, config, extra_plugins)

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
    *,
    requester: Agent | None = None,
  ) -> Agent:
    """Spawn a child agent by name and return it (no prompt is run).

    The canonical sub-agent API (MBI-003 Decision 8). Thin wrapper over
    :meth:`_spawn_internal` that returns only the constructed :class:`Agent`.
    The caller drives the agent directly (e.g.
    ``await agent.process("...")``). The agent stays registered in the
    session's active map until :meth:`release` is called (or the session
    exits and cleans up).

    Args:
      name: Agent definition name (bare or namespaced) to spawn.
      requester: The requesting :class:`Agent` (for allowlist enforcement).
        When ``None`` (top-level spawn) the allowlist check is bypassed.

    Returns:
      The spawned :class:`Agent` instance.

    Raises:
      ValueError: On allowlist violation, unknown agent, or capacity
        (depth / max_agents) exceeded.
    """
    child, _agent_id = await self._spawn_internal(name, requester=requester)
    return child

  async def _spawn_internal(
    self,
    name: str,
    *,
    requester: Agent | None = None,
  ) -> tuple[Agent, str]:
    """Spawn a child agent and return ``(agent, agent_id)`` (internal).

    Enforces the requester's :attr:`AgentDefinition.agents` allowlist,
    resolves the definition from ``session.agents``, checks recursion
    depth and ``max_agents`` limits, creates a child :class:`Agent` with
    a session-injected backend, injects the Session-injected tools
    (``agent`` and ``send_message``) on the child, registers it in the
    active map, stamps the session-assigned id on the Agent as
    ``agent._session_id`` (the bridge used by :meth:`send` for event
    payloads), and emits ``AGENT_SPAWNED``. Used by the public
    :meth:`spawn` and by the Session-injected ``agent`` tool.
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

    # Recursion depth check. Top-level spawn (requester is None) starts
    # at depth 1; nested spawns derive depth from the requester's tracked
    # depth in this session.
    parent_depth = 0
    if requester is not None:
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

    # Backend: shared when same provider config, fresh when overridden.
    backend = self.get_backend(child_config)

    # Unique session-assigned agent name.
    agent_id = self._generate_agent_name(agent_definition.simple_name or name)

    # Construct the child Agent (Session-agnostic; backend injected).
    from yoker.core import Agent as _Agent

    child = _Agent(
      config=child_config,
      agent_definition=agent_definition,
      backend=backend,
      console_logging=False,
    )

    # Stamp the session-assigned id on the Agent. This is Session-managed
    # metadata (not Agent business state) — the bridge used by send() to
    # resolve Agent instances back to ids for event payloads.
    child._session_id = agent_id

    # Register in the active map and track depth.
    self._agents_map[agent_id] = child
    self._recursion_depths[agent_id] = child_depth

    # Inject Session tools ``agent`` and ``send_message`` are
    # registered on the child by the Session (closure capture).
    self.inject_tools(child, agent_id)

    # Event aggregation: register a forwarding handler on the child so its
    # events reach session-level handlers wrapped in a SessionEvent envelope.
    if self.config.session.event_aggregation:
      child.add_event_handler(self._make_forwarding_handler(agent_id))

    # Lifecycle signal: AGENT_SPAWNED is emitted after registration.
    self._emit(
      AgentSpawnedEvent(
        type=EventType.AGENT_SPAWNED,
        session_id=self.id,
        agent_id=agent_id,
        definition_name=agent_definition.simple_name or name,
      )
    )
    return child, agent_id

  def release(self, agent: Agent) -> None:
    """Release a spawned agent: emit AGENT_FINISHED and remove from the active map.

    Removes the agent by identity. When the agent is not registered (already
    released or never registered) this is a no-op. This is the single
    cleanup path used by both the ``agent`` tool and standalone callers
    that drive a spawned agent directly.
    """
    agent_id = next((aid for aid, a in self._agents_map.items() if a is agent), None)
    if agent_id is None:
      return  # already released or never registered
    self._emit(
      AgentFinishedEvent(
        type=EventType.AGENT_FINISHED,
        session_id=self.id,
        agent_id=agent_id,
      )
    )
    self._agents_map = {aid: a for aid, a in self._agents_map.items() if a is not agent}
    self._recursion_depths.pop(agent_id, None)

  def inject_tools(self, agent: Agent, agent_id: str) -> None:
    """Inject Session-injected tools onto an agent

    Registers ``agent`` and ``send_message`` on the agent's tool
    registry. The Session captures itself in the closure (back-reference)
    so the tools can call ``session.spawn`` / ``session.send`` at execution
    time. ``ListAgents`` is deferred and is NOT injected.

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
    # Stamp the session-assigned id on the Agent (bridge for send() event
    # payloads) and override its backend with the session-shared one so
    # the primary agent shares the same backend as spawned sub-agents.
    agent._session_id = agent_id
    agent._backend = self.get_backend(agent.config)
    self._agents_map[agent_id] = agent
    self._recursion_depths[agent_id] = 0
    self.inject_tools(agent, agent_id)
    self._agent: Agent = agent
    return agent_id

  @property
  def agent(self) -> Agent:
    """The primary :class:`Agent` registered via :meth:`register_primary_agent`.

    Raises:
      RuntimeError: When no primary agent has been registered.
    """
    try:
      return self._agent
    except AttributeError as e:
      raise RuntimeError("No primary agent registered with this session.") from e

  def _make_forwarding_handler(self, agent_id: str) -> EventCallback:
    """Build a handler that wraps agent events in :class:`SessionEvent`.

    The returned handler is async: it wraps each emitted :class:`Event` in
    a :class:`SessionEvent` envelope tagged with ``agent_id`` and forwards
    it to ``session._event_handlers``. Existing event dataclasses and
    their construction sites are untouched.
    """

    async def forward(event: Event | SessionEvent) -> None:
      # Agents emit bare events; envelopes do not reach agent handlers.
      assert not isinstance(event, SessionEvent)
      self._emit(SessionEvent(agent_id=agent_id, event=event))

    forward.__name__ = f"session_forward_{agent_id}"
    return forward

  async def send(self, *, to: Agent, from_: Agent, content: str) -> str:
    """Send a message from one agent to another and return the target's reply.

    The Python API accepts :class:`Agent` instances directly. The
    session-assigned ids carried on ``to._session_id`` and
    ``from_._session_id`` are used only for the :class:`AgentMessageEvent`
    payload (the LLM-facing ``agent_id`` strings are mere references).
    Emits the event, then calls ``await to.process(content)``.
    Request-response only — content is a plain string and the response is
    a plain string (no streaming).

    Args:
      to: The target :class:`Agent` (must be active in this session).
      from_: The sending :class:`Agent`.
      content: Plain-string message content (the prompt).

    Returns:
      The target agent's response string. When the target agent raises,
      the exception is caught and an error string is returned (preserving
      the ``agent`` tool's behaviour of not propagating exceptions).

    Raises:
      ValueError: When the target agent is not registered in this session.
    """
    to_id = getattr(to, "_session_id", None)
    from_id = getattr(from_, "_session_id", None)
    if to_id is None or to not in self._agents_map.values():
      raise ValueError(f"Target agent is not active in session '{self.id}'.")

    self._emit(
      AgentMessageEvent(
        type=EventType.AGENT_MESSAGE,
        session_id=self.id,
        from_id=from_id or "",
        to_id=to_id,
        content=content,
      )
    )

    try:
      return await to.process(content)
    except Exception as e:
      logger.warning(
        "session_send_failed",
        from_id=from_id,
        to_id=to_id,
        error=str(e),
      )
      return f"Error: agent '{to_id}' failed: {e}"

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
