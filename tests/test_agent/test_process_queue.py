"""Tests for the per-Agent process queue.

When ``Session.send`` injects a message directly into
``Agent.process`` while the agent is mid-turn, parallel ``chat_stream``
calls must not happen. The Agent owns an ``asyncio.Queue`` and a
background consumer that processes requests one at a time. The public
``process()`` API is unchanged — the queueing is transparent.

Cross-loop reuse of one Agent instance (sequential turns, e.g. one
``asyncio.run(agent.process(msg))`` per turn from a sync wrapper) is
supported: when the serialization machinery's loop was closed (the
``asyncio.run`` teardown), ``process()`` rebuilds it on the new loop.
Use from a second, still-running loop fails loud with
``ConcurrentLoopError``.
"""

import asyncio
import threading
import time
from collections.abc import Coroutine
from typing import Any, TypeVar
from unittest.mock import MagicMock

import pytest

from yoker.config import Config
from yoker.core import Agent
from yoker.exceptions import ConcurrentLoopError

_T = TypeVar("_T")


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
  ``yoker.core.__init__`` so the consumer sees it.
  """
  monkeypatch.setattr("yoker.core.process_message", handler)


class _BackgroundLoop:
  """A private event loop running on a side thread.

  Lets a test execute coroutines on a *different*, live event loop
  (bridged via ``run_coroutine_threadsafe``) and tear it down the way
  ``asyncio.run`` does: cancel all pending tasks, stop the loop, close it.
  """

  def __init__(self) -> None:
    self.loop = asyncio.new_event_loop()
    self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)

  def start(self) -> None:
    """Start the loop on its side thread and wait until it is running."""
    self._thread.start()
    for _ in range(1000):
      if self.loop.is_running():
        return
      time.sleep(0.01)
    msg = "Background event loop failed to start"
    raise RuntimeError(msg)

  def run(self, coro: Coroutine[Any, Any, _T]) -> _T:
    """Run ``coro`` on the background loop and block until it completes."""
    return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=30)

  def stop(self) -> None:
    """Tear the loop down asyncio.run-style: cancel tasks, stop, close."""

    async def _shutdown() -> None:
      current = asyncio.current_task()
      assert current is not None
      pending = [t for t in asyncio.all_tasks(self.loop) if t is not current and not t.done()]
      for task in pending:
        task.cancel()
      if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    if self.loop.is_closed():
      return
    asyncio.run_coroutine_threadsafe(_shutdown(), self.loop).result(timeout=10)
    self.loop.call_soon_threadsafe(self.loop.stop)
    self._thread.join(timeout=10)
    self.loop.close()


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


class TestAgentAclose:
  """``Agent.aclose`` cancels the background ``_process_consumer`` task.

  Without this cleanup, the consumer — an infinite ``while True`` loop
  blocked on ``queue.get()`` — outlives the Agent object and triggers a
  ``"Task was destroyed but it is pending!"`` warning when the GC
  collects the agent.
  """

  @pytest.mark.asyncio
  async def test_aclose_cancels_consumer_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """aclose() cancels the _process_task and sets it to None."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return "ok"

    _patch_process_message(monkeypatch, handler)
    await agent.process("hi")
    assert agent._process_task is not None
    assert not agent._process_task.done()

    await agent.aclose()
    assert agent._process_task is None

  @pytest.mark.asyncio
  async def test_aclose_no_op_when_no_consumer(self) -> None:
    """aclose() is a no-op when _process_task was never created."""
    agent = _make_agent()
    assert agent._process_task is None
    await agent.aclose()
    assert agent._process_task is None

  @pytest.mark.asyncio
  async def test_aclose_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling aclose() twice does not raise."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return "ok"

    _patch_process_message(monkeypatch, handler)
    await agent.process("hi")
    await agent.aclose()
    await agent.aclose()  # second call should be a no-op
    assert agent._process_task is None

  @pytest.mark.asyncio
  async def test_aclose_task_cancelled_not_pending(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """After aclose(), the consumer task is cancelled (not left pending).

    This is the regression test for the "Task was destroyed but it is
    pending!" warning. We verify that after aclose() the task is
    cancelled (done() returns True) rather than left dangling.
    """
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return "ok"

    _patch_process_message(monkeypatch, handler)
    await agent.process("hi")
    task = agent._process_task
    assert task is not None and not task.done()

    await agent.aclose()
    # The task should now be done (cancelled) — not pending.
    assert task.done()
    assert task.cancelled()


class TestResetProcessMachinery:
  """``Agent._reset_process_machinery`` rebuilds dead-loop machinery."""

  @pytest.mark.asyncio
  async def test_reset_drains_pending_futures(self) -> None:
    """Stale futures enqueued on the dead loop are drained and cancelled.

    Fabricates the post-teardown state directly (queue with a future
    created on a since-closed loop) and runs the reset helper on the
    current loop, mirroring what ``process()`` does on a rebuild.
    """
    agent = _make_agent()

    dead_loop = asyncio.new_event_loop()
    stale_future = dead_loop.create_future()  # bound to the (about-to-die) loop
    dead_loop.close()

    stale_queue: asyncio.Queue[tuple[str, asyncio.Future[str]]] = asyncio.Queue()
    stale_queue.put_nowait(("stale", stale_future))  # non-blocking: no loop check
    agent._process_queue = stale_queue
    agent._process_loop = dead_loop

    fresh = agent._reset_process_machinery()
    agent._process_queue = fresh  # mirror the caller inside process()

    assert fresh is not stale_queue
    assert stale_queue.empty()  # drained
    assert stale_future.cancelled()  # best-effort cancel succeeded
    assert agent._process_task is not None
    assert not agent._process_task.done()  # new consumer started
    assert agent._idle_watchdog_task is None  # artifact cleared

    await agent.aclose()
    assert agent._process_task is None


class TestCrossLoopReuse:
  """Sequential cross-loop reuse of one Agent across event loops.

  Regression tests for the "Queue is bound to a different event loop"
  crash: a sync wrapper (e.g. a Prefect task) running one turn per
  ``asyncio.run()`` against a persistent Agent. Turn 1's loop teardown
  (cancel pending tasks + close) dead-ends the serialization machinery;
  turn 2 must rebuild it on the new loop instead of crashing. Use from a
  second, still-running loop fails loud with ``ConcurrentLoopError``.
  """

  @pytest.mark.asyncio
  async def test_two_sequential_closed_loop_turns(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn 1 on one loop, teardown, turn 2 on another — both succeed.

    Mirrors the incident: one agent, one turn per loop, the first loop's
    asyncio.run-style teardown (cancel pending + close) between turns.
    """
    agent = _make_agent()
    seen: list[str] = []

    async def handler(_agent: Agent, message: str) -> str:
      seen.append(message)
      return f"reply:{message}"

    _patch_process_message(monkeypatch, handler)

    bg = _BackgroundLoop()
    bg.start()
    result1 = bg.run(agent.process("first"))
    bg.stop()  # teardown: cancels the consumer, closes loop 1
    assert agent._process_loop is not None
    assert agent._process_loop.is_closed()

    result2 = await agent.process("second")  # new loop = the test loop

    assert result1 == "reply:first"
    assert result2 == "reply:second"
    assert seen == ["first", "second"]
    # Rebuilt machinery is now bound to the running (test) loop.
    assert agent._process_loop is asyncio.get_running_loop()

    await agent.aclose()

  @pytest.mark.asyncio
  async def test_rebuild_discards_old_machinery(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """After a rebuild, queue/task/loop are all fresh objects."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return "ok"

    _patch_process_message(monkeypatch, handler)

    bg = _BackgroundLoop()
    bg.start()
    bg.run(agent.process("turn-1"))
    old_task = agent._process_task
    old_queue = agent._process_queue
    old_loop = agent._process_loop
    bg.stop()

    assert old_task is not None and old_task.done()  # cancelled by teardown
    assert old_queue is not None
    assert old_loop is not None and old_loop.is_closed()

    result = await agent.process("turn-2")
    assert result == "ok"
    assert agent._process_task is not old_task
    assert agent._process_queue is not old_queue
    assert agent._process_loop is not old_loop
    assert agent._process_loop is asyncio.get_running_loop()
    assert agent._idle_watchdog_task is None

    await agent.aclose()

  @pytest.mark.asyncio
  async def test_second_live_loop_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second, still-running loop gets a loud ConcurrentLoopError.

    Turn 1 runs on a background loop that is kept ALIVE; the next call
    from the (different, live) test loop must raise ConcurrentLoopError
    and must not fork a second consumer or enqueue anything. After the
    background loop is torn down, the agent recovers via the rebuild
    path — the failed call left no corrupt state.
    """
    agent = _make_agent()
    seen: list[str] = []

    async def handler(_agent: Agent, message: str) -> str:
      seen.append(message)
      return "ok"

    _patch_process_message(monkeypatch, handler)

    bg = _BackgroundLoop()
    bg.start()
    old_task = None
    try:
      bg.run(agent.process("turn-1"))
      old_task = agent._process_task
      assert old_task is not None

      # Machinery lives on the still-running background loop; the test
      # loop is a second live loop → fail loud before any enqueue.
      with pytest.raises(ConcurrentLoopError, match="still-running event loop"):
        await agent.process("turn-2")
      assert agent._process_task is old_task  # no consumer forking
      assert seen == ["turn-1"]  # nothing was enqueued
    finally:
      bg.stop()

    # Recovery: teardown closed the machinery's loop → rebuild succeeds.
    result = await agent.process("turn-3")
    assert result == "ok"
    assert seen == ["turn-1", "turn-3"]
    assert agent._process_loop is asyncio.get_running_loop()

    await agent.aclose()

  @pytest.mark.asyncio
  async def test_aclose_cancels_only_current_consumer(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """After a rebuild, aclose() closes the current consumer cleanly."""
    agent = _make_agent()

    async def handler(_agent: Agent, message: str) -> str:
      return "ok"

    _patch_process_message(monkeypatch, handler)

    bg = _BackgroundLoop()
    bg.start()
    bg.run(agent.process("turn-1"))
    old_task = agent._process_task
    bg.stop()

    assert await agent.process("turn-2") == "ok"  # rebuild on the test loop
    new_task = agent._process_task
    assert new_task is not None and new_task is not old_task

    await agent.aclose()
    assert agent._process_task is None
    assert new_task.done()
    assert new_task.cancelled()
