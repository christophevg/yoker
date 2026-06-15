"""/agents command implementation in the UI layer.

Shows the currently loaded agent and known agents. The command queries the
agent's state and config, then outputs via the UIHandler.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "Show loaded agent and known agents"


def _scan_agents_directory(agents_dir: Path | None) -> list[tuple[str, str, str]]:
  """Scan an agents directory for agent definitions.

  Args:
    agents_dir: Directory to scan, or None.

  Returns:
    List of tuples (agent_name, source_path, description).
  """
  from yoker.agents import load_agent_definition

  agents: list[tuple[str, str, str]] = []

  if agents_dir is None or not agents_dir.exists():
    return agents

  try:
    for md_file in sorted(agents_dir.glob("*.md")):
      try:
        agent_def = load_agent_definition(md_file)
        agents.append((agent_def.name, str(md_file), agent_def.description))
      except Exception:
        continue
  except Exception:
    pass

  return agents


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """Show currently loaded agent and known agents.

  Args:
    args: Ignored (no arguments needed).
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Formatted text showing current agent and known agents.
  """
  agent_def = agent.agent_definition
  lines: list[str] = []

  lines.append("Current agent:")
  lines.append("")

  if agent_def is None:
    lines.append("  (default) - No agent definition loaded")
    lines.append("  All enabled tools are available.")
  else:
    lines.append(f"  ✓ {agent_def.name}")
    if agent_def.source_path:
      lines.append(f"      Source: {agent_def.source_path}")
    lines.append(f"      Description: {agent_def.description}")
    if agent_def.model:
      lines.append(f"      Model: {agent_def.model}")
    if agent_def.tools:
      lines.append(f"      Tools: {', '.join(sorted(agent_def.tools))}")

  lines.append("")
  lines.append("Known agents:")
  lines.append("")

  config = agent.config
  agents_dir = None
  if config.agents.directory:
    agents_dir = Path(config.agents.directory).expanduser()

  known_agents = _scan_agents_directory(agents_dir)
  plugin_agents = agent._core.plugin_agents

  if not known_agents and not plugin_agents and agent_def is None:
    lines.append("  No agents configured.")
    lines.append("")
    lines.append("Use --agents-definition <path> to load a specific agent.")
  else:
    if known_agents:
      for agent_name, source_path, description in known_agents:
        is_loaded = agent_def is not None and agent_def.name == agent_name
        marker = "✓" if is_loaded else "✗"
        lines.append(f"  {marker} {agent_name}")
        lines.append(f"      Source: {source_path}")
        lines.append(f"      Description: {description}")
        lines.append("")

    if plugin_agents:
      if known_agents:
        lines.append("")
      for plugin_agent in plugin_agents:
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


def create_command() -> "Command":
  """Create the /agents command.

  Returns:
    A Command object for /agents.
  """
  from yoker.ui.commands.base import Command

  return Command(name="agents", description=DESCRIPTION, handler=handle)
