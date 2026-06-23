"""Context management for Yoker agent sessions.

Provides pluggable, list-like context managers for conversation history.

Example:
    >>> from yoker.context import (
    ...     BasicContextManager,
    ...     ContextManager,
    ...     PersistenceContextManager,
    ...     list_sessions,
    ...     SessionMetadata,
    ... )
    >>>
    >>> # In-memory context
    >>> cm = BasicContextManager()
    >>> cm.add_message("user", "Hello")
    >>>
    >>> # Persisted context
    >>> pcm = PersistenceContextManager(session_id="my-session")
    >>> pcm.add_message("user", "Hello")
"""

from yoker.context.basic import BasicContextManager, SimpleContextManager
from yoker.context.interface import ContextStatistics, SessionMetadata
from yoker.context.manager import ContextManager
from yoker.context.persistence import DEFAULT_STORAGE_PATH, PersistenceContextManager
from yoker.context.session import list_sessions, load_session_metadata

__all__ = [
  "ContextManager",
  "ContextStatistics",
  "SessionMetadata",
  "BasicContextManager",
  "SimpleContextManager",
  "PersistenceContextManager",
  "DEFAULT_STORAGE_PATH",
  "list_sessions",
  "load_session_metadata",
]
