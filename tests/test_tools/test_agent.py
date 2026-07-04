"""Tests for the Session-injected ``agent`` and ``send_message`` tools (MBI-007 Phase 4).

PR #43 Clarifications 2, 4 & 5:
  - The ``agent`` tool is Session-injected (closure capture of the Session
    back-reference).
  - The ``send_message`` tool enables inter-agent messaging via tool calls.
  - ``agent`` returns both the spawned agent's unique id and its
    response string (PR #43 Clarification 5).

These tests verify the tool factories in :mod:`yoker.session.tools`:
schema, parameter validation, delegation to ``session.spawn`` /
``session.send``, and error wrapping. Deep behaviour (allowlist, depth,
timeout, max_agents) is covered by ``tests/test_session/test_spawn.py``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.agents import AgentDefinition
from yoker.session.message import Message
from yoker.session.spawn_result import SpawnResult
from yoker.session.tools import (
  DEFAULT_TIMEOUT_SECONDS,
  make_send_message_tool,
  make_spawn_agent_tool,
)
from yoker.tools import ToolRegistry


def _spawn_agent_spec(session=None, requester=None):
  """Create and register the ``agent`` tool."""
  registry = ToolRegistry()
  if session is None:
    session = MagicMock()
    session.agents = MagicMock()
    session.agents.names = []
  if requester is None:
    requester = MagicMock()
    requester.definition = AgentDefinition(
      simple_name="parent",
      description="Parent agent",
      tools=("read",),
      agents=("researcher",),
    )
  return registry.register(
    make_spawn_agent_tool(session, requester),
    namespace="yoker",
    name="agent",
  )


def _send_message_spec(session=None, from_id="parent"):
  """Create and register the ``send_message`` tool."""
  registry = ToolRegistry()
  if session is None:
    session = MagicMock()
  return registry.register(
    make_send_message_tool(session, from_id),
    namespace="yoker",
    name="send_message",
  )


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


def _make_requester(allowlist=("researcher",)):
  """Build a mock requester agent with a definition allowlist."""
  agent = MagicMock()
  agent.definition = AgentDefinition(
    simple_name="parent",
    description="Parent agent",
    tools=("read",),
    agents=tuple(allowlist),
  )
  return agent


class TestAgentToolSchema:
  """Tests for the ``agent`` tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name is agent."""
    spec = _spawn_agent_spec()
    assert spec.name == "yoker:agent"

  def test_description(self) -> None:
    """Test tool description mentions sub-agent / task."""
    spec = _spawn_agent_spec()
    assert "sub-agent" in spec.description.lower()
    assert "task" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    spec = _spawn_agent_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "yoker__agent"
    assert "agent_name" in schema["function"]["parameters"]["properties"]
    assert "prompt" in schema["function"]["parameters"]["properties"]
    assert "timeout_seconds" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["agent_name", "prompt"]

  def test_timeout_in_schema(self) -> None:
    """Test that timeout_seconds parameter is present with integer type."""
    spec = _spawn_agent_spec()
    schema = spec.schema

    timeout_prop = schema["function"]["parameters"]["properties"]["timeout_seconds"]
    assert timeout_prop["type"] == "integer"


class TestAgentToolParameters:
  """Tests for parameter validation."""

  @pytest.mark.asyncio
  async def test_missing_agent_name(self) -> None:
    """Test error when agent_name is missing."""
    spec = _spawn_agent_spec()
    result = await spec.execute(agent_name="", prompt="Test prompt")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "agent_name" in result.error

  @pytest.mark.asyncio
  async def test_missing_prompt(self) -> None:
    """Test error when prompt is missing."""
    spec = _spawn_agent_spec()
    result = await spec.execute(agent_name="researcher", prompt="")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "prompt" in result.error

  @pytest.mark.asyncio
  async def test_invalid_timeout_string(self) -> None:
    """Test error for invalid timeout_seconds parameter."""
    spec = _spawn_agent_spec()
    result = await spec.execute(
      agent_name="test-agent",
      prompt="Test",
      timeout_seconds="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric parameter" in result.error


class TestAgentToolDelegation:
  """Tests that the ``agent`` tool delegates to session.spawn (Phase 4)."""

  @pytest.mark.asyncio
  async def test_delegates_to_session_spawn(self) -> None:
    """Successful spawn returns ToolResult with agent_id and response."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    session.spawn = AsyncMock(
      return_value=SpawnResult(agent_id="researcher", response="researcher response")
    )
    requester = _make_requester(allowlist=("researcher",))

    spec = _spawn_agent_spec(session=session, requester=requester)
    result = await spec.execute(agent_name="researcher", prompt="find X")

    assert result.success
    assert "researcher" in result.result
    assert "researcher response" in result.result
    assert "agent_id:" in result.result
    session.spawn.assert_awaited_once()
    call_kwargs = session.spawn.call_args.kwargs
    assert call_kwargs["requester"] is requester

  @pytest.mark.asyncio
  async def test_value_error_wrapped_as_failure(self) -> None:
    """ValueError from session.spawn (allowlist/depth/capacity) is wrapped."""
    session = _make_session_with_registry(resolve_error=ValueError("Agent not found: ghost"))
    session.spawn = AsyncMock(side_effect=ValueError("not allowed"))
    requester = _make_requester(allowlist=("researcher",))

    spec = _spawn_agent_spec(session=session, requester=requester)
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
    requester = _make_requester(allowlist=("researcher",))

    spec = _spawn_agent_spec(session=session, requester=requester)
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
    requester = _make_requester(allowlist=("researcher",))

    spec = _spawn_agent_spec(session=session, requester=requester)
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
    session.spawn = AsyncMock(return_value=SpawnResult(agent_id="researcher", response="ok"))
    requester = _make_requester(allowlist=("researcher",))

    spec = _spawn_agent_spec(session=session, requester=requester)
    await spec.execute(agent_name="researcher", prompt="hi")

    call_kwargs = session.spawn.call_args.kwargs
    assert call_kwargs["timeout_seconds"] == DEFAULT_TIMEOUT_SECONDS

  @pytest.mark.asyncio
  async def test_result_contains_agent_id(self) -> None:
    """PR #43 Clarification 5: result contains the spawned agent's id."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    session.spawn = AsyncMock(
      return_value=SpawnResult(agent_id="researcher-2", response="found it")
    )
    requester = _make_requester(allowlist=("researcher",))

    spec = _spawn_agent_spec(session=session, requester=requester)
    result = await spec.execute(agent_name="researcher", prompt="find X")

    assert result.success
    assert "researcher-2" in result.result
    assert "found it" in result.result


class TestAgentToolDescription:
  """Tests for the tool description baking (allowlist intersection)."""

  def test_description_lists_allowlisted_names(self) -> None:
    """Parameter description includes agent names from the requester's allowlist."""
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    session = _make_session_with_registry(agent_def=agent_def)
    requester = _make_requester(allowlist=("researcher", "writer"))

    spec = _spawn_agent_spec(session=session, requester=requester)
    # Available names are baked into the agent_name parameter description.
    agent_name_prop = spec.schema["function"]["parameters"]["properties"]["agent_name"]
    assert "researcher" in agent_name_prop["description"]
    # "writer" is in the allowlist but not in the registry. The implementation
    # intersects the allowlist with the registry, so "writer" is NOT shown.
    # (The allowlist is the authoritative gate; the registry determines which
    # are actually available to spawn.)
    assert "writer" not in agent_name_prop["description"]

  def test_description_falls_back_to_allowlist_when_registry_empty(self) -> None:
    """When the registry is empty, the full allowlist is shown."""
    session = MagicMock()
    session.agents = MagicMock()
    session.agents.names = []
    requester = _make_requester(allowlist=("researcher", "writer"))

    spec = _spawn_agent_spec(session=session, requester=requester)
    agent_name_prop = spec.schema["function"]["parameters"]["properties"]["agent_name"]
    # When the registry is empty, the fallback uses the full allowlist.
    assert "researcher" in agent_name_prop["description"]
    assert "writer" in agent_name_prop["description"]


