"""Tests for Session lifecycle — async context manager, cleanup, handler edge cases.

Extends ``test_session.py`` with cleanup-on-exception, handler exception
isolation, registry population edge paths, and ``register_primary_agent``
behaviour. Also covers the least-privilege gating of the session-injected
``agent``/``send_message``/``release_agent`` tools by the definition's
``tools:`` grants.
"""

import asyncio
import importlib
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agents import AgentDefinition
from yoker.config import AgentToolConfig, Config
from yoker.core import Agent
from yoker.events import SessionEndEvent
from yoker.session import Session
from yoker.tools import ToolRegistry

# Explicit reference to the real yoker.session module — the package-level
# `session` FUNCTION re-export (yoker.api) shadows the submodule attribute
# on Python 3.10, so patching "yoker.session.Agent" fails there.
session_module = importlib.import_module("yoker.session")


class TestSessionExceptionExit:
  """Tests for __aexit__ when the body raises."""

  @pytest.mark.asyncio
  async def test_session_end_emitted_on_exception_exit(self) -> None:
    """SESSION_END is emitted even when the body raises."""
    session = Session(config=Config())
    received: list = []
    session.on_event(lambda e: received.append(e))
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

    session.on_event(bad_handler)
    session.on_event(good_handler)
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

    session.on_event(bad_async)
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
  """Tests for the primary-agent path through ``_create_agent`` (requester=None).

  ``Session.__init__`` constructs the primary agent via the unified
  :meth:`Session._create_agent` flow with ``requester=None``. These tests
  exercise that path directly (and via ``Session.__init__``) to verify
  agent-id assignment, tool injection, and disambiguation.
  """

  def test_primary_path_assigns_id_and_injects_tools(self) -> None:
    """_create_agent(requester=None) registers the agent and injects tools."""
    config = Config()
    session = Session(config=config)
    # The primary agent is constructed in __init__ and available as
    # session.agent. It is registered in the active map under a runtime id
    # and has the ``agent`` and ``send_message`` tools injected.
    primary = session.agent
    assert primary is not None
    # Reverse-lookup resolves the primary back to its id.
    primary_id = session._id_of(primary)
    assert primary_id == "primary"
    assert session.get_agent("primary") is primary
    # Both session-injected tools are present on the primary.
    assert "yoker:agent" in primary.tools.names
    assert "yoker:send_message" in primary.tools.names

  def test_primary_path_skips_spawnagent_when_disabled(self) -> None:
    """The ``agent`` tool is NOT injected when config.tools.agent.enabled is False."""
    from dataclasses import replace

    from yoker.config import AgentToolConfig

    config = Config()
    config = replace(config, tools=replace(config.tools, agent=AgentToolConfig(enabled=False)))
    session = Session(config=config)
    primary = session.agent
    assert "yoker:agent" not in primary.tools.names
    # send_message is always injected when an agent is part of a session.
    assert "yoker:send_message" in primary.tools.names

  def test_create_agent_disambiguates_primary_names(self) -> None:
    """A second _create_agent call with the same definition name gets a -2 suffix."""
    config = Config()
    session = Session(config=config)
    # __init__ already registered the primary as "primary"; a second
    # _create_agent call with the same default definition gets disambiguated.
    first, first_id = session._create_agent(requester=None, config=config)
    assert first_id == "primary-2"
    second, second_id = session._create_agent(requester=None, config=config)
    assert second_id == "primary-3"
    assert session.get_agent("primary-2") is first
    assert session.get_agent("primary-3") is second


SESSION_TOOLS = ("yoker:agent", "yoker:send_message", "yoker:release_agent")


