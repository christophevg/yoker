"""Tests for the per-Agent process queue.

When ``Session.send`` injects a message directly into
``Agent.process`` while the agent is mid-turn, parallel ``chat_stream``
calls must not happen. The Agent owns an ``asyncio.Queue`` and a
background consumer that processes requests one at a time. The public
``process()`` API is unchanged — the queueing is transparent.
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.agent import Agent
from yoker.config import Config


def _make_agent() -> Agent:
  """Build a standalone Agent without invoking a real backend.

  The backend is replaced with a MagicMock after construction so tests can
  drive ``process()`` without network calls.
  """
  agent = Agent(config=Config())
  # Replace the real backend with a mock so chat_stream never runs.
  agent._backend = MagicMock()
  return agent


def _patch_process_message(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
  """Patch ``process_message`` with ``handler`` (sync or async callable).

  ``handler`` receives ``(agent, message)`` and returns a string (sync) or
  an awaitable string (async). The patch targets the symbol imported into
  ``yoker.agent.__init__`` so the consumer sees it.
  """
  monkeypatch.setattr("yoker.agent.process_message", handler)


class TestProcessQueueSerialization:
  """Concurrent ``process()`` calls are serialized."""

  @pytest.mark.asyncio
  async def test_concurrent_calls_run_sequentially(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two concurrent process() calls are processed one at a time.

    The handler tracks in-flight concurrency; the second call must not
    start until the first has finished.
    """
    agent = _make_agent()
    in_flight = 0
    max_in_flight = 0
    started: list[str] = []
    finished: list[str] = []

    async def handler(_agent: Agent, message: str) -> str:
      nonlocal in_flight, max_in_flight
      in_flight += 1
      max_in_flight = max(max_in_flight, in_flight)
      started.append(message)
      # Yield to let other tasks attempt to enter.
      await asyncio.sleep(0.05)
      finished.append(message)
      in_flight -= 1
      return f"reply:{message}"

    _patch_process_message(monkeypatch, handler)

    results = await asyncio.gather(
      agent.process("first"),
      agent.process("second"),
    )
    assert results == ["reply:first", "reply:second"]
    # Strictly sequential: max concurrency was 1.
    assert max_in_flight == 1
    # Order preserved (FIFO queue).
    assert started == ["first", "second"]
    assert finished == ["first", "second"]

  @pytest.mark.asyncio
  async def test_fifo_order_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Three concurrent calls are processed in the order they were queued."""
    agent = _make_agent()
    order: list[str] = []

    async def handler(_agent: Agent, message: str) -> str:
      order.append(message)
      await asyncio.sleep(0.01)
      return message

    _patch_process_message(monkeypatch, handler)

    await asyncio.gather(
      agent.process("a"),
      agent.process("b"),
      agent.process("c"),
    )
    assert order == ["a", "b", "c"]

  @pytest.mark.asyncio
  async def test_single_call_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """A single process() call returns the response (no queueing visible)."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return f"echo:{message}"

    _patch_process_message(monkeypatch, handler)
    result = await agent.process("hello")
    assert result == "echo:hello"


class TestProcessQueueErrorPropagation:
  """Exceptions during processing are propagated to the correct caller."""

  @pytest.mark.asyncio
  async def test_exception_propagated_to_caller(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """An exception in process_message is set on the caller's future."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      raise RuntimeError(f"boom:{message}")

    _patch_process_message(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="boom:oops"):
      await agent.process("oops")

  @pytest.mark.asyncio
  async def test_exception_does_not_block_subsequent_calls(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """A failing call does not poison the queue — the next call succeeds."""
    agent = _make_agent()
    call_count = 0

    async def handler(_agent: Agent, message: str) -> str:
      nonlocal call_count
      call_count += 1
      if call_count == 1:
        raise RuntimeError("first fails")
      return f"ok:{message}"

    _patch_process_message(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="first fails"):
      await agent.process("first")
    # Subsequent call works — the consumer kept running.
    result = await agent.process("second")
    assert result == "ok:second"

  @pytest.mark.asyncio
  async def test_exception_goes_to_correct_future(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """When two calls overlap and the first raises, only the first sees it."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      if message == "boom":
        raise ValueError("boom-error")
      await asyncio.sleep(0.05)
      return f"ok:{message}"

    _patch_process_message(monkeypatch, handler)
    first = asyncio.ensure_future(agent.process("boom"))
    second = asyncio.ensure_future(agent.process("ok"))
    with pytest.raises(ValueError, match="boom-error"):
      await first
    result = await second
    assert result == "ok:ok"


class TestProcessQueueConsumerLifecycle:
  """The consumer task is created lazily and reused."""

  @pytest.mark.asyncio
  async def test_consumer_created_on_first_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """The consumer task is None until the first process() call."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return "ok"

    _patch_process_message(monkeypatch, handler)
    assert agent._process_task is None
    await agent.process("hi")
    assert agent._process_task is not None
    assert not agent._process_task.done()

  @pytest.mark.asyncio
  async def test_consumer_reused_across_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sequential calls reuse the same consumer task."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return f"r:{message}"

    _patch_process_message(monkeypatch, handler)
    await agent.process("a")
    task_after_first = agent._process_task
    await agent.process("b")
    task_after_second = agent._process_task
    assert task_after_first is task_after_second
