"""Echo tool implementation for demo plugin.

Provides a simple echo tool that returns its input with a prefix. The
prefix comes from the plugin's typed config (``EchoToolConfig``), injected
as ``ctx.config`` when the function declares a ``ctx: ToolContext``
parameter (TODO 7.2 — plugin tool configuration).
"""

from dataclasses import dataclass, field
from typing import Annotated

from yoker.config import ToolConfig
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext


@dataclass
class EchoToolConfig(ToolConfig):
  """Configuration for the demo plugin's echo tool.

  Attributes:
    prefix: Prefix prepended to every echoed message. The default
      preserves the pre-config feature's output exactly.
  """

  prefix: str = "Echo: "


@dataclass
class DemoPluginConfig(ToolConfig):
  """Plugin-root config for the demo plugin (owner shape: nested).

  One field per tool; the TOML user side is
  ``[tools.yoker_plugin_demo.echo]``. The root ``enabled`` flag gates the
  whole plugin's tools, a per-tool ``enabled`` gates that tool.
  """

  echo: EchoToolConfig = field(default_factory=EchoToolConfig)


def echo(
  message: Annotated[str, Text("The message to echo back")],
  ctx: ToolContext,
) -> str:
  """Echo back the input message with the configured prefix.

  Receives the plugin's top-level config (``DemoPluginConfig``) and
  navigates to its own tool config — the harness imposes no hierarchy
  convention (TODO 7.2).
  """
  config = ctx.config if isinstance(ctx.config, DemoPluginConfig) else DemoPluginConfig()
  return f"{config.echo.prefix}{message}"


__all__ = ["DemoPluginConfig", "EchoToolConfig", "echo"]
