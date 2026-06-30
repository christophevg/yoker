"""Tests for network error handling in Agent."""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from yoker.agent import Agent
from yoker.backends import ChatChunk
from yoker.config import Config
from yoker.exceptions import NetworkError


class TestNetworkError:
  """Tests for NetworkError exception class."""

  def test_network_error_basic(self) -> None:
    """Test NetworkError can be created with message."""
    error = NetworkError("Connection failed")
    assert str(error) == "Connection failed"
    assert error.recoverable is True
    assert error.original_error is None

  def test_network_error_with_original(self) -> None:
    """Test NetworkError preserves original error."""
    original = httpx.RemoteProtocolError("peer closed connection")
    error = NetworkError("Network error", original_error=original)
    assert error.original_error is original
    assert "Network error" in str(error)

  def test_network_error_non_recoverable(self) -> None:
    """Test NetworkError can be marked non-recoverable."""
    error = NetworkError("Fatal error", recoverable=False)
    assert error.recoverable is False


async def _aiter_chunks(chunks: list[ChatChunk]) -> AsyncIterator[ChatChunk]:
  """Async generator that yields ChatChunk instances."""
  for chunk in chunks:
    yield chunk


class TestAgentNetworkErrors:
  """Tests for Agent network error handling."""

  @pytest.mark.asyncio
  async def test_agent_raises_network_error_on_remote_protocol_error(self) -> None:
    """Test that RemoteProtocolError is converted to NetworkError."""
    agent = Agent(config=Config())

    # Mock the backend's chat_stream to raise RemoteProtocolError
    async def raise_error(*args: Any, **kwargs: Any) -> AsyncIterator[ChatChunk]:
      raise httpx.RemoteProtocolError(
        "peer closed connection without sending complete message body"
      )
      yield  # type: ignore # Never reached, but needed for type checker

    with patch.object(agent._backend, "chat_stream", side_effect=raise_error):
      with pytest.raises(NetworkError) as exc_info:
        await agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert exc_info.value.recoverable is True
      assert isinstance(exc_info.value.original_error, httpx.RemoteProtocolError)

  @pytest.mark.asyncio
  async def test_agent_raises_network_error_on_connect_error(self) -> None:
    """Test that ConnectError is converted to NetworkError."""
    agent = Agent(config=Config())

    async def raise_error(*args: Any, **kwargs: Any) -> AsyncIterator[ChatChunk]:
      raise httpx.ConnectError("Connection refused")
      yield  # type: ignore

    with patch.object(agent._backend, "chat_stream", side_effect=raise_error):
      with pytest.raises(NetworkError) as exc_info:
        await agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert isinstance(exc_info.value.original_error, httpx.ConnectError)

  @pytest.mark.asyncio
  async def test_agent_raises_network_error_on_read_timeout(self) -> None:
    """Test that ReadTimeout is converted to NetworkError."""
    agent = Agent(config=Config())

    async def raise_error(*args: Any, **kwargs: Any) -> AsyncIterator[ChatChunk]:
      raise httpx.ReadTimeout("Read timed out")
      yield  # type: ignore

    with patch.object(agent._backend, "chat_stream", side_effect=raise_error):
      with pytest.raises(NetworkError) as exc_info:
        await agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert isinstance(exc_info.value.original_error, httpx.ReadTimeout)

  @pytest.mark.asyncio
  async def test_agent_raises_network_error_on_connect_timeout(self) -> None:
    """Test that ConnectTimeout is converted to NetworkError."""
    agent = Agent(config=Config())

    async def raise_error(*args: Any, **kwargs: Any) -> AsyncIterator[ChatChunk]:
      raise httpx.ConnectTimeout("Connection timed out")
      yield  # type: ignore

    with patch.object(agent._backend, "chat_stream", side_effect=raise_error):
      with pytest.raises(NetworkError) as exc_info:
        await agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert isinstance(exc_info.value.original_error, httpx.ConnectTimeout)

  @pytest.mark.asyncio
  async def test_agent_context_preserved_on_network_error(self) -> None:
    """Test that context state is preserved when NetworkError is raised."""
    agent = Agent(config=Config())
    initial_message_count = len(agent.context.get_messages())

    async def raise_error(*args: Any, **kwargs: Any) -> AsyncIterator[ChatChunk]:
      raise httpx.ConnectError("Connection refused")
      yield  # type: ignore

    with patch.object(agent._backend, "chat_stream", side_effect=raise_error):
      with pytest.raises(NetworkError):
        await agent.process("Hello")

    # Context should still have the user message
    assert len(agent.context.get_messages()) == initial_message_count + 1


class TestNetworkErrorRecovery:
  """Tests for NetworkError recovery behavior."""

  def test_different_httpx_errors_are_recoverable(self) -> None:
    """Test that different httpx error types can be wrapped in NetworkError."""
    errors = [
      httpx.RemoteProtocolError("peer closed"),
      httpx.ConnectError("connection refused"),
      httpx.ReadError("read error"),
      httpx.WriteError("write error"),
      httpx.ConnectTimeout("connect timeout"),
      httpx.ReadTimeout("read timeout"),
    ]

    for original_error in errors:
      network_error = NetworkError("Network error", original_error=original_error)
      assert network_error.recoverable is True
      assert network_error.original_error is original_error
