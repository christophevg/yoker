"""/tools command implementation."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from yoker.commands.base import Command
from yoker.tools import ToolRegistry

if TYPE_CHECKING:
  from yoker.base import AgentCore


def create_tools_command(registry: ToolRegistry, agent_core: "AgentCore") -> Command:
  """Create the /tools command.

  The tools command lists all known tools with availability markers.

  Args:
    registry: The tool registry with currently available (filtered) tools.
    agent_core: AgentCore instance for accessing known tools.

  Returns:
    A Command object for the tools command.
  """
  return Command(
    name="tools",
    description="List all known tools with availability",
    handler=_create_tools_handler(registry, agent_core),
  )


def _create_tools_handler(
  registry: ToolRegistry, agent_core: "AgentCore"
) -> Callable[[list[str]], str]:
  """Create the tools command handler.

  Args:
    registry: The tool registry with currently available tools.
    agent_core: AgentCore instance for accessing known tools.

  Returns:
    Handler function for the tools command.
  """

  def handler(args: list[str]) -> str:
    """List all known tools with availability markers.

    Shows:
      - Built-in tools (always known)
      - Plugin tools (known when plugins loaded)
      - Each marked as available (✓) or not available (✗)

    Args:
      args: Ignored (no arguments needed).

    Returns:
      Formatted text listing all tools with availability.
    """
    lines = ["Known tools:"]
    lines.append("")

    # Get available tool names (from filtered registry)
    available_names = set(registry.names)

    # Get known built-in tools from AgentCore
    known_builtin_tools = agent_core.get_known_tools()

    # Helper to truncate descriptions
    def truncate_description(desc: str, max_len: int = 60) -> str:
      """Truncate description to max_len, adding ellipsis if needed."""
      if len(desc) <= max_len:
        return desc
      return desc[: max_len - 3] + "..."

    # Get allowed tools from agent definition (if any)
    allowed_tools: set[str] = set()
    if agent_core.agent_definition:
      # Agent definition's tools list is already namespaced correctly
      allowed_tools = set(agent_core.agent_definition.tools)

    # Built-in tools section
    lines.append("Built-in:")
    if known_builtin_tools:
      for tool in sorted(known_builtin_tools, key=lambda t: t.name):
        # Check if available: tool is available if:
        # 1. No agent loaded (all tools available), OR
        # 2. Agent allows this tool (check both yoker:name and plain name)
        is_available = (
          "yoker:" + tool.name in available_names
          or tool.name in available_names
          or ("yoker:" + tool.name) in allowed_tools
          or tool.name in allowed_tools
        )
        # If agent is loaded, check if tool is in allowed list
        if agent_core.agent_definition:
          is_available = (
            ("yoker:" + tool.name) in allowed_tools or tool.name in allowed_tools
          ) and (tool.name in available_names or "yoker:" + tool.name in available_names)
        marker = "✓" if is_available else "✗"
        description = truncate_description(tool.description)
        lines.append(f"  {marker} {tool.name:15} - {description}")
    else:
      lines.append("  (none)")
    lines.append("")

    # Plugin tools section (from AgentCore)
    plugin_tools = agent_core.plugin_tools
    if plugin_tools:
      lines.append("Plugins:")
      for tool in sorted(plugin_tools, key=lambda t: t.name):
        # Plugin tools are namespaced as "package:tool_name"
        # Check if available in registry
        is_available = tool.name in available_names
        # If agent is loaded, also check if tool is in allowed list
        if agent_core.agent_definition:
          is_available = tool.name in allowed_tools and tool.name in available_names
        marker = "✓" if is_available else "✗"
        # Get actual tool from registry if available (might have different description)
        actual_tool = registry.get(tool.name)
        description = actual_tool.description if actual_tool else tool.description
        description = truncate_description(description)
        lines.append(f"  {marker} {tool.name:15} - {description}")
      lines.append("")

    # Context information
    if agent_core.agent_definition:
      lines.append(f"Agent: {agent_core.agent_definition.name}")
      lines.append(f"  Allowed tools: {', '.join(sorted(agent_core.agent_definition.tools))}")
    else:
      lines.append("No agent loaded. All enabled tools are available.")

    return "\n".join(lines)

  return handler
