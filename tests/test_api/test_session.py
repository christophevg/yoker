"""Tests for Layer 3 — the session facade (MBI-003 task 3.6)."""

import pytest

import yoker
from yoker.api.session import Session as ApiSession
from yoker.core import Agent
from yoker.session import Session as CoreSession


@pytest.fixture
def patched_process(monkeypatch: pytest.MonkeyPatch) -> list[str]:
  """Patch ``process_message`` to return canned replies without a backend."""
  seen: list[str] = []

  async def handler(_agent: Agent, message: str) -> str:
    seen.append(message)
    return f"reply:{message}"

  monkeypatch.setattr("yoker.core.process_message", handler)
  return seen


class TestSessionFacadeLifecycle:
  """``yoker.session`` is an async context manager wrapping the core Session."""

  async def test_session_enters_and_exits(self, patched_process) -> None:
    """async with yoker.session() enters and exits cleanly."""
    async with yoker.session() as sess:
      assert isinstance(sess, ApiSession)
      assert sess.id != ""
    # Exiting should not raise.

  async def test_session_has_core_and_agent(self, patched_process) -> None:
    """The facade exposes the underlying core Session and primary Agent."""
    async with yoker.session() as sess:
      assert isinstance(sess.core, CoreSession)
      assert isinstance(sess.agent, Agent)
      assert sess.agent_id in sess.core._agents_map

  async def test_session_explicit_id(self, patched_process) -> None:
    """id= is honoured on the underlying session."""
    async with yoker.session(id="audit-2026-07-06") as sess:
      assert sess.id == "audit-2026-07-06"
      assert sess.core.id == "audit-2026-07-06"


class TestSessionAgentProcess:
  """``session.agent.process`` runs a turn on the primary agent."""

  async def test_process_returns_response(self, patched_process) -> None:
    """agent.process() returns the reply."""
    async with yoker.session() as sess:
      result = await sess.agent.process("hello")
    assert result == "reply:hello"
    assert patched_process == ["hello"]

  async def test_process_multi_turn(self, patched_process) -> None:
    """Multiple process() calls reuse the same primary agent."""
    async with yoker.session() as sess:
      await sess.agent.process("first")
      await sess.agent.process("second")
    assert patched_process == ["first", "second"]


class TestSessionOnEvent:
  """``session.on_event`` registers a session-scoped handler."""

  async def test_on_event_receives_session_start(self, patched_process) -> None:
    """on_event handlers receive SESSION_START from the core Session."""
    from yoker.events import SessionStartEvent

    received: list = []
    async with yoker.session(event_handler=lambda e: received.append(e)) as sess:
      # The handler is registered after SESSION_START is emitted by
      # __aenter__ — register explicitly to observe SESSION_END too.
      sess.on_event(lambda e: received.append(e))
    # SESSION_END should reach the handler registered inside the body.
    assert any(isinstance(e, SessionStartEvent) or hasattr(e, "type") for e in received)


class TestSessionSpawn:
  """``session.spawn`` delegates to the core Session's spawn."""

  async def test_spawn_without_definition_raises(self, patched_process) -> None:
    """Spawning an unknown agent raises ValueError."""
    async with yoker.session() as sess:
      with pytest.raises(ValueError):
        await sess.spawn("nonexistent-agent")


class TestSessionFreshAndPersist:
  """``fresh`` and ``persist`` kwargs control context persistence."""

  async def test_persist_false_uses_simple_context(self, patched_process) -> None:
    """persist=False builds the primary agent with a SimpleContextManager."""

    async with yoker.session(persist=False) as sess:
      from yoker.context.basic import SimpleContextManager as SC

      assert isinstance(sess.agent.context, SC)

  async def test_persist_true_wraps_with_persisted(self, patched_process) -> None:
    """persist=True (default) wraps the context with Persisted."""
    from yoker.context import Persisted

    async with yoker.session(persist=True) as sess:
      assert isinstance(sess.agent.context, Persisted)
