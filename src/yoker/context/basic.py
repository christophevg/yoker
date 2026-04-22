"""Basic persistence context manager implementation.

Provides JSONL-based context persistence with secure file handling.

Note:
  File locking uses fcntl (Unix-only). On Windows, file writes
  are still atomic but lack inter-process locking protection.
  For production use on Windows, consider adding a cross-platform
  file locking library.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from yoker.context.interface import ContextStatistics
from yoker.context.validator import is_safe_path, validate_session_id, validate_storage_path
from yoker.exceptions import ContextCorruptionError, SessionNotFoundError
from yoker.logging import get_logger

log = get_logger(__name__)

# File permissions
DIR_MODE = 0o700  # Owner-only for directories
FILE_MODE = 0o600  # Owner-only for files


class BasicPersistenceContextManager:
  """Context manager with JSONL persistence.

  Stores conversation history in JSONL (JSON Lines) format with:
  - Atomic writes for crash safety
  - Secure file permissions
  - Session lifecycle tracking

  Record types:
  - session_start: Session metadata
  - message: User/assistant/system message
  - tool_result: Tool execution result
  - turn: Turn boundary marker
  - session_end: Session termination marker
  """

  def __init__(
    self,
    storage_path: Path | str,
    session_id: str = "auto",
  ) -> None:
    """Initialize context manager.

    Args:
      storage_path: Directory for storing context files.
      session_id: Session ID or "auto" to generate.

    Raises:
      ValidationError: If storage_path or session_id is invalid.
    """
    # Validate and resolve storage path
    self._storage_path = validate_storage_path(
      Path(storage_path), "context.storage_path"
    )

    # Validate session ID
    self._session_id = validate_session_id(session_id, "context.session_id")

    # In-memory context: ordered sequence of all items
    # Each item is {"type": "message"|"tool_result", "data": {...}}
    self._sequence: list[dict[str, Any]] = []

    # Statistics
    self._start_time = datetime.now()
    self._last_turn_time: datetime | None = None
    self._tool_call_count = 0

    # File path
    self._file_path = self._storage_path / f"{self._session_id}.jsonl"

    log.debug(
      "context_initialized",
      session_id=self._session_id,
      storage_path=str(self._storage_path),
    )

  def get_session_id(self) -> str:
    """Get the unique session identifier."""
    return self._session_id

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
  ) -> None:
    """Add a message to the context."""
    message: dict[str, Any] = {
      "role": role,
      "content": content,
    }
    if metadata:
      message["metadata"] = metadata

    self._sequence.append({"type": "message", "data": message})
    self._append_record("message", message)

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context."""
    tool_result: dict[str, Any] = {
      "tool_name": tool_name,
      "tool_id": tool_id,
      "result": result,
      "success": success,
    }

    self._sequence.append({"type": "tool_result", "data": tool_result})
    self._tool_call_count += 1
    self._append_record("tool_result", tool_result)

  def get_context(self) -> list[dict[str, Any]]:
    """Get the full context for backend submission.

    Returns messages and tool results in the correct order for the LLM API:
    - User messages
    - Assistant messages (with tool_calls)
    - Tool result messages (after the assistant message)
    """
    context: list[dict[str, Any]] = []

    for item in self._sequence:
      if item["type"] == "message":
        msg = item["data"]
        context.append({
          "role": msg["role"],
          "content": msg["content"],
        })
      elif item["type"] == "tool_result":
        tr = item["data"]
        context.append({
          "role": "tool",
          "name": tr["tool_name"],
          "content": tr["result"],
        })

    return context

  def get_messages(self) -> list[dict[str, Any]]:
    """Get all recorded messages (excludes tool results)."""
    messages: list[dict[str, Any]] = []
    for item in self._sequence:
      if item["type"] == "message":
        messages.append(item["data"])
    return messages

  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn."""
    turn_record: dict[str, Any] = {
      "user_message": user_message,
      "start_time": datetime.now().isoformat(),
    }
    self._sequence.append({"type": "turn", "data": turn_record})
    self._append_record("turn_start", turn_record)

    # Add user message
    self.add_message("user", user_message)

  def end_turn(self, assistant_message: str) -> None:
    """End the current conversation turn."""
    self._last_turn_time = datetime.now()

    # Add assistant message
    self.add_message("assistant", assistant_message)

    # Append turn end record
    self._append_record("turn_end", {
      "assistant_message": assistant_message,
    })

  def save(self) -> None:
    """Persist context to storage.

    Creates storage directory if needed and writes all records.
    """
    self._ensure_storage_directory()

    # Write session_start if file doesn't exist
    if not self._file_path.exists():
      self._write_session_start()

    # Flush any buffered writes
    self._flush_pending_records()

  def load(self) -> bool:
    """Load context from storage.

    Returns:
      True if context was loaded, False if no stored context exists.

    Raises:
      ContextCorruptionError: If stored context is corrupted.
    """
    if not self._file_path.exists():
      return False

    # Check if path is safe
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
    self._sequence.clear()
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
      log.debug("context_deleted", path=str(self._file_path))
    except OSError as e:
      log.error("context_delete_failed", path=str(self._file_path), error=str(e))
      raise

  def get_statistics(self) -> ContextStatistics:
    """Get statistics about context usage."""
    # Count items in sequence
    message_count = sum(1 for item in self._sequence if item["type"] == "message")
    turn_count = sum(1 for item in self._sequence if item["type"] == "turn")

    return ContextStatistics(
      message_count=message_count,
      turn_count=turn_count,
      tool_call_count=self._tool_call_count,
      start_time=self._start_time,
      last_turn_time=self._last_turn_time,
    )

  def close(self) -> None:
    """Release resources and flush any pending writes."""
    self._append_record("session_end", {
      "end_time": datetime.now().isoformat(),
    })

  # Private methods

  def _ensure_storage_directory(self) -> None:
    """Create storage directory with secure permissions if it doesn't exist."""
    if not self._storage_path.exists():
      self._storage_path.mkdir(parents=True, mode=DIR_MODE)
      log.debug("storage_created", path=str(self._storage_path))
    else:
      # Ensure correct permissions
      try:
        self._storage_path.chmod(DIR_MODE)
      except OSError:
        pass  # Ignore permission errors on existing directories

  def _append_record(self, record_type: str, data: dict[str, Any]) -> None:
    """Append a record to the JSONL file.

    Uses atomic write for crash safety.

    Args:
      record_type: Type of record (session_start, message, etc.).
      data: Record data dictionary.
    """
    self._ensure_storage_directory()

    record = {
      "type": record_type,
      "timestamp": datetime.now().isoformat(),
      "data": data,
    }

    self._atomic_write_jsonl(record)

  def _atomic_write_jsonl(self, record: dict[str, Any]) -> None:
    """Write a record atomically to the JSONL file.

    Uses file locking for atomic appends with secure permissions.

    Args:
      record: The record dictionary to write.
    """
    import fcntl

    # Ensure storage directory exists
    self._ensure_storage_directory()

    # Create file if needed with secure permissions
    if not self._file_path.exists():
      self._file_path.touch(mode=FILE_MODE)
    else:
      # Ensure permissions on existing file
      try:
        self._file_path.chmod(FILE_MODE)
      except OSError:
        pass

    # Write with file locking for atomic append
    with open(self._file_path, "a") as f:
      # Acquire exclusive lock
      fcntl.flock(f.fileno(), fcntl.LOCK_EX)
      try:
        json.dump(record, f)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
      finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

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

  def _flush_pending_records(self) -> None:
    """Flush any pending writes to disk.

    For JSONL files, this is a no-op since records are written immediately.
    """
    # Sync file to disk
    if self._file_path.exists():
      with open(self._file_path, "a") as f:
        os.fsync(f.fileno())

  def _load_from_file(self) -> None:
    """Load context from JSONL file.

    Parses all records and reconstructs in-memory state.

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
      # Already handled during initialization
      pass

    elif record_type == "message":
      if "role" not in data or "content" not in data:
        raise ContextCorruptionError(
          str(self._file_path),
          line_num,
          "Missing message fields",
        )
      self._sequence.append({"type": "message", "data": data})

    elif record_type == "tool_result":
      if "tool_id" not in data:
        raise ContextCorruptionError(
          str(self._file_path),
          line_num,
          "Missing tool_id",
        )
      self._sequence.append({"type": "tool_result", "data": data})
      self._tool_call_count += 1

    elif record_type == "turn_start":
      self._sequence.append({"type": "turn", "data": data})

    elif record_type == "turn_end":
      # Turn end - nothing special to do, statistics will be computed
      pass

    elif record_type == "session_end":
      # Session ended, nothing special to do
      pass

    else:
      log.warning(
        "unknown_record_type",
        record_type=record_type,
        line=line_num,
      )


__all__ = [
  "BasicPersistenceContextManager",
]
