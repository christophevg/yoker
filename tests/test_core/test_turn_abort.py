"""Tests for the user-requested turn abort (double-Esc / Agent.abort()).

Covers the contract:

- ``abort()`` on an idle agent is a no-op returning ``False``.
- Aborting during the LLM stream cancels the stream; the caller sees
  ``TurnAbortedError`` and the agent stays usable for the next turn.
- Aborting during tool execution lets the running tool finish, records the
  remaining tool calls as aborted (context stays valid: every tool_call id
  gets a tool_result), makes no further LLM call, and the caller sees
  ``TurnAbortedError``.
- The TURN_ABORTED event is emitted so the UI can render the notice.
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.config import Config
from yoker.core import Agent
from yoker.core._processing import _execute_tool_calls
from yoker.events.types import EventType
from yoker.exceptions import TurnAbortedError


class TestAbortIdleAgent:
  def test_abort_without_active_turn_returns_false(self) -> None:
    agent = Agent(config=Config())
    assert agent.abort() is False
    assert agent.abort_requested is False


@pytest.mark.asyncio
async def test_abort_during_tools_records_remaining_as_aborted(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  from yoker.core import _processing

  calls = _make_tool_calls(["call_1", "call_2", "call_3"])
  started: list[str] = []

  async def fake_execute(agent: Any, call: Any, escalation: Any) -> None:
    started.append(call.id)
    if len(started) == 1:
      # Mirror the real executor: the running tool's result is recorded
      # before the batch notices the abort.
      agent.context.add_tool_result(
        tool_name="some_tool",
        tool_id=call.id,
        result="ok",
        success=True,
      )
      # User hits Esc Esc while the first tool is running.
      agent._abort_requested = True

  monkeypatch.setattr(_processing, "_execute_single_tool_call", fake_execute)

  agent = Agent(config=Config())

  skipped = await _execute_tool_calls(agent, calls, "", escalation=None)

  assert started == ["call_1"], "only the in-flight tool ran; the rest were skipped"
  assert skipped == 2
  messages = agent.context.get_context()
  results = [m for m in messages if m.get("role") == "tool"]
  assert [m["tool_id"] for m in results] == ["call_1", "call_2", "call_3"]
  assert results[1]["tool_id"] == "call_2"
  assert results[2]["tool_id"] == "call_3"
  assert "aborted" in results[1]["content"].lower()
  assert "aborted" in results[2]["content"].lower()
  assert results[1]["success"] is False
  assert results[2]["success"] is False


@pytest.mark.asyncio
async def test_abort_during_streaming_raises_turn_aborted(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """An abort during the stream surfaces as TurnAbortedError; the agent survives."""
  from yoker.backends import ChatChunk, ChatChunkEvent

  started = asyncio.Event()

  async def _stream() -> Any:
    yield ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0)
    started.set()
    # Never yields again — abort() cancels this task.
    await asyncio.sleep(60)

  mock_backend = MagicMock()
  mock_backend.chat_stream = MagicMock(return_value=_stream())
  monkeypatch.setattr("yoker.core.create_backend", lambda *a, **k: mock_backend)
  agent = Agent(config=Config())

  async def _abort_soon() -> None:
    await started.wait()
    # Mirror what the Esc-Esc watcher does.
    assert agent.abort() is True

  task = asyncio.create_task(_abort_soon())
  with pytest.raises(TurnAbortedError):
    await agent.process("hello")
  await task

  # The agent is usable for the next turn.
  assert agent._abort_requested is False
  assert agent._turn_phase is None


@pytest.mark.asyncio
async def test_abort_emits_turn_aborted_event(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  from yoker.backends import ChatChunk, ChatChunkEvent

  started = asyncio.Event()

  async def _stream() -> Any:
    yield ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0)
    started.set()
    await asyncio.sleep(60)

  mock_backend = MagicMock()
  mock_backend.chat_stream = MagicMock(return_value=_stream())
  monkeypatch.setattr("yoker.core.create_backend", lambda *a, **k: mock_backend)
  agent = Agent(config=Config())
  events: list[Any] = []
  agent.on_event(events.append)

  async def _abort_soon() -> None:
    await started.wait()
    agent.abort()

  task = asyncio.create_task(_abort_soon())
  with pytest.raises(TurnAbortedError):
    await agent.process("hello")
  await task

  aborted = [e for e in events if e.type is EventType.TURN_ABORTED]
  assert len(aborted) == 1
  assert aborted[0].phase == "streaming"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_abort_during_tools_via_process_records_aborted_calls(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Through the real loop: a mid-tool abort records every tool_call id's
  result, emits exactly one TURN_ABORTED(phase="tools") event, makes no
  further LLM call, and surfaces TurnAbortedError to the caller."""
  from yoker.backends import ChatChunk, ChatChunkEvent, ToolCallDelta
  from yoker.core import _processing

  started: list[str] = []

  async def fake_single_tool_call(agent: Any, call: Any, escalation: Any) -> None:
    # Mirror the real executor: the running tool's result is recorded
    # before the batch notices the abort.
    agent.context.add_tool_result(tool_name="some_tool", tool_id=call.id, result="ok", success=True)
    started.append(call.id)
    # User hits Esc Esc while the first tool is running.
    agent._abort_requested = True

  monkeypatch.setattr(_processing, "_execute_single_tool_call", fake_single_tool_call)

  # The stream terminates after the tool-call chunks (it never yields a
  # content response): _consume_stream's async-for exits on generator
  # exhaustion, so a forever-sleeping stream would never reach the tools
  # phase. The abort must end the turn before the loop rolls into a
  # second LLM call.
  async def _stream() -> Any:
    for idx, cid in enumerate(["call_1", "call_2", "call_3"]):
      delta = ToolCallDelta(index=idx, id=cid, name="some_tool", arguments_delta=None)
      yield ChatChunk(event=ChatChunkEvent.TOOL_CALL_START, index=idx, tool_call=delta)
      args = ToolCallDelta(index=idx, arguments_delta='{"x": 1}')
      yield ChatChunk(event=ChatChunkEvent.TOOL_CALL_DELTA, index=idx, tool_call=args)
      stop = ToolCallDelta(index=idx)
      yield ChatChunk(event=ChatChunkEvent.TOOL_CALL_STOP, index=idx, tool_call=stop)

  mock_backend = MagicMock()
  mock_backend.chat_stream = MagicMock(return_value=_stream())
  monkeypatch.setattr("yoker.core.create_backend", lambda *a, **k: mock_backend)
  agent = Agent(config=Config())
  events: list[Any] = []
  agent.on_event(events.append)

  with pytest.raises(TurnAbortedError):
    await agent.process("do the thing")

  assert started == ["call_1"], "only the in-flight tool ran; the rest were skipped"
  # Aborted before the loop could roll into a second LLM call.
  assert mock_backend.chat_stream.call_count == 1

  aborted = [e for e in events if e.type is EventType.TURN_ABORTED]
  assert len(aborted) == 1
  assert aborted[0].phase == "tools"  # type: ignore[attr-defined]

  messages = agent.context.get_context()
  assistant_calls = [
    tc for msg in messages if msg.get("role") == "assistant" for tc in (msg.get("tool_calls") or [])
  ]
  assert {tc["id"] for tc in assistant_calls} == {"call_1", "call_2", "call_3"}
  results = {m["tool_id"]: m for m in messages if m.get("role") == "tool"}
  # Context stays valid: every tool_call id has a paired tool result.
  assert set(results) == {"call_1", "call_2", "call_3"}
  assert results["call_1"]["success"] is True
  for cid in ("call_2", "call_3"):
    assert "aborted" in results[cid]["content"].lower()
    assert results[cid]["success"] is False

  # The agent is usable for the next turn.
  assert agent._abort_requested is False
  assert agent._turn_phase is None


def _make_tool_calls(ids: list[str]) -> list[MagicMock]:
  calls = []
  for cid in ids:
    call = MagicMock()
    call.id = cid
    call.parse_error = None
    call.function.name = "some_tool"
    call.function.arguments = {}
    calls.append(call)
  return calls
