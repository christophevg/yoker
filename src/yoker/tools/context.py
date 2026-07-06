"""Tool execution context.

Provides tools with their configuration, shared settings, and backends
without exposing the full Agent or Config.

``ToolContext`` carries an optional ``session`` reference so
session-aware tools (e.g. ``send_message``) can reach the
:class:`yoker.session.Session` that owns the calling agent. The ``agent``
tool uses closure capture instead, but ``ToolContext.session`` is the
canonical injection point for future session-aware tools.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.config import ToolConfig, ToolsSharedConfig
  from yoker.session import Session


@dataclass
class ToolContext:
  """Execution context for tools.

  Injected into tool functions that have a `ctx: ToolContext` parameter.
  Provides tool-specific config, shared settings, and backends.

  Attributes:
    config: Tool-specific config (WriteToolConfig, etc.)
    shared: Shared tool settings (content_display, etc.).
    backends: Provider-specific tool backends
      ({"websearch": OllamaWebSearchBackend, ...}).
    session: The :class:`Session` owning the calling agent, when the agent
      runs inside a session. ``None`` on the single-agent path.
  """

  config: "ToolConfig"  # Tool-specific config (WriteToolConfig, etc.)
  shared: "ToolsSharedConfig"  # content_display, etc.
  backends: dict[str, Any]  # {"websearch": OllamaWebSearchBackend, ...}
  session: "Session | None" = None


__all__ = ["ToolContext"]
