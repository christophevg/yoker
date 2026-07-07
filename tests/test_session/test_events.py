"""Tests for Session event aggregation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config, SessionConfig
from yoker.events import (
  AgentFinishedEvent,
  AgentSpawnedEvent,
  EventRecorder,
  EventType,
  SessionEvent,
  serialize_event,
)
from yoker.events.types import ContentChunkEvent, TurnStartEvent
from yoker.session import Session


def _register_researcher(session: Session) -> AgentDefinition:
  """Register a 'researcher' agent definition on the session registry."""
  agent_def = AgentDefinition(
    simple_name="researcher",
    description="Researcher",
    tools=("read",),
  )
  session.agents.register(agent_def)
  return agent_def


def _patch_agent_cls() -> tuple[MagicMock, MagicMock]:
  """Patch yoker.core.Agent and return (mock_cls, mock_child)."""
  mock_child = MagicMock()
  mock_child.process = AsyncMock(return_value="ok")
  mock_child.on_event = MagicMock()
  mock_cls = MagicMock(return_value=mock_child)
  return mock_cls, mock_child


class TestSessionEventEnvelope:
  """Tests for the SessionEvent frozen envelope wrapper."""

  def test_session_event_is_frozen(self) -> None:
    """SessionEvent is a frozen dataclass."""
    from dataclasses import FrozenInstanceError

    inner = TurnStartEvent(type=EventType.TURN_START, message="hi")
    env = SessionEvent(agent_id="researcher", event=inner)
    with pytest.raises(FrozenInstanceError):
      env.agent_id = "other"  # type: ignore[misc]

  def test_session_event_carries_agent_id_and_inner_event(self) -> None:
    """SessionEvent exposes agent_id and the unchanged inner event."""
    inner = TurnStartEvent(type=EventType.TURN_START, message="hi")
    env = SessionEvent(agent_id="researcher", event=inner)
    assert env.agent_id == "researcher"
    assert env.event is inner


class TestEventAggregation:
  """Tests for forwarding sub-agent events to session handlers."""

  @pytest.mark.asyncio
  async def test_spawned_agent_events_forwarded_in_envelope(self) -> None:
    """Events from a spawned agent reach session handlers wrapped in SessionEvent."""
    async with Session(config=Config()) as session:
      _register_researcher(session)
      # Patch yoker.session.Agent — that is the reference Session._create_agent
      # actually calls (yoker.session binds Agent at module import time).
      with patch("yoker.session.Agent") as mock_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        # Capture the forwarding handler registered on the child.
        mock_child.on_event = MagicMock()
        mock_cls.return_value = mock_child
        child, _agent_id = await session._spawn_internal("researcher")
        await child.process("hi")

      # The Session registered a forwarding handler on the child agent.
      mock_child.on_event.assert_called_once()
      forward_handler = mock_child.on_event.call_args[0][0]

      # Now simulate the child emitting an event.
      received: list = []
      session.on_event(lambda e: received.append(e))
      inner = TurnStartEvent(type=EventType.TURN_START, message="inner")
      import asyncio

      await asyncio.get_event_loop().create_task(forward_handler(inner))
      wrapped = [e for e in received if isinstance(e, SessionEvent)]
      assert len(wrapped) == 1
      assert wrapped[0].agent_id == "researcher"
      assert wrapped[0].event is inner

  @pytest.mark.asyncio
  async def test_inner_event_dispatched_unchanged(self) -> None:
    """The inner Event inside a SessionEvent is not modified."""
    async with Session(config=Config()) as session:
      _register_researcher(session)
      with patch("yoker.session.Agent") as mock_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.on_event = MagicMock()
        mock_cls.return_value = mock_child
        child, _agent_id = await session._spawn_internal("researcher")
        await child.process("hi")
      forward_handler = mock_child.on_event.call_args[0][0]

      received: list = []
      session.on_event(lambda e: received.append(e))
      original = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="chunk")
      import asyncio

      await asyncio.get_event_loop().create_task(forward_handler(original))
      wrapped = next(e for e in received if isinstance(e, SessionEvent))
      # Identity check: the inner event is the very same object.
      assert wrapped.event is original
      assert wrapped.event.text == "chunk"

  @pytest.mark.asyncio
  async def test_event_aggregation_disabled_suppresses_forwarding(self) -> None:
    """When event_aggregation=False, no forwarding handler is registered."""
    config = Config(session=SessionConfig(event_aggregation=False))
    async with Session(config=config) as session:
      _register_researcher(session)
      with patch("yoker.core.Agent") as mock_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.on_event = MagicMock()
        mock_cls.return_value = mock_child
        child, _agent_id = await session._spawn_internal("researcher")
        await child.process("hi")
      mock_child.on_event.assert_not_called()

  @pytest.mark.asyncio
  async def test_agent_spawned_event_emitted(self) -> None:
    """AGENT_SPAWNED is emitted when an agent is spawned."""
    async with Session(config=Config()) as session:
      _register_researcher(session)
      received: list = []
      session.on_event(lambda e: received.append(e))
      with patch("yoker.core.Agent") as mock_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.on_event = MagicMock()
        mock_cls.return_value = mock_child
        child, _agent_id = await session._spawn_internal("researcher")
        await child.process("hi")
      spawned = [e for e in received if isinstance(e, AgentSpawnedEvent)]
      assert len(spawned) == 1
      assert spawned[0].agent_id == "researcher"
      assert spawned[0].session_id == session.id
      assert spawned[0].definition_name == "researcher"

  @pytest.mark.asyncio
  async def test_agent_finished_event_emitted_and_agent_removed(self) -> None:
    """AGENT_FINISHED is emitted and the agent is removed on release."""
    async with Session(config=Config()) as session:
      _register_researcher(session)
      received: list = []
      session.on_event(lambda e: received.append(e))
      with patch("yoker.core.Agent") as mock_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.on_event = MagicMock()
        mock_cls.return_value = mock_child
        child, _agent_id = await session._spawn_internal("researcher")
        await child.process("hi")
        session.release(child)
      finished = [e for e in received if isinstance(e, AgentFinishedEvent)]
      assert len(finished) == 1
      assert finished[0].agent_id == "researcher"
      assert finished[0].session_id == session.id
      # agent removed from the active list.
      assert session.get_agent("researcher") is None

  @pytest.mark.asyncio
  async def test_agent_finished_emitted_even_on_timeout(self) -> None:
    """AGENT_FINISHED is emitted in the finally block even when the run times out."""
    import asyncio as _asyncio

    async def slow_process(_msg: str) -> str:
      await _asyncio.sleep(10)
      return "never"

    async with Session(config=Config()) as session:
      _register_researcher(session)
      received: list = []
      session.on_event(lambda e: received.append(e))
      with patch("yoker.core.Agent") as mock_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(side_effect=slow_process)
        mock_child.on_event = MagicMock()
        mock_cls.return_value = mock_child
        child, _agent_id = await session._spawn_internal("researcher")
        with pytest.raises(TimeoutError):
          await _asyncio.wait_for(child.process("hi"), timeout=0.05)
        session.release(child)
      finished = [e for e in received if isinstance(e, AgentFinishedEvent)]
      assert len(finished) == 1
      assert session.get_agent("researcher") is None


class TestEventRecorderOnSession:
  """Tests for EventRecorder capturing SessionEvent envelopes."""

  def test_serialize_session_event_envelope(self) -> None:
    """serialize_event produces the session_event envelope form for SessionEvent."""
    inner = TurnStartEvent(type=EventType.TURN_START, message="hi")
    env = SessionEvent(agent_id="researcher", event=inner)
    out = serialize_event(env)
    assert out["session_event"] is True
    assert out["agent_id"] == "researcher"
    assert out["event"]["type"] == "TURN_START"
    assert out["event"]["data"]["message"] == "hi"

  def test_serialize_bare_event_unchanged(self) -> None:
    """serialize_event on a bare Event produces the standard form (no envelope marker)."""
    inner = TurnStartEvent(type=EventType.TURN_START, message="hi")
    out = serialize_event(inner)
    assert "session_event" not in out
    assert out["type"] == "TURN_START"

  def test_roundtrip_session_event(self) -> None:
    """deserialize_event(serialize_event(env)) reconstructs the SessionEvent."""
    from yoker.events import deserialize_event

    inner = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="chunk")
    env = SessionEvent(agent_id="researcher", event=inner)
    roundtrip = deserialize_event(serialize_event(env))
    assert isinstance(roundtrip, SessionEvent)
    assert roundtrip.agent_id == "researcher"
    assert isinstance(roundtrip.event, ContentChunkEvent)
    assert roundtrip.event.text == "chunk"

  def test_roundtrip_bare_event_unchanged(self) -> None:
    """deserialize_event(serialize_event(bare)) reconstructs a bare Event."""
    from yoker.events import deserialize_event

    inner = TurnStartEvent(type=EventType.TURN_START, message="hi")
    roundtrip = deserialize_event(serialize_event(inner))
    assert not isinstance(roundtrip, SessionEvent)
    assert isinstance(roundtrip, TurnStartEvent)
    assert roundtrip.message == "hi"

  def test_recorder_writes_session_event_envelope(self, tmp_path: Path) -> None:
    """EventRecorder on a Session writes SessionEvent envelopes to JSONL."""
    recorder_path = tmp_path / "session.jsonl"
    recorder = EventRecorder(recorder_path)
    inner = TurnStartEvent(type=EventType.TURN_START, message="hi")
    env = SessionEvent(agent_id="researcher", event=inner)
    recorder(env)
    recorder.close()
    line = recorder_path.read_text().strip()
    entry = json.loads(line)
    assert entry["session_event"] is True
    assert entry["agent_id"] == "researcher"
    assert entry["event"]["type"] == "TURN_START"
