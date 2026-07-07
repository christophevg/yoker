"""Context manager factory — agent-scoped construction driven by Config.

Hides ContextManager construction from Session. Each agent gets its own
instance; persisted agents get a per-agent JSONL file via a configurable
filename pattern.
"""

from pathlib import Path

from yoker.config import Config
from yoker.context.basic import SimpleContextManager
from yoker.context.persisted import Persisted
from yoker.context.protocol import ContextManager


def create_context_manager(config: Config, agent_id: str) -> ContextManager:
  """Construct an agent-scoped ContextManager from ``config.context``.

  When ``persist_after_turn`` is set, a :class:`Persisted` wrapper is built
  with a per-agent filename derived from ``config.context.filename``
  interpolated with ``session_id`` and ``agent_id``. When ``fresh`` is set
  any existing persisted state for that filename is deleted first. When
  persistence is disabled a bare :class:`SimpleContextManager` is returned.

  No agent wiring or registration — callers set ``.agent`` after assignment.
  """
  ctx = config.context
  # option 1: in-memory only
  if not ctx.persist_after_turn:
    return SimpleContextManager()

  # option 2: per-agent JSONL file
  # Sanitize agent_id: namespaced ids (e.g. "file:researcher") contain colons
  # that validate_session_id rejects. Replace with a safe separator.
  safe_agent_id = agent_id.replace(":", "-")
  # standalone agent: no session_id
  filename = (
    safe_agent_id
    if ctx.session_id is None
    else ctx.filename.format(session_id=ctx.session_id, agent_id=safe_agent_id)
  )
  storage_path = Path(ctx.storage_path).expanduser()
  persisted = Persisted(SimpleContextManager(), storage_path=storage_path, session_id=filename)
  if ctx.fresh:
    persisted.delete()
  return persisted


__all__ = ["create_context_manager"]
