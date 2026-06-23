"""Register plugin components with Yoker registries.

Provides functions to register tools, skills, and agents with namespace prefixes.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from structlog import get_logger

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition, AgentRegistry
  from yoker.skills import Skill, SkillRegistry
  from yoker.tools import ToolRegistry

logger = get_logger(__name__)


def register_tools(
  tools: list[Callable[..., Any]],
  registry: "ToolRegistry",
  namespace: str,
) -> list[str]:
  """Register tools with namespace prefix.

  Creates a namespaced name for each tool: {namespace}:{tool_name}

  Args:
    tools: List of functions or callable class instances.
    registry: ToolRegistry to register with.
    namespace: Package namespace prefix (e.g., "pkgq", "yoker").

  Returns:
    List of registered tool names (with namespace).

  Raises:
    ValueError: If tool name already registered.
  """
  registered = []

  for tool in tools:
    spec = registry.register(tool, namespace=namespace)
    registered.append(spec.name)

    logger.info(
      "tool_registered",
      original_name=spec.name.split(":", 1)[-1],
      namespaced_name=spec.name,
      namespace=namespace,
    )

  return registered


def register_skills(
  skills: list["Skill"],
  registry: "SkillRegistry",
  namespace: str,
) -> list[str]:
  """Register skills with namespace prefix.

  Skills are loaded with their namespace already set by load_skills().
  This function registers them in the registry.

  Args:
    skills: List of Skill instances (namespace already set).
    registry: SkillRegistry to register with.
    namespace: Package namespace prefix (for logging).

  Returns:
    List of registered skill names.

  Raises:
    ValueError: If skill name already registered.
  """
  registered = []

  logger.info(
    "register_skills_started",
    namespace=namespace,
    skills_count=len(skills),
    skill_names=[s.name for s in skills],
  )

  for skill in skills:
    try:
      registry.register(skill)
      registered.append(skill.name)
      logger.info(
        "skill_registered",
        skill_name=skill.name,
        namespace=namespace,
      )
    except ValueError as e:
      logger.warning(
        "skill_name_collision",
        name=skill.name,
        namespace=namespace,
        error=str(e),
      )
      raise

  return registered


def register_agents(
  agents: list["AgentDefinition"],
  registry: "AgentRegistry",
  namespace: str,
) -> list[str]:
  """Register agents with namespace prefix into the AgentRegistry.

  Agents are frozen dataclasses, so a namespaced copy is registered. Agents
  loaded from a package's ``agents/`` directory already carry the package
  namespace, so re-setting it is a no-op for them; manifest-declared agents
  (constructed in code without a namespace) get the plugin namespace applied.

  Args:
    agents: List of AgentDefinition instances.
    registry: AgentRegistry to register with.
    namespace: Package namespace prefix (e.g., "pkgq", "yoker").

  Returns:
    List of registered agent names (with namespace).

  Raises:
    ValueError: If an agent name is already registered.
  """
  from dataclasses import fields as dataclass_fields

  from yoker.agents import AgentDefinition

  registered = []

  logger.info(
    "register_agents_started",
    namespace=namespace,
    agents_count=len(agents),
    agent_names=[a.name for a in agents],
  )

  for agent_def in agents:
    field_values = {f.name: getattr(agent_def, f.name) for f in dataclass_fields(agent_def)}
    field_values["namespace"] = namespace
    namespaced_agent = AgentDefinition(**field_values)

    try:
      registry.register(namespaced_agent)
      registered.append(namespaced_agent.name)
      logger.info(
        "agent_registered",
        original_name=agent_def.name,
        namespaced_name=namespaced_agent.name,
        namespace=namespace,
      )
    except ValueError as e:
      logger.warning(
        "agent_name_collision",
        name=namespaced_agent.name,
        namespace=namespace,
        error=str(e),
      )
      raise

  return registered


def _clone_agent_with_name(
  agent_def: "AgentDefinition",
  new_simple_name: str,
) -> "AgentDefinition":
  """Create a copy of agent definition with a different simple name.

  ``name`` is a derived property (``namespace:simple_name``); the underlying
  field is ``simple_name``, so that is what gets replaced.
  """
  from dataclasses import fields as dataclass_fields

  field_values = {f.name: getattr(agent_def, f.name) for f in dataclass_fields(agent_def)}
  field_values["simple_name"] = new_simple_name

  return type(agent_def)(**field_values)


__all__ = [
  "register_tools",
  "register_skills",
  "register_agents",
]
