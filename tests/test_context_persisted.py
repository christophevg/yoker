"""Tests for Persisted — JSONL persistence wrapper."""

import json
from pathlib import Path

import pytest

from yoker.agents import AgentDefinition
from yoker.context import BaseContextManager, Persisted, SimpleContextManager
from yoker.exceptions import ContextCorruptionError, SessionNotFoundError, ValidationError


class TestPersistedInit:
  """Tests for Persisted initialization."""

  def test_init_auto_session_id(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path)
    assert len(cm.get_session_id()) >= 8

  def test_init_custom_session_id(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="custom-session-123")
    assert cm.get_session_id() == "custom-session-123"

  def test_init_invalid_session_id_raises(self, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
      Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="short")

  def test_wrapped_is_stored(self, tmp_path: Path) -> None:
    wrapped = SimpleContextManager()
    cm = Persisted(wrapped, storage_path=tmp_path, session_id="test-session-123")
    assert cm._wrapped is wrapped


class TestPersistedAddMessage:
  """Tests for add_message on Persisted."""

  def test_add_message(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-session")
    cm.add_message("user", "Hello")
    cm.add_message("assistant", "Hi there!")

    messages = cm.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

  def test_add_message_persists_to_jsonl(self, tmp_path: Path) -> None:
    session_id = "test-persist-msg"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.add_message("user", "Hello")
    cm.add_message("assistant", "Hi!")

    file_path = tmp_path / f"{session_id}.jsonl"
    assert file_path.exists()

    with open(file_path) as f:
      lines = f.readlines()

    # session_start + turn_start (for user msg) + 2 messages = 4 lines
    assert len(lines) == 4
    for line in lines:
      record = json.loads(line.strip())
      assert "type" in record
      assert "timestamp" in record

  def test_add_tool_result(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-session")
    cm.add_tool_result("read", "tool-123", "file content", success=True)

    context = cm.get_context()
    assert len(context) == 1
    assert context[0]["role"] == "tool"
    assert context[0]["name"] == "read"
    assert cm.get_statistics().tool_call_count == 1

  def test_add_tool_calls_stores_arguments_as_dict(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-session")

    tool_calls = [
      {
        "id": "call_123",
        "function": {
          "name": "read_file",
          "arguments": {"path": "/tmp/test.txt", "mode": "r"},
        },
      }
    ]
    cm.add_tool_calls(tool_calls)

    context = cm.get_context()
    assert len(context) == 1
    assistant_msg = context[0]
    assert assistant_msg["role"] == "assistant"
    assert "tool_calls" in assistant_msg
    stored_tool_call = assistant_msg["tool_calls"][0]
    assert stored_tool_call["function"]["name"] == "read_file"
    assert isinstance(stored_tool_call["function"]["arguments"], dict)
    assert stored_tool_call["function"]["arguments"] == {"path": "/tmp/test.txt", "mode": "r"}

  def test_add_tool_calls_with_arguments_already_string(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-session")

    tool_calls = [
      {
        "id": "call_456",
        "function": {
          "name": "write_file",
          "arguments": '{"content": "hello world"}',
        },
      }
    ]
    cm.add_tool_calls(tool_calls)

    context = cm.get_context()
    stored_tool_call = context[0]["tool_calls"][0]
    assert isinstance(stored_tool_call["function"]["arguments"], str)
    assert stored_tool_call["function"]["arguments"] == '{"content": "hello world"}'


class TestPersistedTurnLifecycle:
  """Tests for turn lifecycle on Persisted."""

  def test_turn_lifecycle(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-session")
    cm.start_turn("Hello")
    cm.end_turn("Hi there!")

    stats = cm.get_statistics()
    assert stats.turn_count == 1
    assert stats.message_count == 2

  def test_statistics(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-session")
    cm.start_turn("Hello")
    cm.add_tool_result("read", "tool-1", "content")
    cm.end_turn("Done")

    stats = cm.get_statistics()
    assert stats.message_count == 2
    assert stats.turn_count == 1
    assert stats.tool_call_count == 1
    assert stats.last_turn_time is not None
    assert stats.start_time is not None


class TestPersistedSaveLoad:
  """Tests for save/load round-trip on Persisted."""

  def test_save_and_load(self, tmp_path: Path) -> None:
    session_id = "test-session-save"

    cm1 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm1.add_message("user", "Hello")
    cm1.add_message("assistant", "Hi!")
    cm1.save()
    cm1.close()

    cm2 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    loaded = cm2.load()

    assert loaded is True
    messages = cm2.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

    cm2.delete()

  def test_load_nonexistent(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="nonexistent")
    loaded = cm.load()
    assert loaded is False

  def test_delete(self, tmp_path: Path) -> None:
    session_id = "test-delete"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.add_message("user", "Test")
    cm.save()

    cm.delete()

    cm2 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    assert cm2.load() is False

  def test_delete_nonexistent_raises(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="nonexistent-delete")
    with pytest.raises(SessionNotFoundError):
      cm.delete()

  def test_clear(self, tmp_path: Path) -> None:
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-clear")
    cm.add_message("user", "Hello")
    cm.clear()

    assert cm.get_messages() == []
    stats = cm.get_statistics()
    assert stats.message_count == 0
    # JSONL file should be removed
    assert not (tmp_path / "test-clear.jsonl").exists()

  def test_jsonl_format(self, tmp_path: Path) -> None:
    session_id = "test-jsonl"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.add_message("user", "Hello")
    cm.save()

    file_path = tmp_path / f"{session_id}.jsonl"
    assert file_path.exists()

    with open(file_path) as f:
      lines = f.readlines()

    for line in lines:
      record = json.loads(line.strip())
      assert "type" in record
      assert "timestamp" in record

    cm.delete()

  def test_corrupted_file(self, tmp_path: Path) -> None:
    session_id = "test-corrupt"
    file_path = tmp_path / f"{session_id}.jsonl"
    file_path.write_text('{"type": "session_start", "data": {}}\ninvalid json\n')

    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    with pytest.raises(ContextCorruptionError) as exc_info:
      cm.load()
    assert "Invalid JSON" in str(exc_info.value)

  def test_bulk_rewrite_on_every_mutation(self, tmp_path: Path) -> None:
    """JSONL file is rewritten on every mutating call."""
    session_id = "test-bulk-rewrite"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.add_message("user", "first")

    file_path = tmp_path / f"{session_id}.jsonl"
    assert file_path.exists()

    with open(file_path) as f:
      lines_after_first = len(f.readlines())

    cm.add_message("user", "second")
    with open(file_path) as f:
      lines_after_second = len(f.readlines())

    # Bulk-rewrite: session_start + turn_start + 1 message = 3 lines after first
    # session_start + 2 turn_starts + 2 messages = 5 lines after second
    assert lines_after_first == 3
    assert lines_after_second == 5


class TestPersistedResume:
  """Tests for Persisted.resume."""

  def test_resume_existing_session(self, tmp_path: Path) -> None:
    cm1 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="test-resume")
    cm1.start_turn("Hello")
    cm1.end_turn("Hi there!")
    cm1.save()
    cm1.close()

    cm2 = Persisted.resume("test-resume", storage_path=tmp_path)

    assert cm2.get_statistics().message_count == 2
    messages = cm2.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"

  def test_resume_nonexistent_session_raises(self, tmp_path: Path) -> None:
    with pytest.raises(SessionNotFoundError):
      Persisted.resume("nonexistent", storage_path=tmp_path)


class TestPersistedComposition:
  """Tests for composition: Persisted(SimpleContextManager()) and
  Persisted(BaseContextManager()).

  Verifies the key acceptance criterion: a JSONL file produced by
  Persisted(SimpleContextManager()) survives a fresh
  Persisted(BaseContextManager(), session_id=...).load() and includes the
  env-reminder + system-prompt message.
  """

  def test_persisted_simple_includes_env_reminder(self, tmp_path: Path) -> None:
    from yoker.agent import Agent
    from yoker.config import Config

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for context test.",
    )
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="compose-simple")
    Agent(config=Config(), agent_definition=agent_def, context_manager=cm)

    messages = cm.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    content = system_messages[0].get("content", "")
    assert "You are running inside the Yoker agent harness" in content
    assert "Custom system prompt for context test." in content

    # The system prompt was persisted to the JSONL file
    cm.save()
    file_path = tmp_path / "compose-simple.jsonl"
    assert file_path.exists()

    # Replay with Persisted(BaseContextManager()) and verify the system message
    # is present in the loaded context.
    cm2 = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="compose-simple")
    assert cm2.load() is True
    loaded_system = [m for m in cm2.get_messages() if m.get("role") == "system"]
    assert len(loaded_system) == 1
    loaded_content = loaded_system[0].get("content", "")
    assert "You are running inside the Yoker agent harness" in loaded_content
    assert "Custom system prompt for context test." in loaded_content

  def test_persisted_base_no_env_reminder(self, tmp_path: Path) -> None:
    from yoker.agent import Agent
    from yoker.config import Config

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for context test.",
    )
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="compose-base")
    Agent(config=Config(), agent_definition=agent_def, context_manager=cm)

    messages = cm.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    # BaseContextManager adds only the raw system prompt (no env reminder)
    assert system_messages[0].get("content", "") == "Custom system prompt for context test."

    cm.save()
    cm2 = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="compose-base")
    assert cm2.load() is True
    loaded_system = [m for m in cm2.get_messages() if m.get("role") == "system"]
    assert len(loaded_system) == 1
    assert loaded_system[0].get("content", "") == "Custom system prompt for context test."


class TestPersistedTildeExpansion:
  """Regression test for tilde expansion in storage_path."""

  def test_tilde_expansion_in_storage_path(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    cm = Persisted(
      SimpleContextManager(),
      storage_path="~/.cache/yoker/sessions",
      session_id="test-tilde-expansion",
    )

    storage_path_str = str(cm._storage_path)
    assert "~" not in storage_path_str, f"Path contains literal ~: {storage_path_str}"
    assert str(tmp_path) in storage_path_str, f"Path not under home: {storage_path_str}"


class TestPersistedImplementsProtocol:
  """Verify Persisted satisfies the ContextManager Protocol."""

  def test_persisted_is_context_manager(self, tmp_path: Path) -> None:
    from yoker.context import ContextManager

    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="protocol-test")
    assert isinstance(cm, ContextManager)
