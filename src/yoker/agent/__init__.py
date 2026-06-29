"""

Asynchronous Agent implementation for Yoker.

"""

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
from structlog import get_logger

from yoker.agent._processing import process_message
from yoker.agent._setup import (
  add_skill_discovery_block,
  create_web_guardrails,
  validate_recursion_depth,
)
from yoker.agent.thinking import ThinkingMode
from yoker.agents import (
  AgentDefinition,
  AgentRegistry,
  load_agent_definition,
  load_agent_definitions,
)
from yoker.backends import ModelBackend, create_backend
from yoker.builtin import make_agent_tool, make_skill_tool
from yoker.config import Config, get_yoker_config
from yoker.context import ContextManager
from yoker.context.basic import SimpleContextManager
from yoker.events import EventCallback
from yoker.logging import configure_logging
from yoker.plugins import load_configured_plugins
from yoker.skills import SkillRegistry, load_skills
from yoker.tools import ToolRegistry
from yoker.tools.guardrails import Guardrail
from yoker.tools.guardrails.path import PathGuardrail

if TYPE_CHECKING:
  pass

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
    plugins: list[str] | None = None,
    _recursion_depth: int = 0,
    backend: "ModelBackend | None" = None,
    parse_cli_args: bool = False,
    console_logging: bool = True,
  ) -> None:
    """Initialize the async agent.

    Args:
      config: Optional explicit config. If omitted, config is discovered via
        Clevis after loading .env / .env.local files.
      thinking_mode: Thinking mode for the model.
      agent_definition: Optional explicit agent definition.
      agent_path: Optional path to an agent definition.
      context_manager: Optional context manager.
      plugins: Optional plugin packages to load.
      _recursion_depth: Internal recursion depth tracking.
      backend: Optional ModelBackend instance. If not provided, one will be
        created from config.
      parse_cli_args: Whether to parse CLI arguments
      console_logging: Whether to enable console logging. The CLI sets this to
        False so the UI layer owns all terminal output.
    """

    # load env vars from .env files (we shouldn't have to do this, but hey 😇)
    _ = load_dotenv(Path(".env"))
    _ = load_dotenv(Path(".env.local"))

    # adopt config or load yoker configuration
    self.config: Config = config if config else get_yoker_config(cli=parse_cli_args)

    # with config available, configure logging (will be skipped if already done)
    configure_logging(self.config.logging, console=console_logging)
    logger.info("agent config", source="provided" if config else "loaded")

    # set up registries for tools, skills and agents.
    self.tools: ToolRegistry = ToolRegistry()
    self.skills: SkillRegistry = SkillRegistry()
    self.agents: AgentRegistry = AgentRegistry()

    # additional plugin packages requested on the CLI (--with). Config is
    # frozen, so these are threaded through to the plugin loader directly.
    self._cli_plugins: tuple[str, ...] = tuple(plugins) if plugins else ()

    # skills and agents can be loaded from directories specified in config
    self._load_skills()
    self._load_agents()

    # load more skills, agents and tools from plugins
    load_configured_plugins(self, self.config, self._cli_plugins)

    # load own definition
    self.definition: AgentDefinition = self._resolve_agent_definition(agent_definition, agent_path)
    self.recursion_depth = validate_recursion_depth(self.config, _recursion_depth)
    self.max_recursion_depth = self.config.tools.agent.max_recursion_depth

    # check that all requested tools for the agent are available (warn before filtering)
    self._warn_missing_tools()

    # filter tools based on agent definition (only keep specified tools)
    self._filter_tools_by_definition()

    # all tools, skills and agents are registered. add skill/agent tool IF skills
    # /agents are available AND if allowed to use them
    if self.config.tools.skill.enabled and len(self.skills):
      self.tools.register(make_skill_tool(self.skills), namespace="yoker")

    if self.config.tools.agent.enabled and len(self.agents):
      if "agent" in self.definition.tools or len(self.definition.tools) == 0:
        self.tools.register(make_agent_tool(parent_agent=self), namespace="yoker")

    # setup the model
    self.model: str = self._resolve_model()
    self.thinking_mode: ThinkingMode = thinking_mode

    # setup the backend for the model provider
    self._backend: ModelBackend | None = backend or create_backend(self.config)

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

    # set up the context manager
    # Note: Use explicit None check because empty UserList is falsy
    if context_manager is not None:
      # Use provided context manager - add system messages like SimpleContextManager does
      self.context: ContextManager = context_manager
      self._setup_context()
    else:
      # Create default SimpleContextManager which sets up context in __init__
      self.context = SimpleContextManager(self)

    add_skill_discovery_block(self.config, self.skills, self.context)

    self._event_handlers: list[EventCallback] = []

    logger.info("agent", agent=self)
    logger.debug("agent", skills=list(self.skills.keys()))
    logger.debug("agent", tools=list(self.tools.keys()))

  def __repr__(self) -> str:
    return f"Agent({self.definition.name},tools={len(self.tools)},skills={len(self.skills)})"

  def _setup_context(self) -> None:
    """Set up context with system messages (environment reminder and system prompt)."""
    from pathlib import Path

    harness = self.config.harness
    harness_name = harness.name
    harness_version = f" v{harness.version}" if harness.version else ""
    harness_author = f" by {harness.author}" if harness.author else ""
    harness_id = f"{harness_name}{harness_version}{harness_author}"
    environment_reminder = (
      f"You are running inside the Yoker agent harness ({harness_id}). "
      f"Current working directory: {Path.cwd()}. Model in use: {self.model}."
    )
    self.context.add_message("system", environment_reminder)
    self.context.add_message("system", self.definition.system_prompt)

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler."""
    is_async = inspect.iscoroutinefunction(handler) or (
      callable(handler) and inspect.iscoroutinefunction(type(handler).__call__)
    )
    logger.info(
      "handler registered",
      handler=getattr(handler, "__name__", str(handler)),
      is_async=is_async,
    )
    self._event_handlers.append(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler."""
    self._event_handlers.remove(handler)

  def get_event_handlers(self) -> list[EventCallback]:
    """Return a copy of the registered event handlers."""
    return self._event_handlers.copy()

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
    """Process a single message and return the response."""
    return await process_message(self, message)

  def inject_skill_context(self, skill_name: str, args: str | None = None) -> None:
    """Inject skill context into the conversation."""
    from yoker.exceptions import SkillError
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
    """Resolve the agent definition from explicit value, path, config or default."""
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

    # An existing filesystem path is loaded directly. Otherwise the reference
    # is a name resolved through the AgentRegistry, already populated from
    # configured directories and loaded plugins (--with <pkg> + --agent <name>).
    file_path = Path(reference).expanduser()
    if file_path.exists() and file_path.is_file():
      try:
        definition = load_agent_definition(reference)
        logger.info("agent definition loaded", reference=reference, name=definition.name)
        return definition
      except ValueError:
        logger.warning("agent definition not found", definition=reference)
        raise

    # Name -> registry lookup. A bare name matches a unique simple_name across
    # namespaces; a namespaced name matches exactly. Raises ValueError if not
    # found or ambiguous.
    try:
      definition = self.agents.resolve(reference)
    except ValueError:
      logger.warning("agent definition not found", definition=reference)
      raise
    logger.info("agent definition loaded", reference=reference, name=definition.name)
    return definition

  def _resolve_model(self) -> str:
    """Determine the model to use from agent definition or config."""
    if self.definition and self.definition.model:
      logger.info(
        "model from agent definition", model=self.definition.model, agent=self.definition.name
      )
      return self.definition.model

    # Read from the active provider's config using the generic property
    sub_config = self.config.backend.config
    if sub_config is not None:
      model = sub_config.model
    else:
      # Fallback to Ollama config (default provider)
      if self.config.backend.ollama:
        model = self.config.backend.ollama.model
      else:
        raise ValueError("No model configured and no fallback available")

    logger.info("model from config", model=model, provider=self.config.backend.provider)
    return model

  def _create_tool_backends(self) -> dict[str, Any]:
    """Create tool backends for web tools.

    Populates the ``_tool_backends`` dict used by the ``websearch`` and
    ``webfetch`` tools. Backends are only populated when:
    - The configured provider is ``ollama`` (the only supported web-tool provider).
    - An Ollama API key is configured.
    - The corresponding tool is enabled in config.

    Returns:
      A dict mapping tool names to backend instances. May be empty.
    """
    backends: dict[str, Any] = {}

    # Web tools only work with Ollama
    if self.config.backend.provider != "ollama":
      return backends

    # Use the generic config property
    sub_config = self.config.backend.config
    if sub_config is None:
      return backends

    # Access api_key through the config
    # Type: ignore is needed because we know this is OllamaConfig but mypy doesn't
    api_key = getattr(sub_config, 'api_key', None)  # type: ignore
    if not api_key:
      return backends

    # Extract the Ollama client from the backend for web tools
    # The OllamaBackend wraps the AsyncClient
    from yoker.backends.ollama import OllamaBackend

    if not isinstance(self._backend, OllamaBackend):
      return backends

    client = self._backend._client

    if self.config.tools.websearch.enabled:
      from yoker.tools.web import OllamaWebSearchBackend

      backends["websearch"] = OllamaWebSearchBackend(
        async_client=client,
        timeout_seconds=self.config.tools.websearch.timeout_seconds,
      )
      logger.info("web_search_backend_populated", backend="ollama")

    if self.config.tools.webfetch.enabled:
      from yoker.tools.web import OllamaWebFetchBackend

      backends["webfetch"] = OllamaWebFetchBackend(
        async_client=client,
        timeout_seconds=self.config.tools.webfetch.timeout_seconds,
        max_size_kb=self.config.tools.webfetch.max_size_kb,
      )
      logger.info("web_fetch_backend_populated", backend="ollama")

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

  def _load_agents(self) -> None:
    """Load agents from configured directories into the registry."""
    for directory in self.config.agents.directories:
      try:
        new_agents = load_agent_definitions(directory).items()
        for _, agent in new_agents:
          self.agents.register(agent)
        logger.info("agents loaded", count=len(new_agents), source=directory)
      except Exception as e:
        logger.warning("loading agents failed", directory=directory, error=str(e))