class TestSessionToolsRespectToolGrants:
  """Session-injected tools honour the definition's ``tools:`` grants.

  ``Session.inject_tools`` registers ``agent``/``send_message``/
  ``release_agent`` AFTER ``Agent.__init__`` has filtered the registry, so
  historically every session agent received them regardless of grants. The
  fix re-applies the definition filter post-injection. Grant semantics:

  - No ``tools:`` line (ALL_TOOLS sentinel) → session tools granted
    (backward compatible with the default primary).
  - Explicit ``tools:`` containing the session tool names → granted.
  - Explicit ``tools:`` without them → NOT granted (the least-privilege fix).
  - Explicit ``tools: []`` → no tools at all, session tools included.

  ``config.tools.agent.enabled=False`` still wins for ``agent``/
  ``release_agent`` (global kill-switch, existing behaviour).
  """

  def _spawned(self, session: Session, defn: AgentDefinition) -> Agent:
    """Spawn a mock-backed child built from ``defn`` (definition reused).

    Uses the sync ``_create_agent`` path (same flow ``_spawn_internal``
    delegates to) so the tests stay synchronous. ``tools`` is a real
    ``ToolRegistry`` because ``inject_tools`` registers into it and the
    assertions inspect ``tools.names``; the other attributes the Session
    touches stay mocked.
    """
    session.agents.register(defn)
    with patch.object(session_module, "Agent") as mock_agent_cls:
      mock_child = MagicMock(spec=Agent)
      type(mock_child).tools = ToolRegistry()
      type(mock_child).definition = defn
      mock_child.process = AsyncMock(return_value="ok")
      mock_child.aclose = AsyncMock()
      mock_child.on_event = MagicMock()
      mock_agent_cls.return_value = mock_child
      child, _agent_id = session._create_agent(name=defn.name, agent_definition=defn)
    return child

  def _primary(self, defn: AgentDefinition) -> Session:
    """Build a Session whose primary agent uses ``defn``."""
    return Session(config=Config(), agent_definition=defn)

  # -- no tools: line → session tools granted (ALL_TOOLS backward compat) --

  def test_all_tools_default_keeps_session_tools(self) -> None:
    """A definition without tools: (ALL_TOOLS) keeps all session tools."""
    defn = AgentDefinition(simple_name="orchestrator", description="d")
    session = self._primary(defn)
    for tool in SESSION_TOOLS:
      assert tool in session.agent.tools.names, f"missing {tool} on ALL_TOOLS primary"

  # -- explicit grants → session tools granted --

  def test_explicit_grants_get_session_tools(self) -> None:
    """A definition granting the three names receives all three tools."""
    defn = AgentDefinition(
      simple_name="orchestrator",
      description="d",
      tools=("read", "agent", "send_message", "release_agent"),
    )
    session = self._primary(defn)
    for tool in SESSION_TOOLS:
      assert tool in session.agent.tools.names, f"missing {tool} despite explicit grant"

  def test_explicit_grants_get_session_tools_on_spawned(self) -> None:
    """Same grant semantics on the spawned (requester) path."""
    defn = AgentDefinition(
      simple_name="orchestrator",
      description="d",
      tools=("read", "agent", "send_message", "release_agent"),
    )
    session = Session(config=Config())
    child = self._spawned(session, defn)
    for tool in SESSION_TOOLS:
      assert tool in child.tools.names, f"missing {tool} despite explicit grant"

  # -- no grants → session tools stripped (the least-privilege fix) --

  def test_ungranted_session_tools_stripped(self) -> None:
    """A definition without the grants must NOT see the session tools."""
    defn = AgentDefinition(
      simple_name="worker",
      description="d",
      tools=("read", "list"),
    )
    session = self._primary(defn)
    for tool in SESSION_TOOLS:
      assert tool not in session.agent.tools.names, f"{tool} leaked past tools: filter"

  def test_ungranted_session_tools_stripped_on_spawned(self) -> None:
    """A spawned worker without the grants must NOT see the session tools."""
    defn = AgentDefinition(
      simple_name="worker",
      description="d",
      tools=("read", "list"),
    )
    session = Session(config=Config())
    child = self._spawned(session, defn)
    for tool in SESSION_TOOLS:
      assert tool not in child.tools.names, f"{tool} leaked past tools: filter"

  def test_granted_only_send_message(self) -> None:
    """Partial grants: only the granted session tools survive."""
    defn = AgentDefinition(
      simple_name="messenger",
      description="d",
      tools=("read", "send_message"),
    )
    session = self._primary(defn)
    assert "yoker:send_message" in session.agent.tools.names
    assert "yoker:agent" not in session.agent.tools.names
    assert "yoker:release_agent" not in session.agent.tools.names

  def test_explicit_empty_tools_clears_session_tools(self) -> None:
    """tools: [] agents get nothing — session tools included."""
    defn = AgentDefinition(simple_name="silent", description="d", tools=[])
    session = self._primary(defn)
    for tool in SESSION_TOOLS:
      assert tool not in session.agent.tools.names, f"{tool} leaked past tools: []"

  # -- global kill-switch still applies --

  def test_spawn_tool_kill_switch_still_applies(self) -> None:
    """config.tools.agent.enabled=False still removes agent/release_agent.

    Even when the definition explicitly grants them, the global kill-switch
    wins (existing inject_tools behaviour, unchanged).
    """
    config = Config()
    config = replace(config, tools=replace(config.tools, agent=AgentToolConfig(enabled=False)))
    defn = AgentDefinition(
      simple_name="orchestrator",
      description="d",
      tools=("agent", "send_message", "release_agent"),
    )
    session = Session(config=config, agent_definition=defn)
    assert "yoker:agent" not in session.agent.tools.names
    assert "yoker:release_agent" not in session.agent.tools.names
    # send_message has no kill-switch and was explicitly granted.
    assert "yoker:send_message" in session.agent.tools.names

  # -- loader namespacing of the session tool names --

  def test_bare_release_agent_resolves_to_yoker_namespace(self) -> None:
    """Bare 'release_agent' in frontmatter namespaceres to yoker:release_agent.

    ``release_agent`` was missing from ``_SESSION_INJECTED_TOOLS``, so bare
    frontmatter grants were namespaced to the collection namespace
    (e.g. ``c3:release_agent``) and never resolved to the injected tool.
    """
    from yoker.agents.loader import _namespace_tools

    assert _namespace_tools(["agent", "send_message", "release_agent"], "c3") == [
      "yoker:agent",
      "yoker:send_message",
      "yoker:release_agent",
    ]

  # -- twice-spawned ALL_TOOLS definition stays consistent --

  def test_all_tools_definition_consistent_across_spawns(self) -> None:
    """A shared ALL_TOOLS definition spawns consistently (no marker drift).

    ``AgentDefinition`` is shared between spawns via the registry; the
    default-granted decision must be captured per agent construction, not
    inferred from the (mutated) definition state.
    """
    defn = AgentDefinition(simple_name="researcher", description="d")
    session = Session(config=Config())
    first = self._spawned(session, defn)
    with patch.object(session_module, "Agent") as mock_agent_cls:
      mock_child = MagicMock(spec=Agent)
      type(mock_child).tools = ToolRegistry()
      type(mock_child).definition = defn
      mock_child.aclose = AsyncMock()
      mock_child.on_event = MagicMock()
      mock_agent_cls.return_value = mock_child
      second, _agent_id = session._create_agent(name=defn.name, agent_definition=defn)
    for tool in SESSION_TOOLS:
      assert tool in first.tools.names
      assert tool in second.tools.names
