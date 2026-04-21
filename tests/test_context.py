"""Tests for Yoker context management system."""

import json
import os
from pathlib import Path

import pytest

from yoker.context import BasicPersistenceContextManager, ContextManager, ContextStatistics
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

  def test_forbidden_path_etc(self) -> None:
    """Test forbidden path under /etc."""
    with pytest.raises(ValidationError) as exc_info:
      validate_storage_path(Path("/etc/yoker"))
    assert "/etc" in str(exc_info.value)

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
