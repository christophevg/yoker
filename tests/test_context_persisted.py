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
    from yoker.config import Config
    from yoker.core import Agent

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
    from yoker.config import Config
    from yoker.core import Agent

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


class TestPersistedBugFixes:
  """Regression tests for the context-persistence bug fix (PR #55).

  Covers:
    - Bug #1: tool results ARE persisted to JSONL (were dropped because
      _persist_full_state used get_messages() which excludes role=tool).
    - Bug #2: assistant narration content is preserved on tool-call turns
      (was hardcoded to "" in add_tool_calls).
    - Bug #3: user messages are NOT duplicated in the JSONL file
      (turn_start marker used to carry the same content as the message
      record).
    - Regression: tool results remain in the context for the next turn
      (via get_context()) and survive a save/load round-trip.
  """

  def _read_records(self, file_path: Path) -> list[dict]:
    records = []
    with open(file_path) as f:
      for line in f:
        line = line.strip()
        if line:
          records.append(json.loads(line))
    return records

  def test_tool_result_persisted_to_jsonl(self, tmp_path: Path) -> None:
    """Bug #1: a tool result is written as a `tool_result` record."""
    session_id = "bug1-tool-result"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.add_tool_calls([{"id": "call_1", "function": {"name": "read", "arguments": {}}}])
    cm.add_tool_result("read", "call_1", "file content", success=True)
    cm.save()

    records = self._read_records(tmp_path / f"{session_id}.jsonl")
    tool_result_records = [r for r in records if r["type"] == "tool_result"]
    assert len(tool_result_records) == 1
    data = tool_result_records[0]["data"]
    assert data["tool_name"] == "read"
    assert data["tool_id"] == "call_1"
    assert data["result"] == "file content"
    assert data["success"] is True

  def test_tool_result_round_trips_through_load(self, tmp_path: Path) -> None:
    """Bug #1: tool results survive save/load (replay restores them)."""
    session_id = "bug1-roundtrip"
    cm1 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm1.add_tool_calls([{"id": "call_1", "function": {"name": "read", "arguments": {}}}])
    cm1.add_tool_result("read", "call_1", "file content", success=True)
    cm1.save()
    cm1.close()

    cm2 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    assert cm2.load() is True

    context = cm2.get_context()
    tool_messages = [m for m in context if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["name"] == "read"
    assert tool_messages[0]["content"] == "file content"
    assert tool_messages[0]["tool_id"] == "call_1"

  def test_assistant_content_preserved_on_tool_call_turn(self, tmp_path: Path) -> None:
    """Bug #2: add_tool_calls stores the narration content, not ""."""
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="bug2-content")
    tool_calls = [{"id": "call_1", "function": {"name": "read", "arguments": {}}}]
    cm.add_tool_calls(tool_calls, content="Let me investigate the git tool...")

    context = cm.get_context()
    assert len(context) == 1
    assert context[0]["role"] == "assistant"
    assert context[0]["content"] == "Let me investigate the git tool..."
    assert "tool_calls" in context[0]

  def test_assistant_content_persisted_and_replayed(self, tmp_path: Path) -> None:
    """Bug #2: the narration content survives save/load round-trip."""
    session_id = "bug2-roundtrip"
    cm1 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm1.add_tool_calls(
      [{"id": "call_1", "function": {"name": "read", "arguments": {}}}],
      content="Let me dig into the implementation.",
    )
    cm1.save()
    cm1.close()

    cm2 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    assert cm2.load() is True

    context = cm2.get_context()
    assistant_msgs = [m for m in context if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0]["content"] == "Let me dig into the implementation."

  def test_user_message_not_duplicated_in_jsonl(self, tmp_path: Path) -> None:
    """Bug #3: exactly one `message` record with role=user per start_turn."""
    session_id = "bug3-no-dup"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.start_turn("Hello there")
    cm.save()

    records = self._read_records(tmp_path / f"{session_id}.jsonl")
    user_message_records = [
      r for r in records if r["type"] == "message" and r["data"].get("role") == "user"
    ]
    assert len(user_message_records) == 1
    assert user_message_records[0]["data"]["content"] == "Hello there"

    # turn_start is still emitted as a pure marker (no user_message field).
    turn_start_records = [r for r in records if r["type"] == "turn_start"]
    assert len(turn_start_records) == 1
    assert "user_message" not in turn_start_records[0]["data"]

  def test_turn_start_still_emitted_for_turn_count(self, tmp_path: Path) -> None:
    """Bug #3 regression guard: turn_start marker is still present (for list_sessions)."""
    session_id = "bug3-turn-marker"
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm.start_turn("first turn")
    cm.start_turn("second turn")
    cm.save()

    records = self._read_records(tmp_path / f"{session_id}.jsonl")
    turn_start_records = [r for r in records if r["type"] == "turn_start"]
    assert len(turn_start_records) == 2

  def test_tool_result_available_for_next_turn(self, tmp_path: Path) -> None:
    """Regression: after a tool call → result, the result is in get_context()."""
    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id="regression-next-turn")
    cm.start_turn("Please read the file.")
    cm.add_tool_calls(
      [{"id": "call_1", "function": {"name": "read", "arguments": {"path": "foo.py"}}}],
      content="Reading foo.py now.",
    )
    cm.add_tool_result("read", "call_1", "contents of foo.py", success=True)

    context = cm.get_context()
    # user, assistant (with tool_calls + content), tool
    assert len(context) == 3
    assert context[0]["role"] == "user"
    assert context[1]["role"] == "assistant"
    assert context[1]["content"] == "Reading foo.py now."
    assert context[2]["role"] == "tool"
    assert context[2]["content"] == "contents of foo.py"
    assert context[2]["tool_id"] == "call_1"

  def test_full_loop_survives_save_load(self, tmp_path: Path) -> None:
    """Regression: a tool call → result → next-turn loop survives save/load.

    On replay, the tool-call/tool-result pairing must be intact (no orphaned
    tool calls), and the assistant narration must be preserved.
    """
    session_id = "regression-full-loop"
    cm1 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    cm1.start_turn("Please read foo.py.")
    cm1.add_tool_calls(
      [{"id": "call_1", "function": {"name": "read", "arguments": {"path": "foo.py"}}}],
      content="Let me read foo.py.",
    )
    cm1.add_tool_result("read", "call_1", "contents of foo.py", success=True)
    cm1.end_turn("Done reading foo.py.")
    cm1.save()
    cm1.close()

    cm2 = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    assert cm2.load() is True

    context = cm2.get_context()
    # user, assistant (tool_calls + content), tool, assistant (end_turn)
    assert len(context) == 4
    assert context[0]["role"] == "user"
    assert context[1]["role"] == "assistant"
    assert context[1]["content"] == "Let me read foo.py."
    assert "tool_calls" in context[1]
    assert context[2]["role"] == "tool"
    assert context[2]["content"] == "contents of foo.py"
    assert context[3]["role"] == "assistant"
    assert context[3]["content"] == "Done reading foo.py."

  def test_legacy_jsonl_file_loads_correctly(self, tmp_path: Path) -> None:
    """Backward compatibility: JSONL files written before the fix still load.

    The legacy pre-fix format had two quirks the fix corrected:
      - turn_start carried a `user_message` field (the loader now ignores it;
        the user content lives in the `message` record with role=user)
      - tool_call_message had no `content` field (the loader now defaults
        missing content to "")
    A legacy file that also wrote a duplicate `message` record with role=user
    (the source of the duplication bug) must load as a single user message.
    """
    session_id = "legacy-pre-fix"
    file_path = tmp_path / f"{session_id}.jsonl"
    ts = "2025-01-01T00:00:00"
    legacy_records = [
      {
        "type": "session_start",
        "timestamp": ts,
        "data": {"session_id": session_id, "start_time": ts},
      },
      # Old format carried user_message in turn_start data.
      {"type": "turn_start", "timestamp": ts, "data": {"user_message": "Please read foo.py."}},
      # ...and also wrote a message record with role=user (the duplication bug).
      {
        "type": "message",
        "timestamp": ts,
        "data": {"role": "user", "content": "Please read foo.py."},
      },
      # Old tool_call_message had no content field.
      {
        "type": "tool_call_message",
        "timestamp": ts,
        "data": {
          "tool_calls": [
            {"id": "call_1", "function": {"name": "read", "arguments": {"path": "foo.py"}}}
          ],
          "thinking": None,
        },
      },
      {"type": "message", "timestamp": ts, "data": {"role": "assistant", "content": "Done."}},
      {"type": "session_end", "timestamp": ts, "data": {"end_time": ts}},
    ]
    file_path.write_text("".join(json.dumps(r) + "\n" for r in legacy_records))

    cm = Persisted(SimpleContextManager(), storage_path=tmp_path, session_id=session_id)
    assert cm.load() is True

    context = cm.get_context()
    # user, assistant (tool_calls, content=""), assistant (end_turn)
    user_messages = [m for m in context if m.get("role") == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["content"] == "Please read foo.py."

    assistant_with_tools = [
      m for m in context if m.get("role") == "assistant" and "tool_calls" in m
    ]
    assert len(assistant_with_tools) == 1
    # content defaults to "" when the field is absent from the legacy record.
    assert assistant_with_tools[0]["content"] == ""
    assert assistant_with_tools[0]["tool_calls"][0]["function"]["name"] == "read"

    plain_assistant = [m for m in context if m.get("role") == "assistant" and "tool_calls" not in m]
    assert len(plain_assistant) == 1
    assert plain_assistant[0]["content"] == "Done."
