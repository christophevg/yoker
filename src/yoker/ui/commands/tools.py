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


def _truncate_description(desc: str, max_len: int = 60) -> str:
  """Truncate description to max_len, adding ellipsis if needed."""
  if len(desc) <= max_len:
    return desc
  return desc[: max_len - 3] + "..."


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """List all known tools with availability markers.

  Args:
    args: Ignored (no arguments needed).
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Formatted text listing all tools with availability.
  """
  registry = agent.tool_registry
  available_names = set(registry.names)

  core = agent._core
  known_builtin_tools = core.get_known_tools()
  plugin_tools = core.plugin_tools

  allowed_tools: set[str] = set()
  if core.agent_definition:
    allowed_tools = set(core.agent_definition.tools)

  lines = ["Known tools:", ""]

  lines.append("Built-in:")
  if known_builtin_tools:
    for tool in sorted(known_builtin_tools, key=lambda t: t.name):
      is_available = (
        f"yoker:{tool.name}" in available_names
        or tool.name in available_names
        or f"yoker:{tool.name}" in allowed_tools
        or tool.name in allowed_tools
      )
      if core.agent_definition:
        is_available = (f"yoker:{tool.name}" in allowed_tools or tool.name in allowed_tools) and (
          tool.name in available_names or f"yoker:{tool.name}" in available_names
        )
      marker = "✓" if is_available else "✗"
      description = _truncate_description(tool.description)
      lines.append(f"  {marker} {tool.name:15} - {description}")
  else:
    lines.append("  (none)")
  lines.append("")

  if plugin_tools:
    lines.append("Plugins:")
    for tool in sorted(plugin_tools, key=lambda t: t.name):
      is_available = tool.name in available_names
      if core.agent_definition:
        is_available = tool.name in allowed_tools and tool.name in available_names
      marker = "✓" if is_available else "✗"
      actual_tool = registry.get(tool.name)
      description = actual_tool.description if actual_tool else tool.description
      description = _truncate_description(description)
      lines.append(f"  {marker} {tool.name:15} - {description}")
    lines.append("")

  if core.agent_definition:
    lines.append(f"Agent: {core.agent_definition.name}")
    lines.append(f"  Allowed tools: {', '.join(sorted(core.agent_definition.tools))}")
  else:
    lines.append("No agent loaded. All enabled tools are available.")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /tools command.

  Returns:
    A Command object for /tools.
  """
  from yoker.ui.commands.base import Command

  return Command(name="tools", description=DESCRIPTION, handler=handle)
