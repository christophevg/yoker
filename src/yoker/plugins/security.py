"""Plugin security system for Yoker.

Implements a two-level security model:
  1. Global opt-in: [plugins] enabled = true/false (default: false)
  2. Per-plugin trust: [plugins.trusted] table for trusted plugins

This ensures plugins can only be loaded when explicitly enabled
and trusted by the user.
"""

import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from structlog import get_logger

if TYPE_CHECKING:
  from yoker.config import Config
  from yoker.plugins import PluginComponents

logger = get_logger(__name__)

# Rich console for styled output
console = Console()

# Track plugins confirmed during this session (don't ask twice for same plugin)
_session_trusted: set[str] = set()


def is_trusted(plugin_name: str, config: "Config") -> bool:
  """Check if plugin is in trusted list.

  Args:
    plugin_name: Name of the plugin package.
    config: Configuration object.

  Returns:
    True if plugin is trusted, False otherwise.
  """
  # Check if plugin is in session-trusted set (confirmed during this session)
  if plugin_name in _session_trusted:
    return True

  # Check if plugin is in config's trusted dictionary
  return plugin_name in config.plugins.trusted


def confirm_plugin(plugin_name: str, plugin: "PluginComponents") -> bool:
  """Ask user to confirm loading an untrusted plugin.

  Shows plugin capabilities (tools, skills, agents) and warns about
  security implications. In non-interactive mode, returns False.

  Args:
    plugin_name: Name of the plugin package.
    plugin: Plugin components to show capabilities.

  Returns:
    True if user confirms, False otherwise.
  """
  # Check if running in non-interactive mode
  if not sys.stdin.isatty():
    # Styled error message
    error_text = Text()
    error_text.append("Error: ", style="bold red")
    error_text.append(f"Plugin '{plugin_name}' is not trusted.\n")
    error_text.append("Add to your yoker.toml:\n")
    console.print(error_text)

    # Styled code snippet
    code_text = Text()
    code_text.append("  [plugins.trusted]\n", style="cyan")
    code_text.append(f"  {plugin_name} = true", style="cyan")
    console.print(code_text)

    logger.warning(
      "plugin_not_trusted_non_interactive",
      plugin=plugin_name,
      interactive=False,
    )
    return False

  # Build styled panel content
  # Tools section (tools are now ToolSpec objects, so .name is directly accessible)
  if plugin.tools:
    tools_str = ", ".join(t.name for t in plugin.tools[:5])
    if len(plugin.tools) > 5:
      tools_str += f", +{len(plugin.tools) - 5} more"
  else:
    tools_str = "(none)"

  # Skills section
  if plugin.skills:
    skills_str = ", ".join(s.name for s in plugin.skills[:5])
    if len(plugin.skills) > 5:
      skills_str += f", +{len(plugin.skills) - 5} more"
  else:
    skills_str = "(none)"

  # Agents section
  if plugin.agents:
    agents_str = ", ".join(a.name for a in plugin.agents[:5])
    if len(plugin.agents) > 5:
      agents_str += f", +{len(plugin.agents) - 5} more"
  else:
    agents_str = "(none)"

  # Create styled content
  content = Text()
  content.append("Plugin: ", style="bold")
  content.append(f"{plugin_name}\n\n")
  content.append("Tools:     ", style="cyan")
  content.append(f"{tools_str}\n")
  content.append("Skills:    ", style="cyan")
  content.append(f"{skills_str}\n")
  content.append("Agents:    ", style="cyan")
  content.append(f"{agents_str}\n\n")
  content.append("Plugins can execute code on your system.\n", style="yellow")
  content.append("Only load plugins you trust.\n\n", style="yellow")
  content.append("Load this plugin? [y/N]: ", style="bold")

  # Create and display panel
  panel = Panel(
    content,
    title=f"Plugin: {plugin_name}",
    border_style="blue",
    padding=(0, 1),
  )
  console.print()
  console.print(panel)
  console.print()

  # Get user input
  try:
    response = input().strip().lower()
    if response in ("y", "yes"):
      # Add to session-trusted set
      _session_trusted.add(plugin_name)
      logger.info("plugin_confirmed_by_user", plugin=plugin_name)

      # Show config snippet for permanent trust
      console.print("\nTo trust this plugin permanently, add to your yoker.toml:\n")
      snippet = Text()
      snippet.append("  [plugins.trusted]\n", style="cyan")
      snippet.append(f"  {plugin_name} = true", style="cyan")
      console.print(snippet)
      console.print()

      return True
    else:
      logger.info("plugin_rejected_by_user", plugin=plugin_name)
      return False
  except (EOFError, KeyboardInterrupt):
    print()
    logger.info("plugin_confirmation_cancelled", plugin=plugin_name)
    return False


def check_plugins_enabled(config: "Config") -> bool:
  """Check if plugins are enabled globally.

  Args:
    config: Configuration object.

  Returns:
    True if plugins are enabled, False otherwise.

  Side effects:
    Prints styled error message if plugins are disabled.
  """
  if not config.plugins.enabled:
    # Styled error message
    error_text = Text()
    error_text.append("Error: ", style="bold red")
    error_text.append("Plugins are disabled. To enable, add to your config:\n")
    console.print(error_text)

    # Styled code snippet
    code_text = Text()
    code_text.append("  [plugins]\n", style="cyan")
    code_text.append("  enabled = true", style="cyan")
    console.print(code_text)

    logger.warning("plugins_disabled_globally")
    return False

  return True


def check_plugin_allowed(plugin_name: str, config: "Config", plugin: "PluginComponents") -> bool:
  """Check if a plugin is allowed to load.

  Performs two-level security check:
    1. Global opt-in (config.plugins.enabled)
    2. Per-plugin trust (config.plugins.trusted or session confirmation)

  Args:
    plugin_name: Name of the plugin package.
    config: Configuration object.
    plugin: Plugin components (for confirmation dialog).

  Returns:
    True if plugin is allowed to load, False otherwise.

  Note:
    This function should be called after global plugins.enabled check.
  """
  # Check if plugin is trusted
  if is_trusted(plugin_name, config):
    logger.info("plugin_trusted", plugin=plugin_name)
    return True

  # Ask for confirmation
  if confirm_plugin(plugin_name, plugin):
    return True

  return False


def reset_session_trusted() -> None:
  """Reset the session-trusted set (for testing)."""
  _session_trusted.clear()


__all__ = [
  "is_trusted",
  "confirm_plugin",
  "check_plugins_enabled",
  "check_plugin_allowed",
  "reset_session_trusted",
]
