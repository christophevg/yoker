"""

Asynchronous Agent implementation for Yoker.

"""

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
from ollama import AsyncClient
from structlog import get_logger

from yoker.agent._processing import process_message
from yoker.agent._setup import (
  add_skill_discovery_block,
  create_client,
  create_web_guardrails,
  validate_recursion_depth,
)
from yoker.agents import (
  AgentDefinition,
  AgentRegistry,
  load_agent_definition,
  load_agent_definitions,
)
from yoker.config import Config, get_yoker_config
from yoker.context import ContextManager
from yoker.context.basic import SimpleContextManager
from yoker.events import EventCallback
from yoker.logging import configure_logging
from yoker.plugins import load_configured_plugins
from yoker.skills import SkillRegistry, load_skills
from yoker.thinking import ThinkingMode
from yoker.tools import ToolRegistry, make_agent_tool, make_skill_tool
from yoker.tools.guardrails import Guardrail
from yoker.tools.path_guardrail import PathGuardrail

if TYPE_CHECKING:
  from yoker.context import ContextManager
  from yoker.tools.path_guardrail import PathGuardrail

logger = get_logger(__name__)


class Agent:
  """Asynchronous agent that chats with Ollama and uses tools."""

  def __init__(
    self,
    config: "Config | None" = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    agent_definition: AgentDefinition | None = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    plugins: list[str] | None = None,
    _recursion_depth: int = 0,
    client: "AsyncClient | None" = None,
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
      client: Optional Ollama async client.
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

    # all tools, skills and agents are registered. add skill/agent tool IF skills
    # /agents are available AND if allowed to use them
    if self.config.tools.skill.enabled and len(self.tools):
      self.tools.register(make_skill_tool(self.skills), namespace="yoker")

    if self.config.tools.agent.enabled and len(self.agents):
      if "agent" in self.definition.tools:
        self.tools.register(make_agent_tool(parent_agent=self))

    # check that all "requested/required" tools for the agent are available (fail-fast)
    self._warn_missing_tools()

    # setup the model
    self.model: str = self._resolve_model()
    self.thinking_mode: ThinkingMode = thinking_mode

    # setup the client to the model-provider backend
    self._client: AsyncClient | None = client or create_client(self.config, AsyncClient)

    # prepare guardrails
    query_guardrail, url_guardrail = create_web_guardrails(self.config)
    self._guardrails: dict[str, Guardrail | None] = {
      "path": PathGuardrail(self.config),
      "query": query_guardrail,
      "url": url_guardrail,
    }

    # tool backends for context injection (populated when tools are registered)
    self._tool_backends: dict[str, Any] = {}

    # set up the context manager
    self.context: ContextManager = context_manager or SimpleContextManager(self)
    # TODO -> responsibility of context manager
    add_skill_discovery_block(self.config, self.skills, self.context)

    self._event_handlers: list[EventCallback] = []

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

  async def process(self, message: str) -> str:
    """Process a single message and return the response."""
    return await process_message(self, message)

  def inject_skill_context(self, skill_name: str, args: str | None = None) -> None:
    """Inject skill context into the conversation."""
    from yoker.exceptions import SkillError
    from yoker.skills import format_invocation_block

    registry = self.skills
    if registry is None:
      raise SkillError(skill_name, "No skill registry available")

    skill = registry.get(skill_name)
    if skill is None:
      available = ", ".join(registry.names)
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
    if self.definition is None:
      return

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
    """Determine the model to use."""
    if self.definition and self.definition.model:
      logger.info(
        "model from agent definition", model=self.definition.model, agent=self.definition.name
      )
      return self.definition.model
    logger.info("model from config", model=self.config.backend.ollama.model)
    return self.config.backend.ollama.model

  def _load_skills(self):
    """Load skills from configured directories into the registry."""
    for directory in self.config.skills.directories:
      try:
        new_skills = load_skills(directory).items()
        for _, skill in new_skills:
          self.skills.register(skill)
        logger.info("skills loaded", count=len(new_skills), source=directory)
      except Exception as e:
        logger.warning("loading skills failed", directory=directory, error=str(e))

  def _load_agents(self):
    """Load agents from configured directories into the registry."""
    for directory in self.config.agents.directories:
      try:
        new_agents = load_agent_definitions(directory).items()
        for _, agent in new_agents:
          self.agents.register(agent)
        logger.info("agents loaded", count=len(new_agents), source=directory)
      except Exception as e:
        logger.warning("loading agents failed", directory=directory, error=str(e))
