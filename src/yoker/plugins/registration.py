"""Register plugin components with Yoker registries.

Provides functions to register tools, skills, and agents with namespace prefixes.
"""

from structlog import get_logger

from yoker.skills import Skill, SkillRegistry
from yoker.tools import ToolRegistry
from yoker.tools.schema import ToolSpec

logger = get_logger(__name__)


def register_tools(
  tools: list[ToolSpec],
  registry: "ToolRegistry",
  namespace: str,
) -> list[str]:
  """Register pre-built ToolSpec objects with namespace prefix.

  Tools are already parsed into ToolSpec objects during plugin load,
  so this function simply registers them in the registry.

  Args:
    tools: List of ToolSpec objects (already namespaced).
    registry: ToolRegistry to register with.
    namespace: Package namespace prefix (for logging).

  Returns:
    List of registered tool names (with namespace).

  Raises:
    ValueError: If tool name already registered.
  """
  registered = []

  for tool_spec in tools:
    if tool_spec.name in registry:
      raise ValueError(f"Tool '{tool_spec.name}' is already registered")

    registry[tool_spec.name] = tool_spec
    registered.append(tool_spec.name)

    logger.info(
      "tool_registered",
      original_name=tool_spec.simple_name,
      namespaced_name=tool_spec.name,
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


# def _clone_agent_with_name(
#   agent_def: "AgentDefinition",
#   new_simple_name: str,
# ) -> "AgentDefinition":
#   """Create a copy of agent definition with a different simple name.

#   ``name`` is a derived property (``namespace:simple_name``); the underlying
#   field is ``simple_name``, so that is what gets replaced.
#   """
#   from dataclasses import fields as dataclass_fields

#   field_values = {f.name: getattr(agent_def, f.name) for f in dataclass_fields(agent_def)}
#   field_values["simple_name"] = new_simple_name

#   return type(agent_def)(**field_values)


__all__ = [
  "register_tools",
  "register_skills",
  "register_agents",
]
