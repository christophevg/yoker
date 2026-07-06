"""Tests for UIBridge handling of SessionEvent envelopes and session lifecycle events."""

from pathlib import Path

import pytest

from yoker.events import (
  AgentFinishedEvent,
  AgentSpawnedEvent,
  EventType,
  SessionEndEvent,
  SessionEvent,
  SessionStartEvent,
)
from yoker.events.types import (
  AgentMessageEvent,
  ContentChunkEvent,
  ContentStartEvent,
  ThinkingStartEvent,
  TurnStartEvent,
)
from yoker.ui import UIBridge


class RecordingHandler:
  """Handler that records every call; implements optional lifecycle methods."""

  def __init__(self, *, implement_lifecycle: bool = True) -> None:
    self.calls: list = []
    self._implement_lifecycle = implement_lifecycle

  # Minimal surface used by the bridge dispatch tests.
  def start_content_stream(self) -> None:
    self.calls.append("start_content_stream")

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    self.calls.append(("stream_content", chunk, content_type))

  def end_content_stream(self, total_length: int) -> None:
    self.calls.append(("end_content_stream", total_length))

  def start_thinking_stream(self) -> None:
    self.calls.append("start_thinking_stream")

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    self.calls.append(("output_stats", duration_ms, prompt_tokens, eval_tokens))

  def output_command_result(self, result: str) -> None:
    self.calls.append(("output_command_result", result))

  def output_tool_call(self, tool_name: str, args: dict) -> None:
    self.calls.append(("output_tool_call", tool_name, args))

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    self.calls.append(("output_tool_result", tool_name, success, result))

  def output_tool_content(self, *args, **kwargs) -> None:
    self.calls.append(("output_tool_content", args, kwargs))

  def agent_spawned(self, name: str) -> None:
    if self._implement_lifecycle:
      self.calls.append(("agent_spawned", name))

  def agent_finished(self, name: str) -> None:
    if self._implement_lifecycle:
      self.calls.append(("agent_finished", name))


