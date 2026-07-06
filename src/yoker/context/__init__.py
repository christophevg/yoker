"""Context management for Yoker agent sessions.

Provides the ContextManager Protocol and concrete implementations:

* BaseContextManager — in-memory base with system prompt.
* SimpleContextManager — adds environment reminder + system prompt.
* ContextManagerWrapper — pure proxy for wrapping other context managers.
* Persisted — JSONL persistence wrapper (wrap a SimpleContextManager or
  BaseContextManager to add persistence).

Example:
    >>> from yoker.context import (
    ...     BaseContextManager,
    ...     SimpleContextManager,
    ...     Persisted,
    ...     list_sessions,
    ... )
    >>>
    >>> # In-memory context with env reminder
    >>> cm = SimpleContextManager()
    >>> cm.add_message("user", "Hello")
    >>>
    >>> # Persisted context (with env reminder)
    >>> pcm = Persisted(SimpleContextManager(), session_id="my-session")
    >>> pcm.add_message("user", "Hello")
"""

from yoker.context.basic import SimpleContextManager
from yoker.context.interface import ContextStatistics, SessionMetadata
from yoker.context.manager import BaseContextManager
from yoker.context.persisted import DEFAULT_STORAGE_PATH, Persisted
from yoker.context.protocol import ContextManager
from yoker.context.session import list_sessions, load_session_metadata
from yoker.context.wrapper import ContextManagerWrapper

__all__ = [
  "ContextManager",
  "BaseContextManager",
  "SimpleContextManager",
  "ContextManagerWrapper",
  "Persisted",
  "ContextStatistics",
  "SessionMetadata",
  "DEFAULT_STORAGE_PATH",
  "list_sessions",
  "load_session_metadata",
]
