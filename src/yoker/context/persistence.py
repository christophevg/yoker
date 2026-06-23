"""Persistence context manager implementation.

Provides PersistenceContextManager, a list-like context manager that persists
conversation history to JSONL files.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Unix-only file locking
if sys.platform != "win32":
  import fcntl
else:
  fcntl = None  # type: ignore[assignment]

from structlog import get_logger

from yoker.context.interface import ContextStatistics
from yoker.context.manager import ContextManager
from yoker.context.validator import is_safe_path, validate_session_id, validate_storage_path
from yoker.exceptions import ContextCorruptionError, SessionNotFoundError

logger = get_logger(__name__)

# File permissions
DIR_MODE = 0o700  # Owner-only for directories
FILE_MODE = 0o600  # Owner-only for files

# Default storage path for sessions
DEFAULT_STORAGE_PATH = Path.home() / ".cache" / "yoker" / "sessions"


class PersistenceContextManager(ContextManager):
  """Context manager with JSONL persistence.

  Stores conversation history in JSONL (JSON Lines) format with:
  - Atomic writes for crash safety
  - Secure file permissions
  - Session lifecycle tracking

  Record types:
  - session_start: Session metadata
  - message: User/assistant/system message
  - tool_result: Tool execution result
  - tool_call_message: Assistant message with tool_calls
  - turn_start: Turn boundary marker
  - turn_end: Turn completion marker
  - session_end: Session termination marker
  """

  def __init__(
    self,
    storage_path: Path | str | None = None,
    session_id: str = "auto",
  ) -> None:
    """Initialize context manager.

    Args:
      storage_path: Directory for storing context files.
                     Defaults to ~/.cache/yoker/sessions.
      session_id: Session ID or "auto" to generate.

    Raises:
      ValidationError: If storage_path or session_id is invalid.
    """
    super().__init__()

    if storage_path is None:
      storage_path = DEFAULT_STORAGE_PATH

    self._storage_path = validate_storage_path(
      Path(storage_path).expanduser(), "context.storage_path"
    )
    self._session_id = validate_session_id(session_id, "context.session_id")
    self._file_path = self._storage_path / f"{self._session_id}.jsonl"

    self._start_time = datetime.now()
    self._last_turn_time: datetime | None = None
    self._tool_call_count = 0

    logger.debug(
      "context_initialized",
      session_id=self._session_id,
      storage_path=str(self._storage_path),
    )

  @classmethod
  def resume(
    cls,
    session_id: str,
    storage_path: Path | str | None = None,
  ) -> "PersistenceContextManager":
    """Resume an existing session.

    Args:
      session_id: Session ID to resume.
      storage_path: Directory for storing context files.

    Returns:
      Context manager with loaded session.

    Raises:
      SessionNotFoundError: If session doesn't exist.
      ContextCorruptionError: If session file is corrupted.
    """
    cm = cls(storage_path=storage_path, session_id=session_id)
    if not cm.load():
      raise SessionNotFoundError(session_id)
    return cm

  def get_session_id(self) -> str:
    """Get the unique session identifier."""
    return self._session_id

  def append(self, item: dict[str, Any]) -> None:
    """Append an item and persist it to disk."""
    super().append(item)
    record_type, data = self._item_to_record(item)
    if record_type and data is not None:
      self._append_record(record_type, data)

  def _item_to_record(self, item: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Map an in-memory item to a JSONL record type and data."""
    role = item.get("role")
    if role == "tool":
      return "tool_result", {
        "tool_name": item["name"],
        "tool_id": item.get("tool_id", item["name"]),
        "result": item["content"],
        "success": item.get("success", True),
      }
    if role == "assistant" and "tool_calls" in item:
      return "tool_call_message", {
        "tool_calls": item["tool_calls"],
        "thinking": item.get("thinking"),
      }
    if role in ("user", "assistant", "system"):
      return "message", item
    return None, None

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context."""
    super().add_tool_result(tool_name, tool_id, result, success=success)
    self._tool_call_count += 1

  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn."""
    turn_record: dict[str, Any] = {
      "user_message": user_message,
      "start_time": datetime.now().isoformat(),
    }
    self._append_record("turn_start", turn_record)
    self.add_message("user", user_message)
    self._last_turn_time = datetime.now()

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    """End the current conversation turn."""
    super().end_turn(assistant_message, thinking=thinking)
    self._last_turn_time = datetime.now()
    self._append_record(
      "turn_end",
      {"assistant_message": assistant_message},
    )

  def save(self) -> None:
    """Persist context to storage.

    Creates storage directory if needed and writes session_start if the file
    does not yet exist. Individual items are persisted on append().
    """
    self._ensure_storage_directory()
    if not self._file_path.exists():
      self._write_session_start()
    self._flush()

  def load(self) -> bool:
    """Load context from storage.

    Returns:
      True if context was loaded, False if no stored context exists.

    Raises:
      ContextCorruptionError: If stored context is corrupted.
    """
    if not self._file_path.exists():
      return False
    if not is_safe_path(self._storage_path, self._file_path):
      raise SessionNotFoundError(self._session_id)

    try:
      self._load_from_file()
      return True
    except json.JSONDecodeError as e:
      raise ContextCorruptionError(
        str(self._file_path),
        e.lineno or 0,
        f"Invalid JSON: {e.msg}",
      ) from None

  def clear(self) -> None:
    """Clear in-memory context (does not delete from storage)."""
    super().clear()
    self._tool_call_count = 0
    self._last_turn_time = None

  def delete(self) -> None:
    """Delete stored context from disk.

    Raises:
      SessionNotFoundError: If session doesn't exist.
    """
    if not self._file_path.exists():
      raise SessionNotFoundError(self._session_id)

    try:
      self._file_path.unlink()
      logger.debug("context_deleted", path=str(self._file_path))
    except OSError as e:
      logger.error("context_delete_failed", path=str(self._file_path), error=str(e))
      raise

  def get_statistics(self) -> ContextStatistics:
    """Get statistics about context usage."""
    message_count = sum(1 for item in self.data if item.get("role") != "tool")
    turn_count = sum(1 for item in self.data if item.get("role") == "user")

    return ContextStatistics(
      message_count=message_count,
      turn_count=turn_count,
      tool_call_count=self._tool_call_count,
      start_time=self._start_time,
      last_turn_time=self._last_turn_time,
    )

  def close(self) -> None:
    """Release resources and flush any pending writes."""
    self._append_record(
      "session_end",
      {
        "end_time": datetime.now().isoformat(),
      },
    )

  # Private methods

  def _ensure_storage_directory(self) -> None:
    """Create storage directory with secure permissions if it doesn't exist."""
    if not self._storage_path.exists():
      self._storage_path.mkdir(parents=True, mode=DIR_MODE)
      logger.debug("storage_created", path=str(self._storage_path))
    else:
      try:
        self._storage_path.chmod(DIR_MODE)
      except OSError:
        pass

  def _append_record(self, record_type: str, data: dict[str, Any]) -> None:
    """Append a record to the JSONL file."""
    self._ensure_storage_directory()
    if not self._file_path.exists():
      self._write_session_start()

    record = {
      "type": record_type,
      "timestamp": datetime.now().isoformat(),
      "data": data,
    }
    self._atomic_write_jsonl(record)

  def _atomic_write_jsonl(self, record: dict[str, Any]) -> None:
    """Write a record atomically to the JSONL file."""
    self._ensure_storage_directory()
    if not self._file_path.exists():
      self._file_path.touch(mode=FILE_MODE)
    else:
      try:
        self._file_path.chmod(FILE_MODE)
      except OSError:
        pass

    with open(self._file_path, "a") as f:
      if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
          json.dump(record, f)
          f.write("\n")
          f.flush()
          os.fsync(f.fileno())
        finally:
          fcntl.flock(f.fileno(), fcntl.LOCK_UN)
      else:
        json.dump(record, f)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())

  def _write_session_start(self) -> None:
    """Write session_start record."""
    record = {
      "type": "session_start",
      "timestamp": self._start_time.isoformat(),
      "data": {
        "session_id": self._session_id,
        "start_time": self._start_time.isoformat(),
      },
    }
    self._atomic_write_jsonl(record)

  def _flush(self) -> None:
    """Flush any pending writes to disk."""
    if self._file_path.exists():
      with open(self._file_path, "a") as f:
        os.fsync(f.fileno())

  def _load_from_file(self) -> None:
    """Load context from JSONL file.

    Raises:
      ContextCorruptionError: If file is corrupted.
    """
    self.clear()

    line_num = 0
    try:
      with open(self._file_path) as f:
        for line_num, line in enumerate(f, start=1):
          line = line.strip()
          if not line:
            continue

          record = json.loads(line)
          self._process_record(record, line_num)

    except json.JSONDecodeError as e:
      raise ContextCorruptionError(
        str(self._file_path),
        line_num,
        f"Invalid JSON: {e.msg}",
      ) from None

  def _process_record(self, record: dict[str, Any], line_num: int) -> None:
    """Process a single JSONL record.

    Args:
      record: The parsed record dictionary.
      line_num: Line number for error messages.

    Raises:
      ContextCorruptionError: If record is malformed.
    """
    if "type" not in record:
      raise ContextCorruptionError(
        str(self._file_path),
        line_num,
        "Missing record type",
      )

    record_type = record.get("type")
    data = record.get("data", {})

    if record_type == "session_start":
      start_time_str = data.get("start_time") or record.get("timestamp")
      if start_time_str:
        self._start_time = datetime.fromisoformat(start_time_str)

    elif record_type == "message":
      if "role" not in data or "content" not in data:
        raise ContextCorruptionError(
          str(self._file_path),
          line_num,
          "Missing message fields",
        )
      self.data.append(data)

    elif record_type == "tool_result":
      if "tool_id" not in data:
        raise ContextCorruptionError(
          str(self._file_path),
          line_num,
          "Missing tool_id",
        )
      self.data.append(
        {
          "role": "tool",
          "name": data["tool_name"],
          "tool_id": data["tool_id"],
          "content": data["result"],
          "success": data.get("success", True),
        }
      )
      self._tool_call_count += 1

    elif record_type == "tool_call_message":
      if "tool_calls" not in data:
        raise ContextCorruptionError(
          str(self._file_path),
          line_num,
          "Missing tool_calls",
        )
      self.data.append(
        {
          "role": "assistant",
          "tool_calls": data["tool_calls"],
          "content": "",
          "thinking": data.get("thinking"),
        }
      )

    elif record_type == "turn_start":
      self._last_turn_time = datetime.fromisoformat(
        record.get("timestamp", datetime.now().isoformat())
      )

    elif record_type in ("turn_end", "session_end"):
      pass

    else:
      logger.warning(
        "unknown_record_type",
        record_type=record_type,
        line=line_num,
      )


__all__ = [
  "PersistenceContextManager",
  "DEFAULT_STORAGE_PATH",
]
