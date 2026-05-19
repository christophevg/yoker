"""Context management for Yoker agent sessions.

Provides pluggable context persistence with secure session management.

Example:
    >>> from yoker.context import (
    ...     BasicPersistenceContextManager,
    ...     list_sessions,
    ...     SessionMetadata,
    ... )
    >>>
    >>> # List available sessions (uses default path)
    >>> sessions = list_sessions()
    >>> for session in sessions:
    ...     print(f"{session.session_id}: {session.message_count} messages")
    >>>
    >>> # Resume a session
    >>> cm = BasicPersistenceContextManager.resume(sessions[0].session_id)
    >>> print(f"Loaded {cm.get_statistics().message_count} messages")
    >>>
    >>> # Create new session (uses default path)
    >>> cm = BasicPersistenceContextManager()  # auto-generates session_id
"""

from yoker.context.basic import (
  DEFAULT_STORAGE_PATH,
  BasicPersistenceContextManager,
)
from yoker.context.interface import ContextManager, ContextStatistics, SessionMetadata
from yoker.context.session import list_sessions, load_session_metadata

__all__ = [
  "ContextManager",
  "ContextStatistics",
  "SessionMetadata",
  "BasicPersistenceContextManager",
  "DEFAULT_STORAGE_PATH",
  "list_sessions",
  "load_session_metadata",
]
