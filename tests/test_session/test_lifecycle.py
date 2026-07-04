"""Tests for Session lifecycle — async context manager, cleanup, handler edge cases.

MBI-007 7.9.1. Extends ``test_session.py`` with cleanup-on-exception,
handler exception isolation, registry population edge paths, and
``register_primary_agent`` behaviour.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config
from yoker.events import SessionEndEvent
from yoker.session import Session


class TestSessionExceptionExit:
  """Tests for __aexit__ when the body raises."""

  @pytest.mark.asyncio
  async def test_session_end_emitted_on_exception_exit(self) -> None:
    """SESSION_END is emitted even when the body raises."""
    session = Session(config=Config())
    received: list = []
    session.add_event_handler(lambda e: received.append(e))
    with pytest.raises(RuntimeError, match="boom"):
      async with session:
        raise RuntimeError("boom")
    end_events = [e for e in received if isinstance(e, SessionEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].session_id == session.id

  @pytest.mark.asyncio
  async def test_outstanding_tasks_cancelled_on_exception_exit(self) -> None:
    """Outstanding tasks are cancelled even when the body raises."""
    session = Session(config=Config())

    async def long_running() -> None:
      await asyncio.sleep(10)

    task: asyncio.Task | None = None
    with pytest.raises(ValueError):
      async with session:
        task = asyncio.ensure_future(long_running())
        session._tasks.add(task)
        raise ValueError("boom")
    assert task is not None
    assert task.cancelled() or task.done()
    # _tasks is cleared after __aexit__.
    assert session._tasks == set()


class TestSessionEventHandlerEdgeCases:
  """Tests for handler fan-out edge cases (lines 163-164 of session.py)."""

  @pytest.mark.asyncio
  async def test_failing_sync_handler_does_not_break_others(self) -> None:
    """A sync handler that raises is logged and does not stop other handlers."""
    session = Session(config=Config())
    received: list = []

    def bad_handler(_event) -> None:
      raise RuntimeError("handler exploded")

    def good_handler(event) -> None:
      received.append(event)

    session.add_event_handler(bad_handler)
    session.add_event_handler(good_handler)
    async with session:
      pass
    # The good handler still received SESSION_START and SESSION_END.
    types = [type(e).__name__ for e in received]
    assert "SessionStartEvent" in types
    assert "SessionEndEvent" in types

  @pytest.mark.asyncio
  async def test_failing_async_handler_is_awaited_safely(self) -> None:
    """An async handler that raises is scheduled and discarded on failure.

    The Session's ``_emit`` catches sync handler exceptions inline. Async
    handlers are scheduled as fire-and-forget tasks; their exceptions are
    logged by the event loop's ``Task exception was never retrieved`` path
    but never propagated to the caller. This test verifies the
    fire-and-forget contract: a failing async handler does not break the
    Session lifecycle.
    """
    session = Session(config=Config())

    async def bad_async(_event) -> None:
      raise RuntimeError("async handler exploded")

    session.add_event_handler(bad_async)
    # Should not raise out of __aenter__ — the handler exception is logged
    # by the Session's _emit, not propagated.
    async with session:
      await asyncio.sleep(0)  # yield control so the scheduled task runs.
    # The SESSION_START-task done callback discards it once it completes;
    # the SESSION_END-task may still be pending (the Session does not await
    # fire-and-forget tasks scheduled by SESSION_END). The contract being
    # tested here is "no propagation", not "all tasks completed".


class TestSessionRegistryPopulationEdge:
  """Tests for _load_agents error handling (lines 181-182)."""

  def test_load_agents_warns_on_invalid_directory(self, tmp_path) -> None:
    """A non-existent directory is warned about, not raised."""
    from dataclasses import replace

    from yoker.config import AgentsConfig

    bogus = tmp_path / "does-not-exist"
    config = Config()
    config = replace(config, agents=AgentsConfig(directories=(str(bogus),)))
    # Should not raise; the warning is logged.
    session = Session(config=config)
    assert session.agents is not None
    # Registry is empty because the directory didn't exist.
    assert list(session.agents.names) == []

  def test_load_agents_warns_on_malformed_definition(self, tmp_path) -> None:
    """A malformed agent definition file is warned about, not raised."""
    from dataclasses import replace

    from yoker.config import AgentsConfig

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "bad.md").write_text("not valid markdown:\n  - missing frontmatter")
    config = Config()
    config = replace(config, agents=AgentsConfig(directories=(str(agents_dir),)))
    session = Session(config=config)
    # No agents loaded; the bad file was warned about.
    assert "agents:bad" not in session.agents.names


class TestRegisterPrimaryAgent:
  """Tests for Session.register_primary_agent (7.8.5)."""

  def test_register_primary_agent_assigns_id_and_injects_tools(self) -> None:
    """register_primary_agent assigns a runtime id and injects agent/send_message."""
    config = Config()
    session = Session(config=config)
    fake_agent = MagicMock()
    fake_agent.definition = AgentDefinition(
      simple_name="primary",
      description="Primary",
      tools=("read",),
    )
    fake_agent.tools = MagicMock()
    agent_id = session.register_primary_agent(fake_agent)
    assert agent_id == "primary"
    assert session.get_agent("primary") is fake_agent
    assert session._recursion_depths["primary"] == 0
    # The ``agent`` tool (gated by config.tools.agent.enabled, default True)
    # and ``send_message`` are both injected by the Session.
    registered_names = [
      call.kwargs.get("name") for call in fake_agent.tools.register.call_args_list
    ]
    assert "agent" in registered_names
    assert "send_message" in registered_names

  def test_register_primary_agent_skips_spawnagent_when_disabled(self) -> None:
    """The ``agent`` tool is NOT injected when config.tools.agent.enabled is False."""
    from dataclasses import replace

    from yoker.config import AgentToolConfig

    config = Config()
    config = replace(config, tools=replace(config.tools, agent=AgentToolConfig(enabled=False)))
    session = Session(config=config)
    fake_agent = MagicMock()
    fake_agent.definition = AgentDefinition(
      simple_name="primary",
      description="Primary",
      tools=("read",),
    )
    fake_agent.tools = MagicMock()
    session.register_primary_agent(fake_agent)
    registered_names = [
      call.kwargs.get("name") for call in fake_agent.tools.register.call_args_list
    ]
    assert "agent" not in registered_names
    # send_message is always injected when an agent is part of a session.
    assert "send_message" in registered_names

  def test_register_primary_agent_disambiguates(self) -> None:
    """A second primary-agent registration with the same name gets a -2 suffix."""
    session = Session(config=Config())
    a = MagicMock()
    a.definition = AgentDefinition(simple_name="primary", description="Primary", tools=("read",))
    a.tools = MagicMock()
    b = MagicMock()
    b.definition = AgentDefinition(simple_name="primary", description="Primary", tools=("read",))
    b.tools = MagicMock()
    first = session.register_primary_agent(a)
    second = session.register_primary_agent(b)
    assert first == "primary"
    assert second == "primary-2"
