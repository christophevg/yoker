"""/tools command implementation in the UI layer.

Lists all known tools with availability markers. The command queries the
agent's tool registry and core state, then outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "List all known tools with availability"


def _truncate(desc: str, max_len: int = 60) -> str:
  """Truncate description to max_len, adding ellipsis if needed."""
  return (desc[: max_len - 3] + "...") if len(desc) > max_len else desc


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """List all known tools with availability markers."""

  def _has(agent, tool):
    if agent.definition:
      return tool.name in agent.definition.tools
    return False

  lines = ["Known tools:", ""]

  lines.append("Built-in:")
  for tool in agent.tools.find_tools(namespace="yoker"):
    marker = "✓" if _has(agent, tool) else "✗"
    lines.append(f"  {marker} {tool.name:15} - {_truncate(tool.description)}")

  lines.append("")

  lines.append("Plugins:")

  for namespace in agent.tools.namespaces:
    if namespace == "yoker":
      continue
    for tool in agent.tools.find_tools(namespace=namespace):
      marker = "✓" if _has(agent, tool) else "✗"
      lines.append(f"  {marker} {tool.name:15} - {_truncate(tool.description)}")
    lines.append("")

  if agent.definition:
    lines.append(f"Agent: {agent.definition.name}")
    lines.append(f"  Allowed tools: {', '.join(sorted(agent.definition.tools))}")
  else:
    lines.append("No agent loaded. All enabled tools are available.")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /tools command."""
  from yoker.ui.commands.base import Command

  return Command(name="tools", description=DESCRIPTION, handler=handle)
