"""Agent definition loader for Yoker.

Parses Markdown files with YAML frontmatter into AgentDefinition objects, and
loads them from filesystem directories or package resource directories (via
:mod:`yoker.resources` for location and reading).

Agent *reference resolution by name* is handled by the spawning agent's
:class:`~yoker.agents.AgentRegistry` (populated from configured directories
and loaded plugins), not by this loader.
"""

from pathlib import Path
from typing import Any

from structlog import get_logger

from yoker.agents.schema import AgentDefinition
from yoker.exceptions import ConfigurationError, FileNotFoundError
from yoker.resources import (
  is_dir,
  iter_files,
  parse_yaml_frontmatter,
)

logger = get_logger(__name__)

# Namespace applied to a directly-referenced agent definition file (the only
# single-file load case). Distinct from folder/module namespaces so a one-off
# file reference never collides with a collection's namespace.
FILE_NAMESPACE = "file"

# Backward-compatible alias
parse_frontmatter = parse_yaml_frontmatter


def _apply_namespace(name: str, namespace: str | None) -> str:
  """Apply namespace prefix to an agent name."""
  if not namespace:
    return name
  return f"{namespace}:{name}"


def _namespace_tools(tools: list[object], namespace: str | None) -> list[str]:
  """Namespace tool names for a plugin agent definition."""
  if not namespace:
    return [str(t) for t in tools]
  short_name = namespace.split(".")[-1]
  result: list[str] = []
  for tool in tools:
    tool_str = str(tool)
    if tool_str.startswith("yoker:"):
      result.append(tool_str)
    elif ":" in tool_str:
      tool_namespace, tool_name = tool_str.split(":", 1)
      if tool_namespace == short_name:
        result.append(f"{namespace}:{tool_name}")
      else:
        result.append(tool_str)
    else:
      result.append(f"{namespace}:{tool_str}")
  return result


def parse_agent_definition(
  frontmatter: dict[str, object],
  body: str,
  source_path: str,
  namespace: str,
  strict: bool = True,
) -> AgentDefinition | None:
  """Build an AgentDefinition from parsed frontmatter and body.

  Args:
    frontmatter: Parsed YAML frontmatter dictionary.
    body: Markdown body content.
    source_path: Source path to record on the definition.
    namespace: Optional namespace prefix for namespaced plugin agents.
    strict: If True, raise ConfigurationError for missing required fields;
      if False, return None instead.

  Returns:
    AgentDefinition, or None in non-strict mode when required fields are missing.

  Raises:
    ConfigurationError: In strict mode when required fields are missing or invalid.
  """
  # Extract required name
  name = frontmatter.get("name")
  if not name:
    if strict:
      raise ConfigurationError(
        setting="name",
        message="Required field 'name' is missing or empty",
      )
    return None

  # Extract description
  description = frontmatter.get("description")
  if strict:
    if not description:
      raise ConfigurationError(
        setting="description",
        message="Required field 'description' is missing or empty",
      )
  elif not description:
    description = ""

  # Extract tools
  tools_raw = frontmatter.get("tools")
  if strict:
    if not tools_raw:
      raise ConfigurationError(
        setting="tools",
        message="Required field 'tools' is missing or empty",
      )
  else:
    if not tools_raw:
      tools_raw = []

  if isinstance(tools_raw, str):
    tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip())
  elif isinstance(tools_raw, list):
    tools = tuple(str(t).strip() for t in tools_raw if t)
  else:
    if strict:
      raise ConfigurationError(
        setting="tools",
        message=f"Field 'tools' must be a comma-separated string or list, got {type(tools_raw).__name__}",
      )
    tools = ()

  if strict and not tools:
    raise ConfigurationError(
      setting="tools",
      message="Field 'tools' must contain at least one tool name",
    )

  # Namespace tools for plugin agent definitions (e.g. 'write' -> 'pkg:write',
  # 'demo:echo' -> 'full.package:echo'); 'yoker:' tools are preserved.
  tools = tuple(_namespace_tools(tools, namespace))

  # Extract optional color
  color = frontmatter.get("color")
  if color is not None:
    color = str(color)

  # Extract optional model
  model = frontmatter.get("model")
  if model is not None:
    model = str(model)

  return AgentDefinition(
    simple_name=str(name),
    namespace=namespace,
    description=str(description),
    tools=tools,
    color=color,
    model=model,
    system_prompt=body.strip(),
    source_path=source_path,
  )


def load_agent_definition(path: Path | str, namespace: str | None = None) -> AgentDefinition:
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

  frontmatter, body = parse_yaml_frontmatter(content)
  agent_def = parse_agent_definition(
    frontmatter,
    body,
    source_path=str(file_path),
    namespace=namespace if namespace is not None else FILE_NAMESPACE,
    strict=True,
  )
  assert agent_def is not None
  return agent_def


def load_agent_definitions(directory: Any, namespace: str | None = None) -> dict[str, AgentDefinition]:
  """Load all agent definitions from a directory.

  Works for both filesystem paths (``pathlib.Path``) and package resource
  directories (``importlib.resources`` ``Traversable``, which lacks ``glob``).
  ``load_agent_definitions`` is the collection loader; the single-file loader is
  :func:`load_agent_definition`.

  Args:
    directory: A ``Path``/string filesystem directory, or a ``Traversable``.
    namespace: Optional namespace prefix for all agents in this directory.
      Defaults to the folder/resource name (callers pass an explicit namespace
      to override, e.g. plugins pass the package name).

  Returns:
    Dictionary mapping agent names (``namespace:simple_name``) to definitions.

  Raises:
    FileNotFoundError: If a filesystem directory doesn't exist.
    ConfigurationError: If the path is not a directory or any definition is
      invalid (including duplicate names).
  """
  if isinstance(directory, str):
    directory = Path(directory)
  if isinstance(directory, Path):
    dir_path = directory
    if "~" in str(dir_path):
      dir_path = dir_path.expanduser()
    if not dir_path.exists():
      raise FileNotFoundError(str(dir_path), "agents directory")
    if not dir_path.is_dir():
      raise ConfigurationError(
        setting=str(dir_path),
        message="Agents path is not a directory",
      )
  else:
    dir_path = directory
    if not is_dir(dir_path):
      raise ConfigurationError(
        setting=str(dir_path),
        message="Agents path is not a directory",
      )

  # Default the namespace to the folder/resource name so agents loaded from
  # different locations stay disjoint (matching how module loads use the module
  # name). Callers pass an explicit namespace to override (plugins pass the
  # package).
  if namespace is None:
    namespace = dir_path.name

  definitions: dict[str, AgentDefinition] = {}

  for md_file in iter_files(dir_path, suffix=".md"):
    try:
      content = md_file.read_text(encoding="utf-8")
      frontmatter, body = parse_yaml_frontmatter(content)
      definition = parse_agent_definition(
        frontmatter,
        body,
        source_path=str(md_file),
        namespace=namespace,
        strict=True,
      )
      assert definition is not None
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
  "parse_agent_definition",
  "load_agent_definition",
  "load_agent_definitions",
]
