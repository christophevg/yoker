"""Tests for the agent subagent tool implementation (MBI-007 Phase 2).

Phase 2 changes (PR #43 Clarifications 1 & 2):
  - ``Agent`` no longer holds ``agents`` / ``recursion_depth`` /
    ``max_recursion_depth`` — the :class:`yoker.session.Session` owns them.
  - ``make_agent_tool`` is no longer registered by ``Agent.__init__``; it
    delegates to ``session.spawn(...)`` when a session is available on the
    parent agent. The full ``SpawnAgent`` rewrite lands in Phase 4 (7.8.3).

These tests verify the transitional delegation behaviour: the tool captures
the parent agent's ``_session``, calls ``session.spawn`` with ``requester``
set, and wraps the response / errors into ``ToolResult``. The deep behaviour
(allowlist, depth, timeout, max_agents) is covered by
``tests/test_session/test_spawn.py``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.agents import AgentDefinition
from yoker.builtin import make_agent_tool
from yoker.builtin.agent import DEFAULT_TIMEOUT_SECONDS, _clamp
from yoker.tools import ToolRegistry


def _agent_spec(parent_agent=None):
  """Create and register the agent tool."""
  registry = ToolRegistry()
  return registry.register(make_agent_tool(parent_agent=parent_agent))


def _make_session_with_registry(agent_def=None, resolve_error=None):
  """Build a mock Session with an AgentRegistry-like agents attribute."""
  session = MagicMock()
  session.agents = MagicMock()
  session.agents.names = [agent_def.simple_name] if agent_def else []
  if resolve_error is not None:
    session.agents.resolve.side_effect = resolve_error
  elif agent_def is not None:
    session.agents.resolve.return_value = agent_def
  return session


def _make_parent_agent(session=None, definition=None):
  """Build a mock parent agent with a _session reference."""
  agent = MagicMock()
  agent._session = session
  agent.definition = definition or AgentDefinition(
    simple_name="parent",
    description="Parent agent",
    tools=("read",),
    agents=("researcher",),
  )
  return agent


class TestAgentToolSchema:
  """Tests for agent tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    spec = _agent_spec()
    assert spec.name == "agent"

  def test_description(self) -> None:
    """Test tool description."""
    spec = _agent_spec()
    assert "sub-agent" in spec.description.lower()
    assert "task" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    spec = _agent_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "agent"
    assert "agent_name" in schema["function"]["parameters"]["properties"]
    assert "prompt" in schema["function"]["parameters"]["properties"]
    assert "timeout_seconds" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["agent_name", "prompt"]

  def test_timeout_in_schema(self) -> None:
    """Test that timeout_seconds parameter is present with integer type."""
    spec = _agent_spec()
    schema = spec.schema

    timeout_prop = schema["function"]["parameters"]["properties"]["timeout_seconds"]
    assert timeout_prop["type"] == "integer"


class TestAgentToolParameters:
  """Tests for parameter validation."""

  @pytest.mark.asyncio
  async def test_missing_agent_name(self) -> None:
    """Test error when agent_name is missing."""
    spec = _agent_spec()
    result = await spec.execute(agent_name="", prompt="Test prompt")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "agent_name" in result.error

  @pytest.mark.asyncio
  async def test_missing_prompt(self) -> None:
    """Test error when prompt is missing."""
    parent = _make_parent_agent(session=_make_session_with_registry())
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(agent_name="researcher", prompt="")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "prompt" in result.error

  @pytest.mark.asyncio
  async def test_invalid_timeout_string(self) -> None:
    """Test error for invalid timeout_seconds parameter."""
    spec = _agent_spec()
    result = await spec.execute(
      agent_name="test-agent",
      prompt="Test",
      timeout_seconds="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric parameter" in result.error


class TestAgentToolDelegation:
  """Tests that make_agent_tool delegates to session.spawn (Phase 2)."""

  @pytest.mark.asyncio
  async def test_no_session_returns_error(self) -> None:
    """Without a session the tool reports no session available."""
    parent = _make_parent_agent(session=None)
    spec = _agent_spec(parent_agent=parent)

    result = await spec.execute(agent_name="x", prompt="hi")

    assert not result.success
    assert "No session" in result.error

  @pytest.mark.asyncio
  async def test_delegates_to_session_spawn(self) -> None:
    """Successful spawn returns ToolResult(success=True) with the response."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    session.spawn = AsyncMock(return_value="researcher response")
    parent = _make_parent_agent(session=session)

    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(agent_name="researcher", prompt="find X")

    assert result.success
    assert result.result == "researcher response"
    session.spawn.assert_awaited_once()
    call_kwargs = session.spawn.call_args.kwargs
    assert call_kwargs["requester"] is parent

  @pytest.mark.asyncio
  async def test_value_error_wrapped_as_failure(self) -> None:
    """ValueError from session.spawn (allowlist/depth/capacity) is wrapped."""
    session = _make_session_with_registry(resolve_error=ValueError("Agent not found: ghost"))
    session.spawn = AsyncMock(side_effect=ValueError("not allowed"))
    session.agents.names = []
    parent = _make_parent_agent(session=session)

    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(agent_name="ghost", prompt="hi")

    assert not result.success
    assert "not allowed" in result.error

  @pytest.mark.asyncio
  async def test_timeout_error_wrapped_as_failure(self) -> None:
    """TimeoutError from session.spawn is wrapped, not re-raised."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    session.spawn = AsyncMock(side_effect=TimeoutError("timed out after 1s"))
    parent = _make_parent_agent(session=session)

    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(agent_name="researcher", prompt="hi", timeout_seconds=1)

    assert not result.success
    assert "timed out" in result.error.lower()

  @pytest.mark.asyncio
  async def test_generic_exception_wrapped_as_failure(self) -> None:
    """Unexpected exceptions are wrapped, not re-raised."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    session.spawn = AsyncMock(side_effect=RuntimeError("boom"))
    parent = _make_parent_agent(session=session)

    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(agent_name="researcher", prompt="hi")

    assert not result.success
    assert "Sub-agent error" in result.error

  @pytest.mark.asyncio
  async def test_default_timeout_passed_to_spawn(self) -> None:
    """Default timeout is forwarded when not specified."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    session.spawn = AsyncMock(return_value="ok")
    parent = _make_parent_agent(session=session)

    spec = _agent_spec(parent_agent=parent)
    await spec.execute(agent_name="researcher", prompt="hi")

    call_kwargs = session.spawn.call_args.kwargs
    assert call_kwargs["timeout_seconds"] == DEFAULT_TIMEOUT_SECONDS


class TestAgentToolClamp:
  """Tests for the _clamp helper function (retained in Phase 2)."""

  def test_clamp_within_range(self) -> None:
    """Test clamping value within range."""
    assert _clamp(50, 0, 100) == 50

  def test_clamp_at_minimum(self) -> None:
    """Test clamping value at minimum."""
    assert _clamp(0, 0, 100) == 0

  def test_clamp_at_maximum(self) -> None:
    """Test clamping value at maximum."""
    assert _clamp(100, 0, 100) == 100

  def test_clamp_below_minimum(self) -> None:
    """Test clamping value below minimum."""
    assert _clamp(-10, 0, 100) == 0

  def test_clamp_above_maximum(self) -> None:
    """Test clamping value above maximum."""
    assert _clamp(150, 0, 100) == 100
