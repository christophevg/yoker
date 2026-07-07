"""Agent registry for managing available agents.

Provides :class:`AgentRegistry`, a thin ``UserDict`` subclass that manages
:class:`AgentDefinition` objects keyed by their namespaced name
(``namespace:simple_name``).
"""

from collections import UserDict

from structlog import get_logger

from yoker.agents import load_agent_definitions
from yoker.agents.schema import AgentDefinition
from yoker.config import Config
from yoker.plugins.loader import load_plugins

logger = get_logger(__name__)


class AgentRegistry(UserDict[str, AgentDefinition]):
  """Registry for available agent definitions, keyed by namespaced name.

  Inherited ``UserDict`` behaviour provides ``get`` (returns None when absent),
  ``__contains__``, ``__getitem__``, ``__iter__`` and ``__len__``.
  """

  def register(self, definition: AgentDefinition, namespace: str | None = None) -> None:
    """
    Raises:
      ValueError: If an agent with the same name is already registered.
    """
    if namespace:
      definition.namespace = namespace
    if definition.name in self.data:
      logger.warning("agent_name_collision", name=definition.name)
      raise ValueError(f"Agent '{definition.name}' is already registered")
    self.data[definition.name] = definition
    logger.info("agent registered", name=definition.name)

  def register_all(self, agents: list[AgentDefinition], namespace: str) -> None:
    logger.info(
      "register_agents_started",
      namespace=namespace,
      agents_count=len(agents),
      agent_names=[a.name for a in agents],
    )
    for agent_def in agents:
      self.register(agent_def, namespace=namespace)

  def register_plugin_agents(self, config: "Config", extra_plugins: tuple[str, ...] = ()) -> None:
    for plugin in load_plugins(config, extra_plugins):
      if plugin.agents:
        logger.info("registering plugin agents", package=plugin.source)
        self.register_all(plugin.agents, namespace=plugin.source)

  def register_config_agents(self, config: Config) -> None:
    for directory in config.agents.directories:
      try:
        logger.info("loading configured agents", source=directory)
        for agent in load_agent_definitions(directory):
          self.register(agent)
      except Exception as e:
        logger.warning("loading agents failed", directory=directory, error=str(e))

  def load(self, config: Config, extra_plugins: tuple[str, ...] = ()) -> None:
    self.register_config_agents(config)
    self.register_plugin_agents(config, extra_plugins)

  @property
  def agents(self) -> list[AgentDefinition]:
    """Return all registered agents sorted by name."""
    return sorted(self.data.values(), key=lambda d: d.name)

  @property
  def names(self) -> list[str]:
    """Return all registered agent names sorted alphabetically."""
    return sorted(self.data.keys())

  @property
  def namespaces(self) -> list[str]:
    """Return all registered agent namespaces sorted alphabetically.

    Unnamespaced definitions (``namespace`` is None) are excluded.
    """
    return sorted({d.namespace for d in self.data.values() if d.namespace})

  def resolve(self, name: str) -> AgentDefinition:
    """Resolve an agent reference to a definition.

    A namespaced name (``pkg:agent``) matches the exact key. A bare name
    (no namespace) matches any registered agent whose ``simple_name`` equals
    it; if exactly one such agent exists it is returned, if several do a
    ``ValueError`` is raised listing the full names so the caller can
    disambiguate.

    Args:
      name: Full namespaced name or bare simple name.

    Returns:
      The matching AgentDefinition.

    Raises:
      ValueError: If no agent matches, or a bare name matches several.
    """
    defn = self.get(name)
    if defn is not None:
      return defn
    if ":" in name:
      raise ValueError(f"Agent not found: {name}")
    matches = [d for d in self.data.values() if d.simple_name == name]
    if len(matches) == 1:
      return matches[0]
    if len(matches) > 1:
      full = ", ".join(sorted(d.name for d in matches))
      raise ValueError(f"Agent '{name}' is ambiguous: {full}")
    raise ValueError(f"Agent not found: {name}")


__all__ = ["AgentRegistry"]
