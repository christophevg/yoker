"""Plugin security system for Yoker.

Implements a two-level security model:
  1. Global opt-in: [plugins] enabled = true/false (default: false)
  2. Per-plugin trust: [plugins.trusted] table for trusted plugins

This ensures plugins can only be loaded when explicitly enabled
and trusted by the user.
"""

import os
import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from structlog import get_logger

if TYPE_CHECKING:
  from yoker.cli.sources import ResolvedSource
  from yoker.config import Config
  from yoker.plugins import PluginComponents

logger = get_logger(__name__)

# Rich console for styled output
console = Console()

# Track plugins confirmed during this session (don't ask twice for same plugin)
_session_trusted: set[str] = set()

# Env var override for non-interactive source trust (mirrors YOKER_ALLOW_CUSTOM_BASE_URL).
ENV_TRUST_SOURCE = "YOKER_TRUST_SOURCE"


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


def check_plugin_allowed(plugin: "PluginComponents", config: "Config") -> bool:
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
  if is_trusted(plugin.source, config):
    logger.info("plugin_trusted", plugin=plugin.source)
    return True

  # Ask for confirmation
  if confirm_plugin(plugin.source, plugin):
    return True

  return False


def check_source_allowed(
  trust_key: str,
  config: "Config",
  resolved: "ResolvedSource | None" = None,
) -> bool:
  """Trust gate for ``yoker run <source>`` (C1, M3 security remediation).

  Mirrors :func:`check_plugin_allowed` but operates on a resolved source's
  ``trust_key`` (stable identifier like ``"github:owner/repo@sha"``,
  ``"folder:/abs/path"``, ``"zip:<sha256>"``, ``"module:pkgname"``) BEFORE
  any code is loaded. This is a security invariant:
  :func:`yoker.cli.sources.load_source` MUST NOT be called until this
  returns ``True``.

  Decision cascade:
    1. Pre-trusted via ``[plugins.trusted]`` table or session confirmation.
    2. ``YOKER_TRUST_SOURCE=1`` env var (non-interactive override).
    3. Interactive confirmation dialog (TTY only).
    4. Non-interactive and untrusted -> reject.

  Args:
    trust_key: Stable source identifier from :attr:`ResolvedSource.trust_key`.
    config: The user's config (NOT manifest-overridden — the source's
      manifest must not influence its own trust decision).
    resolved: Optional :class:`ResolvedSource` for the confirmation dialog
      (source type, origin, manifest details). When ``None``, a minimal
      dialog is shown.

  Returns:
    True if the source is allowed to load, False otherwise.
  """
  # 1. Pre-trusted via config or session confirmation.
  if trust_key in config.plugins.trusted or trust_key in _session_trusted:
    logger.info("source_trusted", trust_key=trust_key)
    return True

  # 2. Env-var override (non-interactive opt-in).
  if os.environ.get(ENV_TRUST_SOURCE) == "1":
    _session_trusted.add(trust_key)
    logger.info("source_trusted_via_env", trust_key=trust_key)
    return True

  # 3. Non-interactive -> reject (no auto-trust).
  if not sys.stdin.isatty():
    _print_source_untrusted_noninteractive(trust_key)
    logger.warning("source_not_trusted_non_interactive", trust_key=trust_key)
    return False

  # 4. Interactive confirmation dialog.
  if _confirm_source(trust_key, resolved):
    _session_trusted.add(trust_key)
    return True
  logger.info("source_rejected_by_user", trust_key=trust_key)
  return False


def _print_source_untrusted_noninteractive(trust_key: str) -> None:
  """Print the styled rejection message for non-interactive untrusted sources."""
  error_text = Text()
  error_text.append("Error: ", style="bold red")
  error_text.append(f"Source '{trust_key}' is not trusted.\n")
  error_text.append("Add to your yoker.toml:\n")
  console.print(error_text)

  code_text = Text()
  code_text.append("  [plugins.trusted]\n", style="cyan")
  code_text.append(f"  {trust_key} = true", style="cyan")
  console.print(code_text)

  hint = Text()
  hint.append(
    f"\nOr set {ENV_TRUST_SOURCE}=1 to trust for this session.\n",
    style="yellow",
  )
  console.print(hint)


def _confirm_source(trust_key: str, resolved: "ResolvedSource | None") -> bool:
  """Show an interactive trust confirmation dialog for a resolved source.

  Displays source type, origin, trust key, agent, full prompt, and
  tools_module (per H2 remediation) so the user can make an informed
  decision. Returns True on explicit ``y``/``yes`` confirmation.
  """
  kind = resolved.kind if resolved is not None else "unknown"
  origin = resolved.source_string if resolved is not None else trust_key
  agent = None
  prompt = None
  tools_module = None
  if resolved is not None and resolved.manifest is not None:
    agent = resolved.manifest.run_config.agent
    prompt = resolved.manifest.run_config.prompt
    tools_module = resolved.manifest.plugin_config.tools_module

  content = Text()
  content.append("Source type:  ", style="cyan")
  content.append(f"{kind}\n")
  content.append("Origin:       ", style="cyan")
  content.append(f"{origin}\n")
  content.append("Trust key:    ", style="cyan")
  content.append(f"{trust_key}\n")
  if agent is not None:
    content.append("Agent:        ", style="cyan")
    content.append(f"{agent}\n")
  if tools_module is not None:
    content.append("tools_module: ", style="cyan")
    content.append(f"{tools_module}\n")
  if prompt is not None:
    content.append("\nPrompt:\n", style="cyan")
    content.append(f"{prompt}\n")
  content.append("\nRunning this source executes code on your system.\n", style="yellow")
  content.append("Only run sources you trust.\n\n", style="yellow")
  content.append("Run this source? [y/N]: ", style="bold")

  panel = Panel(
    content,
    title=f"Source: {trust_key}",
    border_style="blue",
    padding=(0, 1),
  )
  console.print()
  console.print(panel)
  console.print()

  try:
    response = input().strip().lower()
    if response in ("y", "yes"):
      console.print("\nTo trust permanently, add to your yoker.toml:\n")
      snippet = Text()
      snippet.append("  [plugins.trusted]\n", style="cyan")
      snippet.append(f"  {trust_key} = true", style="cyan")
      console.print(snippet)
      console.print()
      return True
    return False
  except (EOFError, KeyboardInterrupt):
    print()
    return False


def reset_session_trusted() -> None:
  """Reset the session-trusted set (for testing)."""
  _session_trusted.clear()


def warn_plugins_disabled() -> None:
  """Emit the styled "Plugins are disabled" hint.

  Visible report (Rich) plus a structured log warning. Caller gates the
  invocation on the actual misconfiguration check.
  """
  error_text = Text()
  error_text.append("Error: ", style="bold red")
  error_text.append("Plugins are disabled. To enable, add to your config:\n")
  console.print(error_text)

  code_text = Text()
  code_text.append("  [plugins]\n", style="cyan")
  code_text.append("  enabled = true", style="cyan")
  console.print(code_text)

  logger.warning("plugins_disabled_globally")


__all__ = [
  "is_trusted",
  "confirm_plugin",
  "check_plugin_allowed",
  "check_source_allowed",
  "reset_session_trusted",
  "warn_plugins_disabled",
  "ENV_TRUST_SOURCE",
]
