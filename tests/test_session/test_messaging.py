"""Tests for Session.send inter-agent messaging."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.config import Config
from yoker.events import AgentMessageEvent
from yoker.session import Session


def _make_mock_agent(name: str, response: str = "ok") -> MagicMock:
  """Build a mock agent with an AsyncMock process method and a session id."""
  agent = MagicMock(name=name)
  agent.process = AsyncMock(return_value=response)
  agent._session_id = name
  return agent


class TestSessionSend:
  """Tests for Session.send routing."""

  @pytest.mark.asyncio
  async def test_send_routes_to_target_agent(self) -> None:
    """send() calls target.process(content) and returns the response."""
    async with Session(config=Config()) as session:
      target = _make_mock_agent("researcher", response="found it")
      sender = _make_mock_agent("coordinator")
      session._agents_map["researcher"] = target
      session._agents_map["coordinator"] = sender
      response = await session.send(to=target, from_=sender, content="find X")
      assert response == "found it"
      target.process.assert_awaited_once_with("find X")

  @pytest.mark.asyncio
  async def test_send_emits_agent_message_event(self) -> None:
    """AGENT_MESSAGE is emitted before processing the message."""
    async with Session(config=Config()) as session:
      received: list = []
      session.add_event_handler(lambda e: received.append(e))
      target = _make_mock_agent("researcher", response="ok")
      sender = _make_mock_agent("coordinator")
      session._agents_map["researcher"] = target
      session._agents_map["coordinator"] = sender
      await session.send(to=target, from_=sender, content="hi")
      messages = [e for e in received if isinstance(e, AgentMessageEvent)]
      assert len(messages) == 1
      assert messages[0].from_id == "coordinator"
      assert messages[0].to_id == "researcher"
      assert messages[0].content == "hi"
      assert messages[0].session_id == session.id

  @pytest.mark.asyncio
  async def test_send_to_unknown_agent_raises_value_error(self) -> None:
    """Sending to an agent not in the session raises ValueError."""
    async with Session(config=Config()) as session:
      sender = _make_mock_agent("coordinator")
      ghost = _make_mock_agent("ghost")
      ghost._session_id = "ghost"
      with pytest.raises(ValueError, match="not active"):
        await session.send(to=ghost, from_=sender, content="hi")

  @pytest.mark.asyncio
  async def test_send_catches_target_exception_and_returns_error(self) -> None:
    """When target.process raises, send returns an error string (no raise)."""
    async with Session(config=Config()) as session:
      target = MagicMock()
      target.process = AsyncMock(side_effect=RuntimeError("boom"))
      target._session_id = "researcher"
      sender = _make_mock_agent("coordinator")
      session._agents_map["researcher"] = target
      session._agents_map["coordinator"] = sender
      response = await session.send(to=target, from_=sender, content="hi")
      assert "Error" in response
      assert "researcher" in response
      assert "boom" in response

  @pytest.mark.asyncio
  async def test_send_passes_content_as_prompt(self) -> None:
    """send() passes the content string to target.process as the prompt."""
    async with Session(config=Config()) as session:
      target = _make_mock_agent("researcher")
      sender = _make_mock_agent("coordinator")
      session._agents_map["researcher"] = target
      session._agents_map["coordinator"] = sender
      await session.send(to=target, from_=sender, content="the prompt")
      target.process.assert_awaited_once_with("the prompt")
