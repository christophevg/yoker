"""Agent definition loading for plugins.

Plugin agents are loaded from a package's ``agents/`` directory via
:func:`load_agents_from_package`, which delegates to the agents-layer loader
(:mod:`yoker.agents.loader`) using :mod:`yoker.resources` for location. Agent
*reference resolution* (by name) is no longer a plugin concern: it is handled
by the spawning agent's :class:`~yoker.agents.AgentRegistry` (populated from
configured directories and loaded plugins), invoked via
``--with <pkg> --agent <name>``.
"""

from typing import TYPE_CHECKING

from structlog import get_logger

from yoker.agents.loader import load_agent_definitions
from yoker.resources import find_package_subdirectory

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition

logger = get_logger(__name__)


def load_agents_from_package(
  package: str,
  agents_dir: str = "agents",
) -> list["AgentDefinition"]:
  """Load agents from a package's agents/ folder.

  Args:
    package: Package name.
    agents_dir: Directory name within the package.

  Returns:
    List of AgentDefinition objects.
  """
  return _load_agents_from_subdirectory(package, package, agents_dir)


def _load_agents_from_subdirectory(
  package: str,
  namespace: str,
  agents_dir: str,
) -> list["AgentDefinition"]:
  """Load agents from a single package subdirectory."""
  path = find_package_subdirectory(package, agents_dir)
  if path is None:
    return []
  return list(load_agent_definitions(path, namespace=namespace).values())


def load_agent_definition_from_string(
  content: str,
  namespace: str | None = None,
) -> "AgentDefinition | None":
  """Load an agent definition from Markdown content with YAML frontmatter.

  This is a thin wrapper around the shared parser in :mod:`yoker.agents.loader`.

  Args:
    content: Markdown content.
    namespace: Optional namespace prefix.

  Returns:
    AgentDefinition if valid, None otherwise.
  """
  from yoker.agents.loader import parse_agent_definition, parse_frontmatter

  try:
    frontmatter, body = parse_frontmatter(content)
    return parse_agent_definition(
      frontmatter,
      body,
      source_path="",
      namespace=namespace,
      strict=False,
    )
  except Exception as e:
    logger.warning("agent_definition_parse_failed", error=str(e))
    return None


__all__ = [
  "load_agents_from_package",
  "load_agent_definition_from_string",
]
