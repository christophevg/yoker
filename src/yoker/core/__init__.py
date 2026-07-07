"""

Asynchronous Agent implementation for Yoker.

"""

import asyncio
import inspect
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from structlog import get_logger

from yoker.agents import (
  AgentDefinition,
  load_agent_definition,
)
from yoker.backends import ModelBackend, create_backend
from yoker.builtin import make_skill_tool
from yoker.config import Config, get_yoker_config
from yoker.context import ContextManager, create_context_manager
from yoker.core._processing import process_message
from yoker.core._setup import create_web_guardrails
from yoker.core.thinking import ThinkingMode
from yoker.events import EventCallback
from yoker.exceptions import SkillError
from yoker.logging import configure_logging
from yoker.plugins import load_plugins, warn_plugins_disabled
from yoker.skills import SkillRegistry, load_skills
from yoker.tools import ToolRegistry
from yoker.tools.guardrails import Guardrail
from yoker.tools.guardrails.path import PathGuardrail

logger = get_logger(__name__)


class Agent:
  """Asynchronous agent that chats with model backends and uses tools."""

  def __init__(
    self,
    config: "Config | None" = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    agent_definition: AgentDefinition | None = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    plugins: tuple[str, ...] = (),
    backend: "ModelBackend | None" = None,
    parse_cli_args: bool = False,
    console_logging: bool = True,
  ) -> None:
    """Initialize the async agent.

    Args:
      config: Optional explicit config. If omitted, config is discovered via
        Clevis after loading .env / .env.local files.
      thinking_mode: Thinking mode for the model.
      agent_definition: Optional explicit agent definition. When provided,
        takes precedence over ``agent_path`` and config-based discovery.
      agent_path: Optional path to an agent definition file.
      context_manager: Optional context manager.
      plugins: Optional plugin packages to load (tools/skills only; plugin
        agent definitions are registered by the Session layer).
      backend: Optional ModelBackend instance. If not provided, one is
        created from ``config``.
      parse_cli_args: Whether to parse CLI arguments
      console_logging: Whether to enable console logging. The CLI sets this to
        False so the UI layer owns all terminal output.
    """

    # load env vars from .env files (we shouldn't have to do this, but hey 😇)
    load_dotenv(Path(".env"))
    load_dotenv(Path(".env.local"))

    # adopt config or load yoker configuration
    self.config: Config = config if config else get_yoker_config(cli=parse_cli_args)

    # with config available, configure logging (will be skipped if already done)
    configure_logging(self.config.logging, console=console_logging)
    logger.info("agent config", source="provided" if config else "loaded")

    # config sanity: plugin packages listed but plugins disabled
    if not self.config.plugins.enabled and self.config.plugins.packages:
      warn_plugins_disabled()

    # set up registries for tools and skills.
    self.tools: ToolRegistry = ToolRegistry()
    self.skills: SkillRegistry = SkillRegistry()

    # CLI-supplied plugin packages (--with), kept separate from config.plugins.packages.
    self._cli_plugins: tuple[str, ...] = plugins

    # skills are loaded from directories specified in config (per-agent).
    self._load_skills()

    # load tools and skills from plugins. Plugin agent definitions are
    # skipped here (no session registry); the Session layer registers them.
    loaded_plugins = list(load_plugins(self.config, self._cli_plugins))
    self.tools.register_plugin_tools(loaded_plugins, self.config)
    self.skills.register_plugin_skills(loaded_plugins)

    # load own definition
    self.definition: AgentDefinition = self._resolve_agent_definition(agent_definition, agent_path)

    # check that all requested tools for the agent are available (warn before filtering)
    self._warn_missing_tools()

    # filter tools based on agent definition (only keep specified tools)
    self._filter_tools_by_definition()

    # Skill tool: registered when skills are available and the tool is enabled.
    if self.config.tools.skill.enabled and len(self.skills):
      self.tools.register(make_skill_tool(self.skills), namespace="yoker")

    # setup the model
    self.model: str = self._resolve_model()
    self.thinking_mode: ThinkingMode = thinking_mode

    # setup the backend for the model provider. When a backend is provided
    # (e.g. shared from a Session), use it; otherwise create one from config.
    if backend is not None:
      self._backend: ModelBackend | None = backend
    else:
      self._backend = create_backend(self.config)

    # prepare guardrails
    query_guardrail, url_guardrail = create_web_guardrails(self.config)
    self._guardrails: dict[str, Guardrail | None] = {
      "path": PathGuardrail(self.config),
      "query": query_guardrail,
      "url": url_guardrail,
    }

    # tool backends for context injection. Populated for the configured
    # provider (Ollama today) so the websearch/webfetch tools resolve to
    # OllamaWebSearchBackend / OllamaWebFetchBackend instead of failing
    # with "No backend configured".
    # Note: We extract the Ollama client from the backend for web tools.
    self._tool_backends: dict[str, Any] = self._create_tool_backends()

    # set up the context manager (config-driven via factory when not provided)
    self.context: ContextManager = (
      context_manager
      if context_manager is not None
      else create_context_manager(self.config, self.definition.name)
    )

    # back-reference triggers initial context + skill discovery block setup
    self.context.agent = self

    self._event_handlers: list[EventCallback] = []

    # agent process queue:
    # serializes concurrent ``process()`` calls so the backend never sees
    # parallel ``chat_stream`` invocations on the same agent. Lazily
    # initialized on the first ``process()`` call.
    self._process_queue: asyncio.Queue[tuple[str, asyncio.Future[str]]] | None = None
    self._process_task: asyncio.Task[None] | None = None

    logger.info("agent", agent=self)
    logger.debug("agent", skills=list(self.skills.keys()))
    logger.debug("agent", tools=list(self.tools.keys()))

  def __repr__(self) -> str:
    return f"Agent({self.definition.name},tools={len(self.tools)},skills={len(self.skills)})"

  def on_event(self, handler: EventCallback) -> EventCallback:
    """Register an event handler and return it for chaining.

    Accepts a sync or async callable accepting an :class:`yoker.events.Event`
    (or a :class:`yoker.events.SessionEvent` envelope when the agent is part
    of a :class:`yoker.session.Session`).

    Args:
      handler: A callable accepting an :class:`yoker.events.Event`. May be
        sync or async.

    Returns:
      The same ``handler`` callable, so callers can chain or inline the
      registration (e.g. ``agent.on_event(print)``).
    """
    is_async = inspect.iscoroutinefunction(handler) or (
      callable(handler) and inspect.iscoroutinefunction(type(handler).__call__)
    )
    logger.info(
      "handler registered",
      handler=getattr(handler, "__name__", str(handler)),
      is_async=is_async,
    )
    self._event_handlers.append(handler)
    return handler

  async def do(
    self,
    skill_name: str,
    prompt: str,
    args: str = "",
  ) -> str:
    """Invoke a skill as a command on this agent and return the response.

    Loads the skill's context into the conversation (via
    :meth:`inject_skill_context`) and then runs a single
    :meth:`process` turn. The skill must be discoverable in the agent's
    skill registry (loaded from configured directories or plugins).

    Args:
      skill_name: Name of the skill to invoke (bare or namespaced).
      prompt: The user's task. Sent as the user message after the skill
        context is injected. May be empty when the skill content alone is
        enough to drive the turn.
      args: Optional arguments forwarded to the skill's invocation block.

    Returns:
      The assistant's response string for the turn.
    """
    resolved = self._resolve_skill_name(skill_name)
    self.inject_skill_context(resolved, args or None)
    return await self.process(prompt)

  def _resolve_skill_name(self, skill_name: str) -> str:
    """Resolve a skill name to its registry key.

    Accepts either the full registry key (``"ns:skill"``) or a bare simple
    name (``"skill"``). When a bare name matches exactly one registered skill
    (across any namespace) that key is used; when it matches multiple, the
    first one (alphabetically) is used. Raises :class:`SkillError` if no
    match is found.
    """
    if skill_name in self.skills.data:
      return skill_name
    # Bare-name match across namespaces.
    matches = [
      key for key, skill in self.skills.data.items() if (skill.simple_name or "") == skill_name
    ]
    if matches:
      return sorted(matches)[0]
    available = ", ".join(sorted(self.skills.names))
    raise SkillError(
      skill_name,
      f"Unknown skill. Available skills: {available}" if available else "Unknown skill",
    )

  @staticmethod
  def filter_skills(registry: SkillRegistry, requested: list[str]) -> None:
    """Keep only ``requested`` skills in ``registry``; raise on unknown names.

    Mutates ``registry`` in place. Bare names try the ``yoker:`` namespace as
    a fallback; namespaced names must match exactly.
    """
    available = {name.lower(): name for name in registry.data.keys()}
    keep: set[str] = set()
    for name in requested:
      normalized = name.lower()
      actual = (
        available.get(normalized)
        if ":" in normalized
        else available.get(normalized) or available.get(f"yoker:{normalized}")
      )
      if actual is None:
        raise SkillError(
          name,
          f"Unknown skill. Available skills: {', '.join(sorted(registry.names))}"
          if registry.names
          else "Unknown skill (no skills loaded).",
        )
      keep.add(actual)
    for key in [k for k in list(registry.data.keys()) if k not in keep]:
      del registry.data[key]

  @property
  def guardrail(self) -> PathGuardrail:
    """Return the path guardrail for file system operations.

    Returns:
        PathGuardrail: The guardrail instance for path validation.
    """
    guardrail = self._guardrails.get("path")
    if guardrail is None:
      raise RuntimeError("Path guardrail not initialized")
    # Type narrow: we know path is always PathGuardrail
    return guardrail  # type: ignore

  async def process(self, message: str) -> str:
    """Process a single message and return the response.

    Concurrent ``process()`` calls on the same agent are serialized via an
    internal ``asyncio.Queue``. When a turn is in flight, additional calls
    wait in the queue and are processed strictly one at a time — the
    backend never sees parallel ``chat_stream`` invocations on the same
    agent. The public API is unchanged: callers simply
    ``await agent.process(msg)`` and the
    queueing is transparent.

    Cancels the consumer task on cancellation, propagating
    ``CancelledError`` to the awaiting caller.
    """
    if self._process_queue is None:
      self._process_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    await self._process_queue.put((message, future))
    if self._process_task is None or self._process_task.done():
      self._process_task = asyncio.ensure_future(self._process_consumer())
    try:
      return await future
    except asyncio.CancelledError:
      # The caller cancelled. Drop the request if pending; the consumer
      # handles in-flight cancellation via the future.
      if not future.done():
        future.cancel()
      raise

  async def _process_consumer(self) -> None:
    """Background consumer that processes queued requests one at a time.

    Loops indefinitely waiting on the queue; each (message, future) pair is
    processed by :func:`process_message` and the result (or exception) is
    set on the future so the awaiting ``process()`` caller sees it. The
    consumer stays alive between requests (blocking on ``queue.get()``)
    and is cleaned up via task cancellation when the agent is garbage
    collected or the event loop closes.
    """
    assert self._process_queue is not None
    while True:
      try:
        message, future = await self._process_queue.get()
      except asyncio.CancelledError:
        # Cancel any pending futures so their awaiters see cancellation.
        while not self._process_queue.empty():
          _, pending = self._process_queue.get_nowait()
          if not pending.done():
            pending.cancel()
        raise
      try:
        result = await process_message(self, message)
        if not future.done():
          future.set_result(result)
      except Exception as exc:
        if not future.done():
          future.set_exception(exc)
      finally:
        self._process_queue.task_done()

  def inject_skill_context(self, skill_name: str, args: str | None = None) -> None:
    """Inject skill context into the conversation."""
    from yoker.skills import format_invocation_block

    skill = self.skills.get(skill_name)
    if skill is None:
      available = ", ".join(self.skills.names)
      raise SkillError(
        skill_name,
        f"Unknown skill. Available skills: {available}" if available else "Unknown skill",
      )

    self.context.add_message("user", format_invocation_block(skill, args or ""))
    logger.info(
      "skill context injected",
      skill_name=skill_name,
      skill_full_name=skill.name,
      has_args=bool(args),
    )

  def _warn_missing_tools(self) -> None:
    """Log warnings for agent-definition tools not present in the registry.

    Built-in tools may omit the ``yoker:`` prefix and are matched
    case-insensitively. Plugin tools must be referenced with their full
    namespaced name.
    """
    available = {name.lower() for name in self.tools.names}
    missing: list[str] = []

    for requested in self.definition.tools:
      normalized = requested.lower()
      if ":" in normalized:
        matched = normalized in available
      else:
        matched = normalized in available or f"yoker:{normalized}" in available
      if not matched:
        missing.append(requested)

    if missing:
      logger.warning(
        "agent tools unavailable",
        agent=self.definition.name,
        missing_tools=missing,
        available_tools=list(self.tools.names),
      )

  def _filter_tools_by_definition(self) -> None:
    """Filter tools in registry to only those specified in agent definition.

    If the agent definition specifies an empty tools tuple, all tools are kept
    (default agent behavior). If tools are specified, only those tools are kept.
    """
    # Default agent (no explicit definition) keeps all tools
    if self.definition.simple_name is None and self.definition.namespace is None:
      return

    # Empty tools tuple means no tools (agent explicitly requests no tools)
    if len(self.definition.tools) == 0:
      logger.debug(
        "agent_tools_empty",
        agent=self.definition.name,
        cleared_tools=list(self.tools.names),
      )
      self.tools.clear()
      return

    # Build set of requested tool names (case-insensitive, with yoker: prefix handling)
    requested = set()
    for tool_name in self.definition.tools:
      normalized = tool_name.lower()
      if ":" in normalized:
        requested.add(normalized)
      else:
        # Add both with and without yoker: prefix for built-in tools
        requested.add(normalized)
        requested.add(f"yoker:{normalized}")

    # Filter tools to only those requested
    available = list(self.tools.names)
    to_remove = []

    for tool_name in available:
      # Check if tool matches any requested tool (case-insensitive)
      normalized = tool_name.lower()
      if normalized not in requested:
        to_remove.append(tool_name)

    if to_remove:
      for tool_name in to_remove:
        del self.tools.data[tool_name]
      logger.debug(
        "agent_tools_filtered",
        agent=self.definition.name,
        kept_tools=list(self.tools.names),
        removed_tools=to_remove,
      )

  def _resolve_agent_definition(
    self, definition: "AgentDefinition | None", path: Path | str | None
  ) -> AgentDefinition:
    """Resolve the agent definition from explicit value, path, config or default.

    The Agent is Session-agnostic: it resolves definitions only from an
    explicit ``definition``/``path`` argument or from ``config.agent`` /
    ``config.agents.definition`` when they point at a filesystem path.
    Name-based registry resolution (through ``session.agents``) is handled by
    the Session layer, which passes the resolved ``agent_definition`` here.
    """
    if definition is not None:
      logger.info("agent definition provided", name=definition.name)
      return definition

    reference: str | None = None
    if path:
      reference = str(path)
    elif self.config.agent:
      reference = self.config.agent
    elif self.config.agents.definition:
      reference = self.config.agents.definition
    else:
      # not provided, not in config
      return AgentDefinition()

    # An existing filesystem path is loaded directly. A non-path reference is
    # a name that must be resolved by the Session layer before constructing
    # the Agent (the Agent has no registry of its own).
    file_path = Path(reference).expanduser()
    if file_path.exists() and file_path.is_file():
      try:
        definition = load_agent_definition(reference)
        logger.info("agent definition loaded", reference=reference, name=definition.name)
        return definition
      except ValueError:
        logger.warning("agent definition not found", definition=reference)
        raise

    logger.warning(
      "agent definition not resolvable",
      definition=reference,
      reason="no registry available on a Session-agnostic Agent",
    )
    raise ValueError(
      f"Agent definition '{reference}' cannot be resolved by a standalone Agent. "
      "Pass an explicit agent_definition=, an agent_path= to a file, or construct "
      "the Agent within a Session so the Session can resolve the name."
    )

  def _resolve_model(self) -> str:
    """Determine the model to use from agent definition or config."""
    if self.definition and self.definition.model:
      logger.info(
        "model from agent definition", model=self.definition.model, agent=self.definition.name
      )
      return self.definition.model

    # Read from the active provider's config
    # Validation in BackendConfig.__post_init__ ensures config is always set
    sub_config = self.config.backend.config
    model = sub_config.model

    if not model:
      raise ValueError(
        f"No model specified for provider '{self.config.backend.provider}'. "
        "Specify a model in the agent definition or configure the provider."
      )

    logger.info("model from config", model=model, provider=self.config.backend.provider)
    return model

  def _create_tool_backends(self) -> dict[str, Any]:
    """Create tool backends for web tools.

    Delegates to the backend's create_tool_backends() method if available.

    Returns:
      A dict mapping tool names to backend instances. May be empty.
    """
    backends: dict[str, Any] = {}

    # Delegate to backend if it supports tool backends
    if hasattr(self._backend, "create_tool_backends"):
      backends = self._backend.create_tool_backends()  # type: ignore

    return backends

  def _load_skills(self) -> None:
    """Load skills from configured directories into the registry."""
    for directory in self.config.skills.directories:
      try:
        new_skills = load_skills(directory).items()
        for _, skill in new_skills:
          self.skills.register(skill)
        logger.info("skills loaded", count=len(new_skills), source=directory)
      except Exception as e:
        logger.warning("loading skills failed", directory=directory, error=str(e))
