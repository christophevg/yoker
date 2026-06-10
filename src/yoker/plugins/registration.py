"""Register plugin components with Yoker registries.

Provides functions to register tools, skills, and agents with namespace prefixes.
"""

from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.skills import Skill, SkillRegistry
  from yoker.tools import Tool, ToolRegistry

log = get_logger(__name__)


def register_tools(
  tools: list["Tool"],
  registry: "ToolRegistry",
  namespace: str,
) -> list[str]:
  """Register tools with namespace prefix.

  Creates a namespaced name for each tool: {namespace}:{tool.name}

  Args:
    tools: List of Tool instances.
    registry: ToolRegistry to register with.
    namespace: Package namespace prefix (e.g., "pkgq", "yoker").

  Returns:
    List of registered tool names (with namespace).

  Raises:
    ValueError: If tool name already registered.
  """
  registered = []

  for tool in tools:
    # Create namespaced name
    namespaced_name = f"{namespace}:{tool.name}"

    # Check for collision
    if registry.get(namespaced_name):
      existing = registry.get(namespaced_name)
      log.warning(
        "tool_name_collision",
        name=namespaced_name,
        namespace=namespace,
        existing=existing.__class__.__name__ if existing else None,
        new=tool.__class__.__name__,
      )
      raise ValueError(
        f"Tool '{namespaced_name}' is already registered "
        f"(from {existing.__class__.__name__ if existing else 'unknown'})"
      )

    # Clone tool with namespaced name
    namespaced_tool = _clone_tool_with_name(tool, namespaced_name)

    registry.register(namespaced_tool)
    registered.append(namespaced_name)

    log.info(
      "tool_registered",
      original_name=tool.name,
      namespaced_name=namespaced_name,
      namespace=namespace,
    )

  return registered


def _clone_tool_with_name(tool: "Tool", new_name: str) -> "Tool":
  """Create a copy of tool with namespaced name.

  Tools use @property for name, so we create a wrapper class
  that overrides the name property.

  Args:
    tool: Original tool instance.
    new_name: New name for the tool.

  Returns:
    New tool instance with namespaced name.

  Note:
    Since Tool.name is a property, we can't directly set it.
    Instead, we create a wrapper that provides the new name.
    This preserves all other tool functionality.
  """
  # Import here to avoid circular dependency
  from yoker.tools import Tool

  # Create a new tool class that wraps the original
  class NamespacedTool(Tool):
    """Wrapper tool that provides a namespaced name."""

    _wrapped: Tool
    _name: str

    def __init__(self, wrapped: Tool, name: str):
      self._wrapped = wrapped
      self._name = name
      # Copy guardrail reference
      self._guardrail = wrapped._guardrail

    @property
    def name(self) -> str:
      return self._name

    @property
    def description(self) -> str:
      return self._wrapped.description

    def get_schema(self) -> dict[str, Any]:
      schema = self._wrapped.get_schema()
      # Update name in schema
      if "function" in schema:
        schema["function"]["name"] = self._name
      return schema

    async def execute(self, **kwargs: Any) -> Any:
      return await self._wrapped.execute(**kwargs)

    # Copy other methods
    def exists(self, path: str) -> bool:
      return self._wrapped.exists(path)

  return NamespacedTool(tool, new_name)


def register_skills(
  skills: list["Skill"],
  registry: "SkillRegistry",
  namespace: str,
) -> list[str]:
  """Register skills with namespace prefix.

  Skills already support namespace via Skill.namespace attribute.
  The full_name property returns 'namespace:name' format.

  Args:
    skills: List of Skill instances.
    registry: SkillRegistry to register with.
    namespace: Package namespace prefix.

  Returns:
    List of registered skill names (full_name with namespace).

  Raises:
    ValueError: If skill name already registered.
  """
  registered = []

  log.info(
    "register_skills_started",
    namespace=namespace,
    skills_count=len(skills),
    skill_names=[s.name for s in skills],
  )

  for skill in skills:
    # Create namespaced skill
    # Skill is a frozen dataclass, so we create a new instance
    from dataclasses import fields as dataclass_fields

    field_values = {f.name: getattr(skill, f.name) for f in dataclass_fields(skill)}
    field_values["namespace"] = namespace

    from yoker.skills import Skill

    namespaced_skill = Skill(**field_values)

    try:
      registry.register(namespaced_skill)
      registered.append(namespaced_skill.full_name)

      log.info(
        "skill_registered",
        original_name=skill.name,
        namespaced_name=namespaced_skill.full_name,
        namespace=namespace,
      )
    except ValueError as e:
      # Skill already registered
      log.warning(
        "skill_name_collision",
        name=namespaced_skill.full_name,
        namespace=namespace,
        error=str(e),
      )
      raise

  return registered


def register_agents(
  agents: list["AgentDefinition"],
  namespace: str,
) -> list[str]:
  """Register agents with namespace prefix.

  Note: AgentRegistry doesn't exist yet, this is for future use.

  Args:
    agents: List of AgentDefinition instances.
    namespace: Package namespace prefix.

  Returns:
    List of registered agent names (namespaced).

  Note:
    This function prepares agents with namespace prefixes but does not
    register them with a registry. The registry parameter will be added
    when AgentRegistry is implemented.

    Agents loaded from plugins are already namespaced (e.g., "yoker_plugin_demo:demo"),
    so we check if the agent is already namespaced and use it as-is.
  """
  # Future implementation - prepare namespaced names
  registered = []

  for agent_def in agents:
    # Check if agent is already namespaced
    # Agents loaded from plugins via load_agent_definition_from_string are already namespaced
    if ":" in agent_def.name:
      # Already namespaced - use as-is
      namespaced_name = agent_def.name
      log.info(
        "agent_already_namespaced",
        name=agent_def.name,
        namespace=namespace,
      )
    else:
      # Add namespace prefix
      namespaced_name = f"{namespace}:{agent_def.name}"
      log.info(
        "agent_prepared",
        original_name=agent_def.name,
        namespaced_name=namespaced_name,
        namespace=namespace,
      )
    registered.append(namespaced_name)

  return registered


def _clone_agent_with_name(
  agent_def: "AgentDefinition",
  new_name: str,
) -> "AgentDefinition":
  """Create a copy of agent definition with namespaced name."""
  from dataclasses import fields as dataclass_fields

  field_values = {f.name: getattr(agent_def, f.name) for f in dataclass_fields(agent_def)}
  field_values["name"] = new_name

  return type(agent_def)(**field_values)


__all__ = [
  "register_tools",
  "register_skills",
  "register_agents",
]
