"""Tests for Session.send inter-agent messaging (MBI-007 7.4.2, D3)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.config import Config
from yoker.events import AgentMessageEvent
from yoker.session import Message, Session


def _make_mock_agent(name: str, response: str = "ok") -> MagicMock:
  """Build a mock agent with an AsyncMock process method."""
  agent = MagicMock(name=name)
  agent.process = AsyncMock(return_value=response)
  return agent


class TestSessionSend:
  """Tests for Session.send routing (task 7.4.2)."""

  @pytest.mark.asyncio
  async def test_send_routes_to_target_agent(self) -> None:
    """send() calls target.process(content) and returns the response."""
    async with Session(config=Config()) as session:
      target = _make_mock_agent("researcher", response="found it")
      session._agents_map["researcher"] = target
      response = await session.send(
        Message(from_id="coordinator", to_id="researcher", content="find X")
      )
      assert response == "found it"
      target.process.assert_awaited_once_with("find X")

  @pytest.mark.asyncio
  async def test_send_emits_agent_message_event(self) -> None:
    """AGENT_MESSAGE is emitted before processing the message."""
    async with Session(config=Config()) as session:
      received: list = []
      session.add_event_handler(lambda e: received.append(e))
      target = _make_mock_agent("researcher", response="ok")
      session._agents_map["researcher"] = target
      await session.send(Message(from_id="coordinator", to_id="researcher", content="hi"))
      messages = [e for e in received if isinstance(e, AgentMessageEvent)]
      assert len(messages) == 1
      assert messages[0].from_id == "coordinator"
      assert messages[0].to_id == "researcher"
      assert messages[0].content == "hi"
      assert messages[0].session_id == session.id

  @pytest.mark.asyncio
  async def test_send_to_unknown_agent_raises_value_error(self) -> None:
    """Sending to an unknown id raises ValueError."""
    async with Session(config=Config()) as session:
      with pytest.raises(ValueError, match="No active agent"):
        await session.send(Message(from_id="coordinator", to_id="ghost", content="hi"))

  @pytest.mark.asyncio
  async def test_send_catches_target_exception_and_returns_error(self) -> None:
    """When target.process raises, send returns an error string (no raise)."""
    async with Session(config=Config()) as session:
      target = MagicMock()
      target.process = AsyncMock(side_effect=RuntimeError("boom"))
      session._agents_map["researcher"] = target
      response = await session.send(
        Message(from_id="coordinator", to_id="researcher", content="hi")
      )
      assert "Error" in response
      assert "researcher" in response
      assert "boom" in response

  @pytest.mark.asyncio
  async def test_send_uses_content_not_metadata_for_prompt(self) -> None:
    """send() passes message.content (the prompt) to target.process, not metadata."""
    async with Session(config=Config()) as session:
      target = _make_mock_agent("researcher")
      session._agents_map["researcher"] = target
      await session.send(
        Message(
          from_id="coordinator",
          to_id="researcher",
          content="the prompt",
          metadata={"priority": 1},
        )
      )
      target.process.assert_awaited_once_with("the prompt")
