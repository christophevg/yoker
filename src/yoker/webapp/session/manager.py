"""Session management for WebSocket connections.

CRITICAL SECURITY: Provides DoS protection through session limits and memory protection through session expiration.

CVSS Score: 8.1 (High)
Vulnerability: DoS through unlimited sessions
Protection: Session limits and expiration
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
  from yoker.agent import Agent


class SessionLimitError(Exception):
  """Raised when session limit is reached.

  Attributes:
    current_count: Current number of sessions.
    max_sessions: Maximum allowed sessions.
  """

  def __init__(self, message: str, current_count: int, max_sessions: int) -> None:
    """Initialize SessionLimitError.

    Args:
      message: Error message.
      current_count: Current number of sessions.
      max_sessions: Maximum allowed sessions.
    """
    super().__init__(message)
    self.current_count = current_count
    self.max_sessions = max_sessions


@dataclass
class Session:
  """Session data for a WebSocket connection.

  Attributes:
    session_id: Unique session identifier.
    agent: Agent instance for this session.
    created_at: Session creation timestamp.
    last_activity: Last activity timestamp.
    context: Session context data.
  """

  session_id: str
  agent: "Agent | None" = None
  created_at: datetime = field(default_factory=datetime.now)
  last_activity: datetime = field(default_factory=datetime.now)
  context: dict[str, Any] = field(default_factory=dict)

  def update_activity(self) -> None:
    """Update last activity timestamp."""
    self.last_activity = datetime.now()

  def is_expired(self, timeout_seconds: int) -> bool:
    """Check if session is expired.

    Args:
      timeout_seconds: Session timeout in seconds.

    Returns:
      True if session is expired, False otherwise.
    """
    expiry_time = self.last_activity + timedelta(seconds=timeout_seconds)
    return datetime.now() > expiry_time


class SessionManager:
  """Manages WebSocket sessions with limits and expiration.

  Attributes:
    max_sessions: Maximum concurrent sessions.
    session_timeout_seconds: Session timeout in seconds.
    sessions: Active sessions dictionary.
  """

  def __init__(
    self,
    max_sessions: int = 100,
    session_timeout_seconds: int = 1800,
  ) -> None:
    """Initialize SessionManager.

    Args:
      max_sessions: Maximum concurrent sessions (DoS protection).
      session_timeout_seconds: Session timeout in seconds (memory protection).
    """
    self.max_sessions = max_sessions
    self.session_timeout_seconds = session_timeout_seconds
    self._sessions: dict[str, Session] = {}
    self._lock = asyncio.Lock()

  async def create_session(self, agent: "Agent | None" = None) -> str:
    """Create a new session.

    Args:
      agent: Optional Agent instance for this session.

    Returns:
      Unique session ID.

    Raises:
      SessionLimitError: If session limit is reached.
    """
    async with self._lock:
      # Check session limit
      if len(self._sessions) >= self.max_sessions:
        logger.warning(
          "session_limit_reached",
          extra={
            "current_count": len(self._sessions),
            "max_sessions": self.max_sessions,
          },
        )
        raise SessionLimitError(
          f"Session limit reached ({self.max_sessions} sessions)",
          current_count=len(self._sessions),
          max_sessions=self.max_sessions,
        )

      # Generate unique session ID
      session_id = str(uuid.uuid4())

      # Create session
      session = Session(
        session_id=session_id,
        agent=agent,
        created_at=datetime.now(),
        last_activity=datetime.now(),
      )

      self._sessions[session_id] = session

      logger.info(
        "session_created",
        extra={
          "session_id": session_id,
          "total_sessions": len(self._sessions),
        },
      )

      return session_id

  async def get_session(self, session_id: str) -> Session | None:
    """Get a session by ID.

    Args:
      session_id: Session ID.

    Returns:
      Session if found, None otherwise.
    """
    async with self._lock:
      session = self._sessions.get(session_id)

      if session:
        session.update_activity()

      return session

  async def remove_session(self, session_id: str) -> None:
    """Remove a session.

    Args:
      session_id: Session ID.
    """
    async with self._lock:
      session = self._sessions.pop(session_id, None)

      if session:
        # Call agent.end_session() if agent exists
        if session.agent:
          try:
            session.agent.end_session()
          except Exception as e:
            logger.error(
              "session_cleanup_error",
              extra={"session_id": session_id, "error": str(e)},
            )

        logger.info(
          "session_removed",
          extra={
            "session_id": session_id,
            "total_sessions": len(self._sessions),
          },
        )

  async def cleanup_expired(self) -> int:
    """Remove expired sessions.

    Returns:
      Number of sessions removed.
    """
    async with self._lock:
      expired_session_ids = []

      for session_id, session in self._sessions.items():
        if session.is_expired(self.session_timeout_seconds):
          expired_session_ids.append(session_id)

      # Remove expired sessions
      for session_id in expired_session_ids:
        # Remove session and call end_session if it exists
        removed_session: Session | None = self._sessions.pop(session_id, None)
        if removed_session:
          # Call end_session on the agent
          if removed_session.agent:
            try:
              removed_session.agent.end_session()
            except Exception as e:
              logger.error(
                "session_cleanup_error",
                extra={"session_id": session_id, "error": str(e)},
              )

      if expired_session_ids:
        logger.info(
          "sessions_expired",
          extra={
            "count": len(expired_session_ids),
            "remaining_sessions": len(self._sessions),
          },
        )

      return len(expired_session_ids)

  @property
  def active_count(self) -> int:
    """Get count of active sessions.

    Returns:
      Number of active sessions.
    """
    return len(self._sessions)