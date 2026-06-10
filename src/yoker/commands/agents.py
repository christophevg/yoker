"""/agents command implementation."""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from yoker.agents import load_agent_definition
from yoker.commands.base import Command

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.config import Config


def create_agents_command(
  get_agent_definition: Callable[[], "AgentDefinition | None"],
  config: "Config",
  get_plugin_agents: Callable[[], list["AgentDefinition"]] | None = None,
) -> Command:
  """Create the /agents command.

  The agents command shows the currently loaded agent and known agents.

  Args:
    get_agent_definition: Function that returns the current agent definition.
    config: Configuration object for accessing agents directory.
    get_plugin_agents: Optional function that returns plugin agents.

  Returns:
    A Command object for the agents command.
  """
  return Command(
    name="agents",
    description="Show loaded agent and known agents",
    handler=_create_agents_handler(get_agent_definition, config, get_plugin_agents),
  )


def _create_agents_handler(
  get_agent_definition: Callable[[], "AgentDefinition | None"],
  config: "Config",
  get_plugin_agents: Callable[[], list["AgentDefinition"]] | None = None,
) -> Callable[[list[str]], str]:
  """Create the agents command handler.

  Args:
    get_agent_definition: Function that returns the current agent definition.
    config: Configuration object for accessing agents directory.
    get_plugin_agents: Optional function that returns plugin agents.

  Returns:
    Handler function for the agents command.
  """

  def handler(args: list[str]) -> str:
    """Show currently loaded agent and known agents from directory.

    Args:
      args: Ignored (no arguments needed).

    Returns:
      Formatted text showing current agent and known agents.
    """
    agent_def = get_agent_definition()
    lines = []

    # Current agent section
    lines.append("Current agent:")
    lines.append("")

    if agent_def is None:
      lines.append("  (default) - No agent definition loaded")
      lines.append("  All enabled tools are available.")
    else:
      marker = "✓"
      lines.append(f"  {marker} {agent_def.name}")
      if agent_def.source_path:
        lines.append(f"      Source: {agent_def.source_path}")
      lines.append(f"      Description: {agent_def.description}")
      if agent_def.model:
        lines.append(f"      Model: {agent_def.model}")
      if agent_def.tools:
        lines.append(f"      Tools: {', '.join(sorted(agent_def.tools))}")

    lines.append("")

    # Known agents section
    lines.append("Known agents:")
    lines.append("")

    # Scan agents directory for agent definitions
    known_agents = _scan_agents_directory(config)

    # Get plugin agents
    plugin_agents = get_plugin_agents() if get_plugin_agents else []

    if not known_agents and not plugin_agents and not agent_def:
      lines.append("  No agents configured.")
      lines.append("")
      lines.append("Use --agents-definition <path> to load a specific agent.")
    else:
      # Show directory agents
      if known_agents:
        for agent_name, source_path, description in known_agents:
          # Mark if this is the loaded agent
          is_loaded = agent_def is not None and agent_def.name == agent_name
          marker = "✓" if is_loaded else "✗"
          lines.append(f"  {marker} {agent_name}")
          lines.append(f"      Source: {source_path}")
          lines.append(f"      Description: {description}")
          lines.append("")

      # Show plugin agents
      if plugin_agents:
        if known_agents:
          lines.append("")  # Add spacing between sections
        for plugin_agent in plugin_agents:
          # Mark if this is the loaded agent
          is_loaded = agent_def is not None and agent_def.name == plugin_agent.name
          marker = "✓" if is_loaded else "✗"
          lines.append(f"  {marker} {plugin_agent.name}")
          if plugin_agent.source_path:
            lines.append(f"      Source: {plugin_agent.source_path}")
          lines.append(f"      Description: {plugin_agent.description}")
          if plugin_agent.model:
            lines.append(f"      Model: {plugin_agent.model}")
          if plugin_agent.tools:
            lines.append(f"      Tools: {', '.join(sorted(plugin_agent.tools))}")
          lines.append("")

    if agent_def is None:
      lines.append("")
      lines.append("Use --agents-definition <path> to load an agent.")

    return "\n".join(lines)

  return handler


def _scan_agents_directory(config: "Config") -> list[tuple[str, str, str]]:
  """Scan agents directory for agent definitions.

  Args:
    config: Configuration object.

  Returns:
    List of tuples (agent_name, source_path, description).
  """
  agents: list[tuple[str, str, str]] = []

  # Check if agents directory is configured
  if not config.agents.directory:
    return agents

  agents_dir = Path(config.agents.directory).expanduser()

  # Check if directory exists
  if not agents_dir.exists():
    return agents

  # Scan for .md files with frontmatter
  try:
    for md_file in sorted(agents_dir.glob("*.md")):
      try:
        agent_def = load_agent_definition(md_file)
        agents.append(
          (
            agent_def.name,
            str(md_file),
            agent_def.description,
          )
        )
      except Exception:
        # Skip files that fail to parse
        continue
  except Exception:
    # Directory scanning failed
    pass

  return agents
