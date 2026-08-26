"""Tests for the UI-layer /session command."""

from unittest.mock import MagicMock

import pytest

from yoker.agents import AgentDefinition
from yoker.context import ContextStatistics
from yoker.core import Agent
from yoker.ui import BatchUIHandler
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.session import DESCRIPTION, handle


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


def _make_agent(simple_name="primary", model=None, agents=()):
  """Create a mock agent with definition and context."""
  agent = MagicMock(spec=Agent)
  agent.definition = AgentDefinition(
    simple_name=simple_name,
    description=f"{simple_name} agent",
    tools=("read", "agent"),
    agents=tuple(agents) if agents else (),
    model=model,
  )
  agent.model = model
  agent.context = MagicMock()
  agent.context.get_statistics.return_value = ContextStatistics(message_count=3, turn_count=1)
  agent.tools = MagicMock()
  agent.tools.__len__ = lambda self: 5
  agent.skills = MagicMock()
  agent.skills.__len__ = lambda self: 0
  return agent


def _make_session(primary_agent, agents_map=None, max_agents=10):
  """Create a mock session with an agents map."""
  session = MagicMock()
  session.id = "test-session-123"
  session.agent = primary_agent
  if agents_map is None:
    agents_map = {primary_agent.definition.simple_name: primary_agent}
  session._agents_map = agents_map
  session.config.session.max_agents = max_agents
  return session


class TestSessionCommand:
  """Tests for /session command in the UI layer."""

  @pytest.mark.asyncio
  async def test_no_session_returns_standalone_message(self):
    """/session without a session returns a standalone message."""
    agent = _make_agent()
    agent._session = None
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "No active session" in result

  @pytest.mark.asyncio
  async def test_shows_session_id(self):
    """/session should show the session ID."""
    agent = _make_agent()
    session = _make_session(agent)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Session" in result
    assert "test-session-123" in result

  @pytest.mark.asyncio
  async def test_shows_agent_count(self):
    """/session should show active agent count and max."""
    agent = _make_agent()
    session = _make_session(agent, max_agents=10)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Active agents: 1 / 10" in result

  @pytest.mark.asyncio
  async def test_shows_primary_agent(self):
    """/session should mark the primary agent with a star."""
    agent = _make_agent(simple_name="coordinator", model="llama3:8b")
    session = _make_session(agent)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "★" in result
    assert "primary" in result
    assert "coordinator" in result
    assert "llama3:8b" in result

  @pytest.mark.asyncio
  async def test_shows_spawned_agent(self):
    """/session should show spawned agents with a bullet marker."""
    primary = _make_agent(simple_name="coordinator")
    spawned = _make_agent(simple_name="researcher", model="qwen2:7b")
    agents_map = {"coordinator": primary, "researcher": spawned}
    session = _make_session(primary, agents_map=agents_map)
    primary._session = session
    ui = MockUI()

    result = await handle("", primary, ui)

    assert "●" in result
    assert "spawned" in result
    assert "researcher" in result
    assert "qwen2:7b" in result

  @pytest.mark.asyncio
  async def test_shows_message_count_and_turns(self):
    """/session should show context statistics per agent."""
    agent = _make_agent()
    session = _make_session(agent)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Messages: 3" in result
    assert "Turns: 1" in result

  @pytest.mark.asyncio
  async def test_shows_tools_count(self):
    """/session should show tool count per agent."""
    agent = _make_agent()
    session = _make_session(agent)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Tools: 5" in result

  @pytest.mark.asyncio
  async def test_shows_can_spawn_list(self):
    """/session should show allowed spawns for agents with spawn permissions."""
    primary = _make_agent(simple_name="pm", agents=("researcher", "python-developer"))
    session = _make_session(primary)
    primary._session = session
    ui = MockUI()

    result = await handle("", primary, ui)

    assert "Can spawn:" in result
    assert "researcher" in result
    assert "python-developer" in result

  @pytest.mark.asyncio
  async def test_warning_when_capacity_reached(self):
    """/session should show a warning when capacity is reached."""
    agent = _make_agent()
    session = _make_session(agent, max_agents=1)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "capacity reached" in result.lower()

  @pytest.mark.asyncio
  async def test_no_warning_when_under_capacity(self):
    """/session should not show a warning when under capacity."""
    agent = _make_agent()
    session = _make_session(agent, max_agents=10)
    agent._session = session
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "capacity reached" not in result.lower()

  @pytest.mark.asyncio
  async def test_registered_in_default_registry(self):
    """/session should be dispatchable from the default registry."""
    registry = create_default_registry()
    agent = _make_agent()
    session = _make_session(agent)
    agent._session = session
    ui = MockUI()

    result = await registry.dispatch("/session", agent, ui)

    assert "Session" in result
    assert "test-session-123" in result

  def test_description(self):
    """The /session command should describe itself."""
    assert "session" in DESCRIPTION.lower()
