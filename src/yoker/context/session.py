"""Session listing utilities.

Provides functions to list and query session metadata without loading
full context.
"""

import json
from datetime import datetime
from pathlib import Path

from structlog import get_logger

from yoker.context.interface import SessionMetadata

logger = get_logger(__name__)

# Maximum characters for last message preview
LAST_MESSAGE_PREVIEW_LENGTH = 100

# Default storage path for sessions (imported from basic.py to avoid circular dependency)
# This is defined in basic.py as DEFAULT_STORAGE_PATH
DEFAULT_STORAGE_PATH = Path.home() / ".cache" / "yoker" / "sessions"


def list_sessions(storage_path: Path | str | None = None) -> list[SessionMetadata]:
  """List all available sessions in a storage directory.

  Scans the storage directory for .jsonl files and extracts metadata
  without loading the full context.

  Args:
    storage_path: Directory containing session files.
                  Defaults to ~/.cache/yoker/sessions.

  Returns:
    List of SessionMetadata objects, sorted by start_time (newest first).

  Example:
    >>> from yoker.context import list_sessions
    >>> sessions = list_sessions()  # Uses default path
    >>> for session in sessions:
    ...     print(f"{session.session_id}: {session.message_count} messages")
  """
  if storage_path is None:
    storage_path = DEFAULT_STORAGE_PATH
  else:
    storage_path = Path(storage_path).expanduser()

  if not storage_path.exists():
    logger.debug("sessions_directory_not_found", path=str(storage_path))
    return []

  sessions: list[SessionMetadata] = []

  for file_path in storage_path.glob("*.jsonl"):
    try:
      metadata = _read_session_metadata(file_path)
      if metadata:
        sessions.append(metadata)
    except Exception as e:
      logger.warning(
        "session_metadata_read_error",
        path=str(file_path),
        error=str(e),
      )
      continue

  # Sort by start_time, newest first
  sessions.sort(key=lambda s: s.start_time, reverse=True)

  logger.debug("sessions_listed", count=len(sessions), path=str(storage_path))
  return sessions


def load_session_metadata(file_path: Path | str) -> SessionMetadata | None:
  """Load metadata from a specific session file.

  Args:
    file_path: Path to the session JSONL file.

  Returns:
    SessionMetadata if successful, None if file is invalid.

  Example:
    >>> from yoker.context import load_session_metadata
    >>> metadata = load_session_metadata("~/.cache/yoker/sessions/my-session.jsonl")
    >>> if metadata:
    ...     print(f"Session {metadata.session_id} has {metadata.message_count} messages")
  """
  file_path = Path(file_path).expanduser()

  if not file_path.exists():
    logger.debug("session_file_not_found", path=str(file_path))
    return None

  return _read_session_metadata(file_path)


def _read_session_metadata(file_path: Path) -> SessionMetadata | None:
  """Read session metadata from a JSONL file.

  Reads only the necessary records to extract metadata, avoiding
  loading the full context.

  Args:
    file_path: Path to the session JSONL file.

  Returns:
    SessionMetadata if successful, None if file is invalid.
  """
  session_id = file_path.stem
  start_time: datetime | None = None
  last_turn_time: datetime | None = None
  message_count = 0
  turn_count = 0
  last_message = ""

  try:
    with open(file_path) as f:
      for line in f:
        line = line.strip()
        if not line:
          continue

        record = json.loads(line)
        record_type = record.get("type")
        data = record.get("data", {})
        timestamp = record.get("timestamp")

        if record_type == "session_start":
          # Parse start time from session_start record
          start_time_str = data.get("start_time") or timestamp
          if start_time_str:
            start_time = datetime.fromisoformat(start_time_str)

        elif record_type == "turn_start":
          turn_count += 1
          # Update last turn time
          if timestamp:
            last_turn_time = datetime.fromisoformat(timestamp)

        elif record_type == "message":
          message_count += 1
          # Track last user message for preview
          if data.get("role") == "user":
            content = data.get("content", "")
            if len(content) > LAST_MESSAGE_PREVIEW_LENGTH:
              content = content[:LAST_MESSAGE_PREVIEW_LENGTH] + "..."
            last_message = content

  except json.JSONDecodeError:
    logger.warning("session_file_corrupted", path=str(file_path))
    return None
  except Exception as e:
    logger.warning("session_read_error", path=str(file_path), error=str(e))
    return None

  # Must have start_time to be valid
  if start_time is None:
    return None

  return SessionMetadata(
    session_id=session_id,
    start_time=start_time,
    last_turn_time=last_turn_time,
    message_count=message_count,
    turn_count=turn_count,
    last_message=last_message,
    file_path=str(file_path),
  )


__all__ = [
  "list_sessions",
  "load_session_metadata",
  "SessionMetadata",
]
