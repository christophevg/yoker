"""Tool execution context.

Provides tools with their configuration, shared settings, and backends
without exposing the full Agent or Config.

``ToolContext`` carries an optional ``session`` reference so
session-aware tools (e.g. ``send_message``) can reach the
:class:`yoker.session.Session` that owns the calling agent. The ``agent``
tool uses closure capture instead, but ``ToolContext.session`` is the
canonical injection point for future session-aware tools.

``ToolContext`` also carries the calling agent's identity as
:class:`AgentInfo` (``ctx.agent.id`` / ``ctx.agent.definition``),
populated by the tool executor from the live Agent. ``id`` is the
session-assigned runtime id — the same LLM-facing string reference used
by ``send_message`` — and falls back to the definition name for
standalone agents (no Session), so tools always see a usable identifier.

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

``ToolContext`` also carries compiled ``blocked_paths`` glob patterns so
that traversal tools (``search``, ``list``) can internally enforce the
universal denylist on every file they touch — preventing bypass via
``search`` reading content of files that would be blocked by the
guardrail.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.config import ToolConfig, ToolsSharedConfig
  from yoker.session import Session

  ApprovalHandler = Callable[[str, str, str], Awaitable[bool]]


@dataclass(frozen=True)
class AgentInfo:
  """Identity of the agent that is executing a tool.

  Attributes:
    id: The agent's session-assigned runtime id — the same LLM-facing
      string reference used by ``send_message`` and the ``stats`` tool
      scopes. Standalone agents (no Session) fall back to their
      definition name.
    definition: The calling agent's definition name (``yoker:primary``,
      ``c3:researcher``, ...). Always set by the executor.
  """

  id: str
  definition: str


@dataclass
class ToolContext:
  """Execution context for tools.

  Injected into tool functions that have a `ctx: ToolContext` parameter.
  Provides tool-specific config, shared settings, and backends.

  Attributes:
    config: Tool-specific config (WriteToolConfig, etc.). For plugin tools
      this resolves to the plugin's typed config field from the augmented
      ToolsConfig (``config.tools.<plugin-package>.<tool>``, TODO 7.2);
      built-ins keep the flat ``config.tools.<name>`` lookup.
    shared: Shared tool settings (content_display, etc.).
    backends: Provider-specific tool backends
      ({"websearch": OllamaWebSearchBackend, ...}).
    session: The :class:`Session` owning the calling agent, when the agent
      runs inside a session. ``None`` on the single-agent path.
    agent: Identity of the calling agent (:class:`AgentInfo`), populated
      by the executor from the live Agent. The empty placeholder
      ``AgentInfo(id="", definition="")`` applies when a ToolContext is
      constructed directly (tests, defaults) — bypassing the executor.
    approval_handler: Optional async callable
      ``(label: str, preview: str, kind: str) -> bool`` for interactive
      approval. ``None`` in batch mode; tools must fail-safe to denial.
    blocked_path_patterns: Compiled glob patterns for ``blocked_paths``
      enforcement during file traversal (used by search/list). Empty list
      when no blocked_paths are configured.
  """

  config: "ToolConfig"  # Tool-specific config (WriteToolConfig, etc.)
  shared: "ToolsSharedConfig"  # content_display, etc.
  backends: dict[str, Any]  # {"websearch": OllamaWebSearchBackend, ...}
  session: "Session | None" = None
  agent: AgentInfo = field(default_factory=lambda: AgentInfo(id="", definition=""))
  approval_handler: "ApprovalHandler | None" = None
  blocked_path_patterns: list[Any] = field(default_factory=list)


__all__ = ["AgentInfo", "ToolContext"]