class TestSendMessageToolSchema:
  """Tests for the ``send_message`` tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name is send_message."""
    spec = _send_message_spec()
    assert spec.name == "yoker:send_message"

  def test_schema_structure(self) -> None:
    """Test schema has to and message parameters."""
    spec = _send_message_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "yoker__send_message"
    assert "to" in schema["function"]["parameters"]["properties"]
    assert "message" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["to", "message"]


class TestSendMessageToolDelegation:
  """Tests that the ``send_message`` tool delegates to session.send."""

  @pytest.mark.asyncio
  async def test_delegates_to_session_send(self) -> None:
    """Successful send returns ToolResult with the target's response."""
    session = MagicMock()
    session.send = AsyncMock(return_value="the reply")

    spec = _send_message_spec(session=session, from_id="coordinator")
    result = await spec.execute(to="researcher", message="hi")

    assert result.success
    assert result.result == "the reply"
    session.send.assert_awaited_once()
    sent_msg: Message = session.send.call_args.args[0]
    assert sent_msg.from_id == "coordinator"
    assert sent_msg.to_id == "researcher"
    assert sent_msg.content == "hi"

  @pytest.mark.asyncio
  async def test_missing_to_returns_error(self) -> None:
    """Missing `to` parameter returns a failure result."""
    spec = _send_message_spec()
    result = await spec.execute(to="", message="hi")

    assert not result.success
    assert "to" in result.error

  @pytest.mark.asyncio
  async def test_missing_message_returns_error(self) -> None:
    """Missing `message` parameter returns a failure result."""
    spec = _send_message_spec()
    result = await spec.execute(to="researcher", message="")

    assert not result.success
    assert "message" in result.error

  @pytest.mark.asyncio
  async def test_unknown_target_returns_failure(self) -> None:
    """ValueError (unknown target) is wrapped as a failure result."""
    session = MagicMock()
    session.send = AsyncMock(side_effect=ValueError("No active agent with id 'ghost'"))

    spec = _send_message_spec(session=session, from_id="coordinator")
    result = await spec.execute(to="ghost", message="hi")

    assert not result.success
    assert "No active agent" in result.error

  @pytest.mark.asyncio
  async def test_generic_exception_wrapped_as_failure(self) -> None:
    """Unexpected exceptions are wrapped, not re-raised."""
    session = MagicMock()
    session.send = AsyncMock(side_effect=RuntimeError("boom"))

    spec = _send_message_spec(session=session, from_id="coordinator")
    result = await spec.execute(to="researcher", message="hi")

    assert not result.success
    assert "Send message error" in result.error
