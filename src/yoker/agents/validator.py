"""Agent definition validation for Yoker.

Validates agent definitions against configuration constraints.
"""

from yoker.agents.schema import AgentDefinition
from yoker.config.schema import ToolsConfig
from yoker.exceptions import ValidationError


def validate_non_empty_string(value: str, path: str) -> None:
  """Validate that a value is a non-empty string.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is empty.
  """
  if not value or not value.strip():
    raise ValidationError(path, value, "must be a non-empty string")


def validate_tools(
  tools: tuple[str, ...],
  tools_config: ToolsConfig,
  path: str,
) -> list[str]:
  """Validate tools against enabled tools configuration.

  Args:
    tools: Tools specified in agent definition.
    tools_config: Global tools configuration.
    path: Configuration path for error messages.

  Returns:
    List of validation warnings (tool not enabled but specified).

  Raises:
    ValidationError: If any specified tool is not recognized.
  """
  # Map of tool names to their config attributes
  known_tools = {
    "list": tools_config.list,
    "read": tools_config.read,
    "write": tools_config.write,
    "update": tools_config.update,
    "search": tools_config.search,
    "agent": tools_config.agent,
    "git": tools_config.git,
  }

  warnings: list[str] = []
  enabled_tools = {name for name, config in known_tools.items() if config.enabled}

  for tool in tools:
    if tool.lower() not in known_tools:
      raise ValidationError(path, tool, f"unknown tool '{tool}'")

    if tool.lower() not in enabled_tools:
      warnings.append(f"Tool '{tool}' is specified but not enabled in configuration")

  return warnings


def validate_agent_definition(
  definition: AgentDefinition,
  tools_config: ToolsConfig,
  existing_names: set[str] | None = None,
) -> list[str]:
  """Validate an agent definition.

  Args:
    definition: Agent definition to validate.
    tools_config: Global tools configuration.
    existing_names: Set of already-used agent names (for uniqueness check).

  Returns:
    List of validation warnings.

  Raises:
    ValidationError: If validation fails.
  """
  warnings: list[str] = []

  # Validate required fields
  validate_non_empty_string(definition.name, "agent.name")
  validate_non_empty_string(definition.description, "agent.description")

  # Validate tools
  if not definition.tools:
    raise ValidationError("agent.tools", definition.tools, "must specify at least one tool")

  warnings.extend(
    validate_tools(definition.tools, tools_config, "agent.tools")
  )

  # Check uniqueness
  if existing_names and definition.name in existing_names:
    raise ValidationError(
      "agent.name",
      definition.name,
      f"agent name must be unique, '{definition.name}' already defined",
    )

  # Warn if no system prompt
  if not definition.system_prompt.strip():
    warnings.append("Agent has no system prompt (empty Markdown body)")

  return warnings


__all__ = [
  "validate_agent_definition",
  "validate_tools",
  "validate_non_empty_string",
]
