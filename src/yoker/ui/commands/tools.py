"""/tools command implementation in the UI layer.

Lists all known tools with availability markers. The command queries the
agent's tool registry and core state, then outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.tools.schema import ToolSpec
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "List all known tools with availability"


def _truncate(desc: str, max_len: int = 60) -> str:
  """Truncate description to max_len, adding ellipsis if needed."""
  return (desc[: max_len - 3] + "...") if len(desc) > max_len else desc


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """List all known tools with availability markers."""

  def _has(ag: "Agent", tl: "ToolSpec") -> bool:
    """Check if a tool is in the agent's allowed tools list.

    Built-in tools may omit the ``yoker:`` prefix and are matched
    case-insensitively. Plugin tools must be referenced with their full
    namespaced name. After the Agent resolves ``ALL_TOOLS`` to the full
    list of tool names, every tool in the registry is available.
    """
    if not ag.definition:
      return False

    # tools is a plain list after Agent._filter_tools_by_definition ran.
    # When it's empty (ALL_TOOLS sentinel before resolution, or explicit []),
    # no tool matches here — but for a constructed agent the sentinel has
    # already been resolved to the full list of tool names.
    tool_name_lower = tl.name.lower()

    for requested in ag.definition.tools or []:
      requested_lower = requested.lower()

      # Direct match (case-insensitive)
      if requested_lower == tool_name_lower:
        return True

      # For built-in tools, also check without yoker: prefix
      if ":" in tool_name_lower:
        # Tool has namespace, check if requested matches without namespace
        tool_namespace, tool_simple = tool_name_lower.split(":", 1)
        if tool_namespace == "yoker":
          # Built-in tool: check if requested is just the simple name
          if requested_lower == tool_simple:
            return True
          # Or if requested also has yoker: prefix
          if requested_lower == tool_name_lower:
            return True

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
    if agent.definition.tools:
      lines.append(f"  Allowed tools: {', '.join(sorted(agent.definition.tools))}")
    else:
      lines.append("  Allowed tools: (none)")
  else:
    lines.append("No agent loaded. All enabled tools are available.")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /tools command."""
  from yoker.ui.commands.base import Command

  return Command(name="tools", description=DESCRIPTION, handler=handle)
