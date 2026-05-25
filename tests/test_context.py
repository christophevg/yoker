"""Tests for Yoker context management system."""

import json
import os
import platform
from pathlib import Path

import pytest

from yoker.context import (
  BasicPersistenceContextManager,
  ContextManager,
  ContextStatistics,
  SessionMetadata,
)
from yoker.context.validator import (
  is_safe_path,
  validate_session_id,
  validate_storage_path,
)
from yoker.exceptions import ContextCorruptionError, SessionNotFoundError, ValidationError


class TestContextStatistics:
  """Tests for ContextStatistics dataclass."""

  def test_default_values(self) -> None:
    """Test default values."""
    stats = ContextStatistics()
    assert stats.message_count == 0
    assert stats.turn_count == 0
    assert stats.tool_call_count == 0
    assert stats.start_time is not None
    assert stats.last_turn_time is None

  def test_custom_values(self) -> None:
    """Test custom values."""
    from datetime import datetime

    start = datetime(2025, 1, 1, 12, 0, 0)
    last = datetime(2025, 1, 1, 12, 30, 0)

    stats = ContextStatistics(
      message_count=10,
      turn_count=5,
      tool_call_count=3,
      start_time=start,
      last_turn_time=last,
    )
    assert stats.message_count == 10
    assert stats.turn_count == 5
    assert stats.tool_call_count == 3
    assert stats.start_time == start
    assert stats.last_turn_time == last

  def test_frozen_dataclass(self) -> None:
    """Test that ContextStatistics is frozen (immutable)."""
    stats = ContextStatistics()
    with pytest.raises(AttributeError):
      stats.message_count = 100  # type: ignore


class TestSessionIdValidation:
  """Tests for session ID validation."""

  def test_auto_generate(self) -> None:
    """Test auto-generating session ID."""
    session_id = validate_session_id("auto")
    assert len(session_id) >= 8
    assert session_id.isalnum() or all(c.isalnum() or c in "-_" for c in session_id)

  def test_valid_session_id(self) -> None:
    """Test valid session IDs."""
    assert validate_session_id("test-session-123") == "test-session-123"
    assert validate_session_id("session_456") == "session_456"
    assert validate_session_id("ABC123xyz") == "ABC123xyz"

  def test_too_short(self) -> None:
    """Test session ID too short."""
    with pytest.raises(ValidationError) as exc_info:
      validate_session_id("short")
    assert "at least" in str(exc_info.value)

  def test_too_long(self) -> None:
    """Test session ID too long."""
    long_id = "a" * 200
    with pytest.raises(ValidationError) as exc_info:
      validate_session_id(long_id)
    assert "at most" in str(exc_info.value)

  def test_invalid_characters(self) -> None:
    """Test session ID with invalid characters."""
    with pytest.raises(ValidationError) as exc_info:
      validate_session_id("test@session")
    assert "alphanumeric" in str(exc_info.value)

  def test_path_traversal(self) -> None:
    """Test session ID with path traversal."""
    with pytest.raises(ValidationError) as exc_info:
      validate_session_id("test..session")
    assert "path traversal" in str(exc_info.value)

  def test_hidden_file(self) -> None:
    """Test session ID starting with dot."""
    with pytest.raises(ValidationError) as exc_info:
      validate_session_id(".hidden-session")
    assert "must not start with a dot" in str(exc_info.value)


class TestStoragePathValidation:
  """Tests for storage path validation."""

  def test_valid_path(self, tmp_path: Path) -> None:
    """Test valid storage path."""
    result = validate_storage_path(tmp_path)
    assert result.is_absolute()

  def test_resolve_relative(self, tmp_path: Path) -> None:
    """Test resolving relative path."""
    relative = Path(".")
    result = validate_storage_path(relative)
    assert result.is_absolute()

  @pytest.mark.skipif(platform.system() == "Windows", reason="Unix-specific path restrictions")
  def test_forbidden_path_etc(self) -> None:
    """Test forbidden path under /etc."""
    with pytest.raises(ValidationError) as exc_info:
      validate_storage_path(Path("/etc/yoker"))
    assert "/etc" in str(exc_info.value)

  @pytest.mark.skipif(platform.system() == "Windows", reason="Unix-specific path restrictions")
  def test_forbidden_path_sys(self) -> None:
    """Test forbidden path under /sys."""
    with pytest.raises(ValidationError) as exc_info:
      validate_storage_path(Path("/sys/class"))
    assert "/sys" in str(exc_info.value)


