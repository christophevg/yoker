"""Agent definition loader for Yoker.

Parses Markdown files with YAML frontmatter into AgentDefinition objects.
"""

from pathlib import Path

import yaml

from yoker.agents.schema import AgentDefinition
from yoker.exceptions import ConfigurationError, FileNotFoundError


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
  """Parse YAML frontmatter from Markdown content.

  Args:
    content: Raw file content (may contain frontmatter).

  Returns:
    Tuple of (frontmatter dict, body content).
    If no frontmatter, returns ({}, content).

  Raises:
    ConfigurationError: If frontmatter exists but is invalid YAML.
  """
  lines = content.strip().split("\n")

  # Check for frontmatter delimiter
  if not lines or lines[0] != "---":
    return {}, content

  # Find closing delimiter
  try:
    end_index = lines.index("---", 1)
  except ValueError:
    # No closing delimiter - not valid frontmatter
    return {}, content

  # Extract frontmatter and body
  frontmatter_lines = lines[1:end_index]
  body_lines = lines[end_index + 1 :]

  if not frontmatter_lines:
    # Empty frontmatter
    return {}, "\n".join(body_lines)

  # Parse YAML
  try:
    frontmatter = yaml.safe_load("\n".join(frontmatter_lines))
    if frontmatter is None:
      frontmatter = {}
    if not isinstance(frontmatter, dict):
      raise ConfigurationError(
        setting="frontmatter",
        message=f"Frontmatter must be a YAML dictionary, got {type(frontmatter).__name__}",
      )
    return frontmatter, "\n".join(body_lines)
  except yaml.YAMLError as e:
    raise ConfigurationError(
      setting="frontmatter",
      message=f"Invalid YAML in frontmatter: {e}",
    ) from None


def load_agent_definition(path: Path | str) -> AgentDefinition:
  """Load an agent definition from a Markdown file.

  Args:
    path: Path to the Markdown file.

  Returns:
    AgentDefinition object with parsed frontmatter and body.

  Raises:
    FileNotFoundError: If the file doesn't exist.
    ConfigurationError: If frontmatter is invalid or missing required fields.
  """
  file_path = Path(path)

  if not file_path.exists():
    raise FileNotFoundError(str(file_path), "agent definition")

  try:
    content = file_path.read_text(encoding="utf-8")
  except OSError as e:
    raise ConfigurationError(
      setting=str(file_path),
      message=f"Failed to read file: {e}",
    ) from None

  frontmatter, body = parse_frontmatter(content)

  # Extract required fields
  name = frontmatter.get("name")
  if not name:
    raise ConfigurationError(
      setting="name",
      message="Required field 'name' is missing or empty",
    )

  description = frontmatter.get("description")
  if not description:
    raise ConfigurationError(
      setting="description",
      message="Required field 'description' is missing or empty",
    )

  tools_raw = frontmatter.get("tools")
  if not tools_raw:
    raise ConfigurationError(
      setting="tools",
      message="Required field 'tools' is missing or empty",
    )

  # Parse tools (comma-separated string or list)
  if isinstance(tools_raw, str):
    tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip())
  elif isinstance(tools_raw, list):
    tools = tuple(str(t).strip() for t in tools_raw if t)
  else:
    raise ConfigurationError(
      setting="tools",
      message=f"Field 'tools' must be a comma-separated string or list, got {type(tools_raw).__name__}",
    )

  if not tools:
    raise ConfigurationError(
      setting="tools",
      message="Field 'tools' must contain at least one tool name",
    )

  # Extract optional color
  color = frontmatter.get("color")
  if color is not None:
    color = str(color)

  return AgentDefinition(
    name=str(name),
    description=str(description),
    tools=tools,
    color=color,
    system_prompt=body.strip(),
    source_path=str(file_path),
  )


def load_agent_definitions(directory: Path | str) -> dict[str, AgentDefinition]:
  """Load all agent definitions from a directory.

  Args:
    directory: Path to the agents directory.

  Returns:
    Dictionary mapping agent names to definitions.

  Raises:
    FileNotFoundError: If the directory doesn't exist.
    ConfigurationError: If any agent definition is invalid.
  """
  dir_path = Path(directory)

  if not dir_path.exists():
    raise FileNotFoundError(str(dir_path), "agents directory")

  if not dir_path.is_dir():
    raise ConfigurationError(
      setting=str(dir_path),
      message="Agents path is not a directory",
    )

  definitions: dict[str, AgentDefinition] = {}

  for md_file in sorted(dir_path.glob("*.md")):
    try:
      definition = load_agent_definition(md_file)
      if definition.name in definitions:
        raise ConfigurationError(
          setting=f"agent.{definition.name}",
          message=f"Duplicate agent name '{definition.name}' in {md_file}",
        )
      definitions[definition.name] = definition
    except ConfigurationError:
      raise
    except Exception as e:
      raise ConfigurationError(
        setting=str(md_file),
        message=f"Failed to load agent definition: {e}",
      ) from None

  return definitions


__all__ = [
  "parse_frontmatter",
  "load_agent_definition",
  "load_agent_definitions",
]
