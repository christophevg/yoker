"""Agent definition validation for Yoker.

Validates agent definitions against configuration constraints.
"""

from yoker.agents.schema import AgentDefinition, AllToolsSentinel
from yoker.config import ToolsConfig
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

  Bare names (``"read"``) are checked against the built-in tool config.
  Namespaced names (``"yoker:read"``, ``"pkg:echo"``, ``"file:Read"``) are
  plugin/file-specific and skipped — the runtime ``_warn_missing_tools``
  check is authoritative for those.

  Args:
    tools: Tools specified in agent definition.
    tools_config: Global tools configuration.
    path: Configuration path for warning messages.

  Returns:
    List of validation warnings. Unknown bare tools and disabled tools
    both produce warnings (no raises) so wiring this onto the runtime path
    never blocks agent construction — the runtime ``_warn_missing_tools``
    check stays authoritative.
  """
  # Map of bare built-in tool names to their config attributes.
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
    # Namespaced tools are plugin/file-specific; skip static validation.
    if ":" in tool:
      continue
    normalized = tool.lower()
    if normalized not in known_tools:
      warnings.append(f"Tool '{tool}' is not a known built-in tool (path: {path})")
    elif normalized not in enabled_tools:
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

  # Validate tools. Empty/missing tools are valid (Option C): an agent with
  # tools=ALL_TOOLS gets all tools at runtime; tools=() gets no tools. When
  # the sentinel is set there is no explicit list to validate, so skip.
  # isinstance narrows the union for mypy; AllToolsSentinel is a singleton so
  # this is equivalent to `definition.tools is ALL_TOOLS`.
  if not isinstance(definition.tools, AllToolsSentinel):
    warnings.extend(validate_tools(definition.tools, tools_config, "agent.tools"))

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