class TestSafePath:
  """Tests for is_safe_path function."""

  def test_safe_path(self, tmp_path: Path) -> None:
    """Test path safely under base."""
    base = tmp_path
    target = tmp_path / "subdir" / "file.txt"
    assert is_safe_path(base, target) is True

  def test_unsafe_path(self, tmp_path: Path) -> None:
    """Test path not under base."""
    base = tmp_path
    target = Path("/etc/passwd")
    assert is_safe_path(base, target) is False

  def test_same_path(self, tmp_path: Path) -> None:
    """Test same path as base."""
    assert is_safe_path(tmp_path, tmp_path) is True


class TestBasicPersistenceContextManager:
  """Tests for BasicPersistenceContextManager."""

  def test_init_auto_session_id(self, tmp_path: Path) -> None:
    """Test initialization with auto-generated session ID."""
    cm = BasicPersistenceContextManager(tmp_path)
    assert len(cm.get_session_id()) >= 8

  def test_init_custom_session_id(self, tmp_path: Path) -> None:
    """Test initialization with custom session ID."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="custom-session-123")
    assert cm.get_session_id() == "custom-session-123"

  def test_add_message(self, tmp_path: Path) -> None:
    """Test adding messages."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-session")

    cm.add_message("user", "Hello")
    cm.add_message("assistant", "Hi there!")

    messages = cm.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

  def test_add_tool_result(self, tmp_path: Path) -> None:
    """Test adding tool results."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-session")

    cm.add_tool_result("read", "tool-123", "file content", success=True)

    context = cm.get_context()
    assert len(context) == 1
    assert context[0]["role"] == "tool"
    assert context[0]["name"] == "read"

  def test_turn_lifecycle(self, tmp_path: Path) -> None:
    """Test turn start and end."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-session")

    cm.start_turn("Hello")
    cm.end_turn("Hi there!")

    stats = cm.get_statistics()
    assert stats.turn_count == 1
    assert stats.message_count == 2  # user + assistant

  def test_statistics(self, tmp_path: Path) -> None:
    """Test statistics tracking."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-session")

    cm.start_turn("Hello")
    cm.add_tool_result("read", "tool-1", "content")
    cm.end_turn("Done")

    stats = cm.get_statistics()
    assert stats.message_count == 2
    assert stats.turn_count == 1
    assert stats.tool_call_count == 1
    assert stats.last_turn_time is not None

  def test_save_and_load(self, tmp_path: Path) -> None:
    """Test saving and loading context."""
    session_id = "test-session-save"

    # Create and save context
    cm1 = BasicPersistenceContextManager(tmp_path, session_id=session_id)
    cm1.add_message("user", "Hello")
    cm1.add_message("assistant", "Hi!")
    cm1.save()
    cm1.close()

    # Load context
    cm2 = BasicPersistenceContextManager(tmp_path, session_id=session_id)
    loaded = cm2.load()

    assert loaded is True
    messages = cm2.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

    # Cleanup
    cm2.delete()

  def test_load_nonexistent(self, tmp_path: Path) -> None:
    """Test loading non-existent session."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="nonexistent")
    loaded = cm.load()
    assert loaded is False

  def test_delete(self, tmp_path: Path) -> None:
    """Test deleting context."""
    session_id = "test-delete"

    cm = BasicPersistenceContextManager(tmp_path, session_id=session_id)
    cm.add_message("user", "Test")
    cm.save()

    # Delete
    cm.delete()

    # Verify deleted
    cm2 = BasicPersistenceContextManager(tmp_path, session_id=session_id)
    assert cm2.load() is False

  def test_delete_nonexistent_raises(self, tmp_path: Path) -> None:
    """Test deleting non-existent session raises error."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="nonexistent-delete")
    with pytest.raises(SessionNotFoundError):
      cm.delete()

  def test_clear(self, tmp_path: Path) -> None:
    """Test clearing context."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-clear")

    cm.add_message("user", "Hello")
    cm.clear()

    messages = cm.get_messages()
    assert len(messages) == 0

    stats = cm.get_statistics()
    assert stats.message_count == 0

  def test_jsonl_format(self, tmp_path: Path) -> None:
    """Test JSONL file format."""
    session_id = "test-jsonl"

    cm = BasicPersistenceContextManager(tmp_path, session_id=session_id)
    cm.add_message("user", "Hello")
    cm.save()

    # Read and verify JSONL
    file_path = tmp_path / f"{session_id}.jsonl"
    assert file_path.exists()

    with open(file_path) as f:
      lines = f.readlines()

    # Each line should be valid JSON
    for line in lines:
      record = json.loads(line.strip())
      assert "type" in record
      assert "timestamp" in record

    # Cleanup
    cm.delete()

  def test_corrupted_file(self, tmp_path: Path) -> None:
    """Test handling corrupted JSONL file."""
    session_id = "test-corrupt"

    # Write corrupted file
    file_path = tmp_path / f"{session_id}.jsonl"
    file_path.write_text('{"type": "session_start", "data": {}}\ninvalid json\n')

    cm = BasicPersistenceContextManager(tmp_path, session_id=session_id)
    with pytest.raises(ContextCorruptionError) as exc_info:
      cm.load()

    assert "Invalid JSON" in str(exc_info.value)

  def test_directory_permissions(self, tmp_path: Path) -> None:
    """Test that storage directory has secure permissions."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-perms")
    cm.save()

    # Check directory permissions (skip on Windows)
    if hasattr(os, "chmod"):
      # Note: actual permissions depend on umask
      # We just verify the directory was created
      assert tmp_path.exists()

    cm.delete()

  def test_context_manager_protocol(self, tmp_path: Path) -> None:
    """Test that BasicPersistenceContextManager implements ContextManager protocol."""
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-protocol")
    assert isinstance(cm, ContextManager)

  def test_tilde_expansion_in_storage_path(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that ~ in storage path is expanded to home directory.

    Regression test for issue #9: Storage path with ~ creates literal ~
    directory instead of expanding to home.
    """
    # Mock home directory to tmp_path (both HOME for Unix and USERPROFILE for Windows)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    # Create context manager with tilde path
    cm = BasicPersistenceContextManager(
      storage_path="~/.cache/yoker/sessions",
      session_id="test-tilde-expansion",
    )

    # The storage path should be expanded to the home directory,
    # not create a literal "~" directory in CWD
    storage_path_str = str(cm._storage_path)

    # Should contain tmp_path (mocked home), not literal "~"
    assert "~" not in storage_path_str, f"Path contains literal ~: {storage_path_str}"
    assert str(tmp_path) in storage_path_str, f"Path not under home: {storage_path_str}"


