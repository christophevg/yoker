"""Persisted — JSONL persistence wrapper.

Inherits from ContextManagerWrapper and adds JSONL persistence by
overriding mutating methods: delegate to wrapped, then bulk-rewrite the
full JSONL file via _persist_full_state(self._wrapped.get_messages()).

Record types (moved over from the former PersistenceContextManager):
  - session_start: Session metadata
  - message: User/assistant/system message
  - tool_result: Tool execution result
  - tool_call_message: Assistant message with tool_calls
  - turn_start: Turn boundary marker
  - turn_end: Turn completion marker
  - session_end: Session termination marker
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

# Unix-only file locking
if sys.platform != "win32":
  import fcntl
else:
  fcntl = None  # type: ignore[assignment]

from structlog import get_logger

from yoker.context.interface import ContextStatistics
from yoker.context.manager import BaseContextManager
from yoker.context.validator import is_safe_path, validate_session_id, validate_storage_path
from yoker.context.wrapper import ContextManagerWrapper
from yoker.exceptions import ContextCorruptionError, SessionNotFoundError

if TYPE_CHECKING:
  from yoker.core import Agent

logger = get_logger(__name__)

# File permissions
DIR_MODE = 0o700  # Owner-only for directories
FILE_MODE = 0o600  # Owner-only for files

# Default storage path for sessions
DEFAULT_STORAGE_PATH = Path.home() / ".cache" / "yoker" / "sessions"


class Persisted(ContextManagerWrapper):
  """Context manager wrapper with JSONL persistence.

  Stores conversation history in JSONL (JSON Lines) format with:
  - Atomic bulk-rewrite on every mutating call (no diff, no heuristic)
  - Secure file permissions
  - Session lifecycle tracking

  Usage:
    Persisted(SimpleContextManager(), session_id="x")  # persistence + env reminder
    Persisted(BaseContextManager(), session_id="x")    # persistence only
  """

  def __init__(
    self,
    wrapped: Any,
    storage_path: Path | str | None = None,
    session_id: str = "auto",
  ) -> None:
    """Initialize the persistence wrapper.

    Args:
      wrapped: The wrapped ContextManager (e.g. SimpleContextManager).
      storage_path: Directory for storing context files.
                     Defaults to ~/.cache/yoker/sessions.
      session_id: Session ID or "auto" to generate.

    Raises:
      ValidationError: If storage_path or session_id is invalid.
    """
    super().__init__(wrapped)

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
  ) -> "Persisted":
    """Resume an existing session.

    Args:
      session_id: Session ID to resume.
      storage_path: Directory for storing context files.

    Returns:
      Persisted wrapper with loaded session.

    Raises:
      SessionNotFoundError: If session doesn't exist.
      ContextCorruptionError: If session file is corrupted.
    """
    cm = cls(BaseContextManager(), storage_path=storage_path, session_id=session_id)
    if not cm.load():
      raise SessionNotFoundError(session_id)
    return cm

  def get_session_id(self) -> str:
    """Get the unique session identifier."""
    return self._session_id

  # --- agent reference ---

  @property
  def agent(self) -> "Agent | None":
    return self._wrapped.agent

  @agent.setter
  def agent(self, new_agent: "Agent") -> None:
    # Delegating to the wrapped setter clears and re-sets up initial context
    # (system prompt + skill discovery block). Persist the resulting state so
    # the JSONL file contains the system prompt.
    self._wrapped.agent = new_agent
    self._persist_full_state(self._wrapped.get_messages())

  # --- mutating overrides: delegate to wrapped, then bulk-rewrite JSONL ---

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    thinking: str | None = None,
  ) -> None:
    self._wrapped.add_message(role, content, metadata=metadata, thinking=thinking)
    self._persist_full_state(self._wrapped.get_messages())

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    self._wrapped.add_tool_result(tool_name, tool_id, result, success=success)
    self._tool_call_count += 1
    self._persist_full_state(self._wrapped.get_messages())

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
  ) -> None:
    self._wrapped.add_tool_calls(tool_calls, thinking=thinking)
    self._persist_full_state(self._wrapped.get_messages())

  def start_turn(self, user_message: str) -> None:
    self._wrapped.start_turn(user_message)
    self._last_turn_time = datetime.now()
    self._persist_full_state(self._wrapped.get_messages())

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    self._wrapped.end_turn(assistant_message, thinking=thinking)
    self._last_turn_time = datetime.now()
    self._persist_full_state(self._wrapped.get_messages())

  def clear(self) -> None:
    """Clear in-memory context and truncate the JSONL file."""
    self._wrapped.clear()
    self._tool_call_count = 0
    self._last_turn_time = None
    if self._file_path.exists():
      try:
        self._file_path.unlink()
      except OSError as e:
        logger.error("context_clear_failed", path=str(self._file_path), error=str(e))

  def save(self) -> None:
    """Persist context to storage via bulk-rewrite."""
    self._wrapped.save()
    self._persist_full_state(self._wrapped.get_messages())

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

  def close(self) -> None:
    """Release resources and append a session_end marker via bulk-rewrite."""
    self._wrapped.close()
    self._persist_full_state(self._wrapped.get_messages(), end_session=True)

  def get_statistics(self) -> ContextStatistics:
    """Merge wrapped stats with persistence stats."""
    base = self._wrapped.get_statistics()
    return ContextStatistics(
      message_count=base.message_count,
      turn_count=base.turn_count,
      tool_call_count=self._tool_call_count,
      start_time=self._start_time,
      last_turn_time=self._last_turn_time,
    )

  # --- private JSONL machinery ---

  def _persist_full_state(self, messages: list[dict[str, Any]], end_session: bool = False) -> None:
    """Bulk-rewrite the full JSONL file.

    Always rewrites the entire file with the current message list. No
    diff, no heuristic.
    """
    self._ensure_storage_directory()

    records: list[dict[str, Any]] = [
      {
        "type": "session_start",
        "timestamp": self._start_time.isoformat(),
        "data": {
          "session_id": self._session_id,
          "start_time": self._start_time.isoformat(),
        },
      }
    ]

    for item in messages:
      # Emit a turn_start marker for each user message so list_sessions can
      # count turns and capture the last user message preview.
      if item.get("role") == "user":
        records.append(
          {
            "type": "turn_start",
            "timestamp": datetime.now().isoformat(),
            "data": {"user_message": item.get("content", "")},
          }
        )
      record_type, data = self._item_to_record(item)
      if record_type and data is not None:
        records.append(
          {
            "type": record_type,
            "timestamp": datetime.now().isoformat(),
            "data": data,
          }
        )

    if end_session:
      records.append(
        {
          "type": "session_end",
          "timestamp": datetime.now().isoformat(),
          "data": {"end_time": datetime.now().isoformat()},
        }
      )

    self._atomic_write_jsonl(records)

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

  def _atomic_write_jsonl(self, records: list[dict[str, Any]]) -> None:
    """Write records to the JSONL file, bulk-rewriting the whole file."""
    self._ensure_storage_directory()
    if self._file_path.exists():
      try:
        self._file_path.chmod(FILE_MODE)
      except OSError:
        pass

    with open(self._file_path, "w") as f:
      if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
          for record in records:
            json.dump(record, f)
            f.write("\n")
          f.flush()
          os.fsync(f.fileno())
        finally:
          fcntl.flock(f.fileno(), fcntl.LOCK_UN)
      else:
        for record in records:
          json.dump(record, f)
          f.write("\n")
        f.flush()
        os.fsync(f.fileno())

  def _load_from_file(self) -> None:
    """Load context from JSONL file by replaying records into the wrapped cm.

    Raises:
      ContextCorruptionError: If file is corrupted.
    """
    self._wrapped.clear()
    self._tool_call_count = 0
    self._last_turn_time = None

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
    """Process a single JSONL record by replaying it into the wrapped cm.

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

    # The wrapped instance is a BaseContextManager (or subclass); we replay
    # records directly into its internal _messages list to preserve exact
    # message shapes (bypassing add_message's empty-content skip).
    wrapped = cast("BaseContextManager", self._wrapped)

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
      wrapped._messages.append(data)

    elif record_type == "tool_result":
      if "tool_id" not in data:
        raise ContextCorruptionError(
          str(self._file_path),
          line_num,
          "Missing tool_id",
        )
      wrapped._messages.append(
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
      wrapped._messages.append(
        {
          "role": "assistant",
          "tool_calls": data["tool_calls"],
          "content": "",
          "thinking": data.get("thinking"),
        }
      )

    elif record_type == "turn_start":
      ts = record.get("timestamp")
      if ts:
        self._last_turn_time = datetime.fromisoformat(ts)

    elif record_type == "turn_marker":
      ts = data.get("last_turn_time") or record.get("timestamp")
      if ts:
        self._last_turn_time = datetime.fromisoformat(ts)

    elif record_type in ("turn_end", "session_end"):
      pass

    else:
      logger.warning(
        "unknown_record_type",
        record_type=record_type,
        line=line_num,
      )


__all__ = ["Persisted", "DEFAULT_STORAGE_PATH"]
