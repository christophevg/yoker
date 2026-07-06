"""/agents command implementation in the UI layer.

Shows the currently loaded agent and known agents. The command queries the
agent's state and config, then outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

from yoker.ui.commands.base import Command

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.ui import UIHandler


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """Show currently loaded agent and known agents.

  Args:
    args: Ignored (no arguments needed).
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Formatted text showing current agent and known agents.
  """
  lines: list[str] = []

  lines.append("Current agent:")
  lines.append("")

  if agent.definition.simple_name is None:
    lines.append("  (default) - No agent definition loaded")
    lines.append("  All enabled tools are available.")
  else:
    lines.append(f"  ✓ {agent.definition.name}")
    if agent.definition.source_path:
      lines.append(f"      Source: {agent.definition.source_path}")
    lines.append(f"      Description: {agent.definition.description}")
    if agent.definition.model:
      lines.append(f"      Model: {agent.definition.model}")
    if agent.definition.tools:
      lines.append(f"      Tools: {', '.join(sorted(agent.definition.tools))}")

  lines.append("")
  lines.append("Known agents:")
  lines.append("")

  # Agent registry is owned by the Session. The command layer
  # still receives the agent; reach the session's registry through it. When
  # no session is set (single-agent standalone use), show "no agents".
  session = getattr(agent, "_session", None)
  registry = getattr(session, "agents", None)
  known_agents = registry.agents if registry is not None else []

  if not known_agents:
    lines.append("  No agents configured.")
  else:
    for agent_definition in known_agents:
      marker = "✓" if agent.definition.name == agent_definition.name else "✗"
      lines.append(f"  {marker} {agent_definition.name}")
      lines.append(f"      Source: {agent_definition.source_path}")
      lines.append(f"      Description: {agent_definition.description}")
      lines.append("")
      if agent_definition.model:
        lines.append(f"      Model: {agent_definition.model}")
      if agent_definition.tools:
        lines.append(f"      Tools: {', '.join(sorted(agent_definition.tools))}")
      lines.append("")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /agents command.

  Returns:
    A Command object for /agents.
  """
  return Command(name="agents", description="Show loaded agent and known agents", handler=handle)
