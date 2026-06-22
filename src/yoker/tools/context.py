"""Tool execution context.

Provides tools with their configuration, shared settings, and backends
without exposing the full Agent or Config.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.config import ToolConfig, ToolsSharedConfig


@dataclass
class ToolContext:
  """Execution context for tools.

  Injected into tool functions that have a `ctx: ToolContext` parameter.
  Provides tool-specific config, shared settings, and backends.
  """

  config: "ToolConfig"  # Tool-specific config (WriteToolConfig, etc.)
  shared: "ToolsSharedConfig"  # content_display, etc.
  backends: dict[str, Any]  # {"websearch": OllamaWebSearchBackend, ...}


__all__ = ["ToolContext"]