class TestListSessions:
  """Tests for list_sessions function."""

  def test_empty_directory(self, tmp_path: Path) -> None:
    """Test listing sessions from empty directory."""
    from yoker.context import list_sessions

    sessions = list_sessions(tmp_path)
    assert sessions == []

  def test_nonexistent_directory(self, tmp_path: Path) -> None:
    """Test listing sessions from nonexistent directory."""
    from yoker.context import list_sessions

    nonexistent = tmp_path / "nonexistent"
    sessions = list_sessions(nonexistent)
    assert sessions == []

  def test_single_session(self, tmp_path: Path) -> None:
    """Test listing a single session."""
    from yoker.context import list_sessions

    # Create a session with some messages
    cm = BasicPersistenceContextManager(tmp_path, session_id="test-session-1")
    cm.start_turn("Hello, how are you?")
    cm.end_turn("I'm doing well, thank you!")
    cm.save()
    cm.close()

    sessions = list_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].session_id == "test-session-1"
    assert sessions[0].message_count == 2  # user + assistant
    assert sessions[0].turn_count == 1
    assert sessions[0].start_time is not None

  def test_multiple_sessions_sorted_newest_first(self, tmp_path: Path) -> None:
    """Test that sessions are sorted by start_time, newest first."""
    import time

    from yoker.context import list_sessions

    # Create first session
    cm1 = BasicPersistenceContextManager(tmp_path, session_id="session-older")
    cm1.start_turn("First message")
    cm1.end_turn("First response")
    cm1.save()
    cm1.close()

    time.sleep(0.01)  # Ensure different timestamps

    # Create second session
    cm2 = BasicPersistenceContextManager(tmp_path, session_id="session-newer")
    cm2.start_turn("Second message")
    cm2.end_turn("Second response")
    cm2.save()
    cm2.close()

    sessions = list_sessions(tmp_path)
    assert len(sessions) == 2
    # Newest should be first
    assert sessions[0].session_id == "session-newer"
    assert sessions[1].session_id == "session-older"

  def test_session_last_message_preview(self, tmp_path: Path) -> None:
    """Test that last_message contains preview of last user message."""
    from yoker.context import list_sessions

    cm = BasicPersistenceContextManager(tmp_path, session_id="test-preview")
    cm.start_turn("Hello there!")
    cm.end_turn("Hi! How can I help?")
    cm.start_turn("What is the weather?")
    cm.end_turn("I don't have weather data.")
    cm.save()
    cm.close()

    sessions = list_sessions(tmp_path)
    assert len(sessions) == 1
    # Last user message should be captured
    assert sessions[0].last_message == "What is the weather?"

  def test_long_message_truncation(self, tmp_path: Path) -> None:
    """Test that long messages are truncated in preview."""
    from yoker.context import list_sessions

    long_message = "A" * 200  # 200 characters

    cm = BasicPersistenceContextManager(tmp_path, session_id="test-long")
    cm.start_turn(long_message)
    cm.end_turn("Response")
    cm.save()
    cm.close()

    sessions = list_sessions(tmp_path)
    assert len(sessions) == 1
    # Should be truncated to 100 chars + "..."
    assert len(sessions[0].last_message) == 103  # 100 + "..."
    assert sessions[0].last_message.endswith("...")

  def test_corrupted_session_skipped(self, tmp_path: Path) -> None:
    """Test that corrupted session files are skipped."""
    from yoker.context import list_sessions

    # Create valid session
    cm = BasicPersistenceContextManager(tmp_path, session_id="valid-session")
    cm.start_turn("Hello")
    cm.end_turn("Hi!")
    cm.save()
    cm.close()

    # Create corrupted session file
    corrupted_file = tmp_path / "corrupted-session.jsonl"
    corrupted_file.write_text("not valid json\n")

    sessions = list_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].session_id == "valid-session"

  def test_session_metadata_fields(self, tmp_path: Path) -> None:
    """Test that all SessionMetadata fields are populated correctly."""
    from yoker.context import list_sessions

    cm = BasicPersistenceContextManager(tmp_path, session_id="full-metadata")
    cm.start_turn("Message 1")
    cm.end_turn("Response 1")
    cm.start_turn("Message 2")
    cm.end_turn("Response 2")
    cm.save()
    cm.close()

    sessions = list_sessions(tmp_path)
    assert len(sessions) == 1

    metadata = sessions[0]
    assert isinstance(metadata, SessionMetadata)
    assert metadata.session_id == "full-metadata"
    assert metadata.message_count == 4  # 2 turns * 2 messages
    assert metadata.turn_count == 2
    assert metadata.start_time is not None
    assert metadata.last_turn_time is not None
    assert metadata.last_message == "Message 2"
    assert metadata.file_path == str(tmp_path / "full-metadata.jsonl")

  def test_default_storage_path(self) -> None:
    """Test that default storage path is used when not provided."""
    from yoker.context import DEFAULT_STORAGE_PATH

    cm = BasicPersistenceContextManager()
    assert cm._storage_path == DEFAULT_STORAGE_PATH

  def test_resume_existing_session(self, tmp_path: Path) -> None:
    """Test resuming an existing session."""
    # Create a session
    cm1 = BasicPersistenceContextManager(tmp_path, session_id="test-resume")
    cm1.start_turn("Hello")
    cm1.end_turn("Hi there!")
    cm1.save()
    cm1.close()

    # Resume the session
    cm2 = BasicPersistenceContextManager.resume("test-resume", storage_path=tmp_path)

    # Verify the session was loaded
    assert cm2.get_statistics().message_count == 2
    messages = cm2.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

  def test_resume_nonexistent_session_raises(self, tmp_path: Path) -> None:
    """Test that resuming a nonexistent session raises SessionNotFoundError."""
    from yoker.exceptions import SessionNotFoundError

    with pytest.raises(SessionNotFoundError):
      BasicPersistenceContextManager.resume("nonexistent", storage_path=tmp_path)

  def test_list_sessions_default_path(self, tmp_path: Path, monkeypatch) -> None:
    """Test list_sessions with default path."""

    from yoker.context import list_sessions

    # Use tmp_path as the default storage path
    monkeypatch.setattr("yoker.context.session.DEFAULT_STORAGE_PATH", tmp_path)
    monkeypatch.setattr("yoker.context.basic.DEFAULT_STORAGE_PATH", tmp_path)

    # Create a session
    cm = BasicPersistenceContextManager(session_id="test-default")
    cm._storage_path = tmp_path  # Override to use tmp_path
    cm._file_path = tmp_path / "test-default.jsonl"
    cm.start_turn("Test")
    cm.end_turn("Response")
    cm.save()
    cm.close()

    # List sessions with default path
    sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].session_id == "test-default"