@pytest.mark.asyncio
class TestUIBridgeSessionEvent:
  """Tests for SessionEvent envelope handling."""

  async def test_bare_event_dispatched_unchanged(self) -> None:
    """A bare Event (single-agent path) is dispatched as today."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    await bridge(ContentStartEvent(type=EventType.CONTENT_START))
    assert "start_content_stream" in handler.calls
    assert bridge._current_agent_id is None

  async def test_session_event_dispatches_inner_event(self) -> None:
    """A SessionEvent envelope is unpacked; the inner event is dispatched."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    inner = ContentStartEvent(type=EventType.CONTENT_START)
    await bridge(SessionEvent(agent_id="researcher", event=inner))
    assert "start_content_stream" in handler.calls
    assert bridge._current_agent_id == "researcher"

  async def test_session_event_preserves_inner_event_payload(self) -> None:
    """The inner event's payload (text, content_type, ...) is forwarded unchanged."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    inner = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="chunk")
    await bridge(SessionEvent(agent_id="researcher", event=inner))
    assert ("stream_content", "chunk", "text/plain") in handler.calls

  async def test_session_event_for_thinking(self) -> None:
    """Thinking events wrapped in SessionEvent are dispatched."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    inner = ThinkingStartEvent(type=EventType.THINKING_START)
    await bridge(SessionEvent(agent_id="researcher", event=inner))
    assert "start_thinking_stream" in handler.calls

  async def test_consecutive_envelopes_update_agent_id(self) -> None:
    """Each SessionEvent updates the bridge's _current_agent_id."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    await bridge(
      SessionEvent(
        agent_id="researcher",
        event=ContentStartEvent(type=EventType.CONTENT_START),
      )
    )
    assert bridge._current_agent_id == "researcher"
    await bridge(
      SessionEvent(
        agent_id="writer",
        event=ContentStartEvent(type=EventType.CONTENT_START),
      )
    )
    assert bridge._current_agent_id == "writer"


@pytest.mark.asyncio
class TestUIBridgeSessionLifecycle:
  """Tests for AGENT_SPAWNED / AGENT_FINISHED / SESSION_* handling."""

  async def test_agent_spawned_dispatches_to_handler(self) -> None:
    """AGENT_SPAWNED calls ui.agent_spawned(name) when implemented."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    await bridge(
      AgentSpawnedEvent(
        type=EventType.AGENT_SPAWNED,
        session_id="s",
        agent_id="researcher",
        definition_name="researcher",
      )
    )
    assert ("agent_spawned", "researcher") in handler.calls

  async def test_agent_finished_dispatches_to_handler(self) -> None:
    """AGENT_FINISHED calls ui.agent_finished(name) when implemented."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    await bridge(
      AgentFinishedEvent(
        type=EventType.AGENT_FINISHED,
        session_id="s",
        agent_id="researcher",
      )
    )
    assert ("agent_finished", "researcher") in handler.calls

  async def test_handler_without_lifecycle_methods_not_broken(self) -> None:
    """A handler missing agent_spawned/agent_finished is not broken.

    A structurally-typed handler that doesn't expose the optional methods
    is silently skipped by the bridge's ``getattr`` guard — no
    ``AttributeError`` is raised.
    """

    class NoLifecycleHandler:
      """Structural handler that omits the optional lifecycle methods."""

      def start_content_stream(self) -> None:
        pass

      def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
        pass

      def end_content_stream(self, total_length: int) -> None:
        pass

      def start_thinking_stream(self) -> None:
        pass

      def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
        pass

      def output_command_result(self, result: str) -> None:
        pass

      def output_tool_call(self, tool_name: str, args: dict) -> None:
        pass

      def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
        pass

      def output_tool_content(self, *args, **kwargs) -> None:
        pass

    handler = NoLifecycleHandler()
    bridge = UIBridge(handler)
    # Should not raise — the bridge guards with getattr(..., None).
    await bridge(
      AgentSpawnedEvent(
        type=EventType.AGENT_SPAWNED,
        session_id="s",
        agent_id="researcher",
        definition_name="researcher",
      )
    )
    await bridge(
      AgentFinishedEvent(
        type=EventType.AGENT_FINISHED,
        session_id="s",
        agent_id="researcher",
      )
    )

  async def test_session_start_and_end_are_no_ops(self) -> None:
    """SESSION_START and SESSION_END do not call any UI method."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    await bridge(SessionStartEvent(type=EventType.SESSION_START, session_id="s"))
    await bridge(SessionEndEvent(type=EventType.SESSION_END, session_id="s"))
    assert handler.calls == []

  async def test_agent_message_is_no_op(self) -> None:
    """AGENT_MESSAGE is a no-op for the UI bridge (no display contract yet)."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    await bridge(
      AgentMessageEvent(
        type=EventType.AGENT_MESSAGE,
        session_id="s",
        from_id="a",
        to_id="b",
        content="hi",
      )
    )
    assert handler.calls == []

  async def test_unknown_event_type_still_ignored(self) -> None:
    """Unknown event types are silently ignored (regression guard)."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    # TURN_START is handled as a no-op by the bridge.
    await bridge(TurnStartEvent(type=EventType.TURN_START, message="hi"))
    assert handler.calls == []

  async def test_session_event_wrapping_session_level_event_dispatches_via_envelope(
    self,
  ) -> None:
    """A SessionEvent wrapping AGENT_SPAWNED dispatches through the envelope path."""
    handler = RecordingHandler()
    bridge = UIBridge(handler)
    inner = AgentSpawnedEvent(
      type=EventType.AGENT_SPAWNED,
      session_id="s",
      agent_id="researcher",
      definition_name="researcher",
    )
    await bridge(SessionEvent(agent_id="researcher", event=inner))
    assert ("agent_spawned", "researcher") in handler.calls
    assert bridge._current_agent_id == "researcher"


class TestUIHandlerProtocolOptionalMethods:
  """Tests for the UIHandler protocol optional lifecycle methods."""

  def test_no_base_ui_handler_module_created(self) -> None:
    """No src/yoker/ui/base.py exists."""
    base_path = (Path(__file__).parent.parent.parent / "src" / "yoker" / "ui" / "base.py").resolve()
    assert not base_path.exists(), f"BaseUIHandler module must not exist: {base_path}"

  def test_interactive_handler_implements_lifecycle(self) -> None:
    """InteractiveUIHandler implements agent_spawned and agent_finished."""
    from yoker.ui.interactive import InteractiveUIHandler

    assert hasattr(InteractiveUIHandler, "agent_spawned")
    assert hasattr(InteractiveUIHandler, "agent_finished")

  def test_batch_handler_does_not_implement_lifecycle(self) -> None:
    """BatchUIHandler does not implement the optional methods.

    The methods are documented on the protocol but not defined as Protocol
    members, so ``hasattr`` is False for handlers that don't implement
    them. The bridge's ``getattr`` guard skips them silently.
    """
    from yoker.ui.batch import BatchUIHandler

    assert not hasattr(BatchUIHandler, "agent_spawned")
    assert not hasattr(BatchUIHandler, "agent_finished")
