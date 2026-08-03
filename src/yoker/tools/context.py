"""Tool execution context.

Provides tools with their configuration, shared settings, and backends
without exposing the full Agent or Config.

``ToolContext`` carries an optional ``session`` reference so
session-aware tools (e.g. ``send_message``) can reach the
:class:`yoker.session.Session` that owns the calling agent. The ``agent``
tool uses closure capture instead, but ``ToolContext.session`` is the
canonical injection point for future session-aware tools.

``ToolContext`` also carries an optional ``approval_handler`` — an async
callable that tools can use to request interactive approval before
executing operations that need user confirmation (e.g. git commit/push).
The handler is wired from ``UIHandler.confirm_approval`` in interactive
mode. When ``None`` (batch mode), tools that require approval must
fail-safe to denial.

The handler signature is ``(label: str, preview: str, kind: str) ->
bool``. ``kind`` is ``"file"`` for protected-file writes (``label`` is a
file path, ``preview`` is a unified diff) or ``"git"`` for git operations
(``label`` is ``"git <operation>"``, ``preview`` is a command preview).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.config import ToolConfig, ToolsSharedConfig
  from yoker.session import Session

  ApprovalHandler = Callable[[str, str, str], Awaitable[bool]]


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
    approval_handler: Optional async callable
      ``(label: str, preview: str, kind: str) -> bool`` for interactive
      approval. ``None`` in batch mode; tools must fail-safe to denial.
  """

  config: "ToolConfig"  # Tool-specific config (WriteToolConfig, etc.)
  shared: "ToolsSharedConfig"  # content_display, etc.
  backends: dict[str, Any]  # {"websearch": OllamaWebSearchBackend, ...}
  session: "Session | None" = None
  approval_handler: "ApprovalHandler | None" = None


__all__ = ["ToolContext"]
