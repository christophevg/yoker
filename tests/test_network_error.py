"""Tests for network error handling in Agent."""

from unittest.mock import patch

import httpx
import pytest

from yoker.agent import Agent
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


class TestAgentNetworkErrors:
  """Tests for Agent network error handling."""

  def test_agent_raises_network_error_on_remote_protocol_error(self) -> None:
    """Test that RemoteProtocolError is converted to NetworkError."""
    agent = Agent()

    # Mock the client.chat to raise RemoteProtocolError
    with patch.object(agent.client, 'chat') as mock_chat:
      mock_chat.side_effect = httpx.RemoteProtocolError(
        "peer closed connection without sending complete message body"
      )

      with pytest.raises(NetworkError) as exc_info:
        agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert exc_info.value.recoverable is True
      assert isinstance(exc_info.value.original_error, httpx.RemoteProtocolError)

  def test_agent_raises_network_error_on_connect_error(self) -> None:
    """Test that ConnectError is converted to NetworkError."""
    agent = Agent()

    with patch.object(agent.client, 'chat') as mock_chat:
      mock_chat.side_effect = httpx.ConnectError("Connection refused")

      with pytest.raises(NetworkError) as exc_info:
        agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert isinstance(exc_info.value.original_error, httpx.ConnectError)

  def test_agent_raises_network_error_on_read_timeout(self) -> None:
    """Test that ReadTimeout is converted to NetworkError."""
    agent = Agent()

    with patch.object(agent.client, 'chat') as mock_chat:
      mock_chat.side_effect = httpx.ReadTimeout("Read timed out")

      with pytest.raises(NetworkError) as exc_info:
        agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert isinstance(exc_info.value.original_error, httpx.ReadTimeout)

  def test_agent_raises_network_error_on_connect_timeout(self) -> None:
    """Test that ConnectTimeout is converted to NetworkError."""
    agent = Agent()

    with patch.object(agent.client, 'chat') as mock_chat:
      mock_chat.side_effect = httpx.ConnectTimeout("Connection timed out")

      with pytest.raises(NetworkError) as exc_info:
        agent.process("Hello")

      assert "Network error" in str(exc_info.value)
      assert isinstance(exc_info.value.original_error, httpx.ConnectTimeout)

  def test_agent_context_preserved_on_network_error(self) -> None:
    """Test that context state is preserved when NetworkError is raised."""
    agent = Agent()

    # Add initial context
    agent.context.add_message("user", "First message")
    initial_messages = agent.context.get_messages().copy()

    with patch.object(agent.client, 'chat') as mock_chat:
      mock_chat.side_effect = httpx.ConnectError("Connection refused")

      with pytest.raises(NetworkError):
        agent.process("Second message")

      # Context should still have the original message
      # (the failed turn's message was added but can be recovered from)
      assert len(agent.context.get_messages()) >= len(initial_messages)


class TestNetworkErrorRecovery:
  """Tests for recovering from network errors."""

  def test_network_error_is_recoverable(self) -> None:
    """Test that network errors are marked recoverable."""
    error = NetworkError("Connection failed")
    assert error.recoverable is True

  def test_different_httpx_errors_are_recoverable(self) -> None:
    """Test that all common httpx errors are recoverable."""
    agent = Agent()

    httpx_errors = [
      httpx.RemoteProtocolError("protocol error"),
      httpx.ConnectError("connection failed"),
      httpx.ReadTimeout("timeout"),
      httpx.ConnectTimeout("timeout"),
    ]

    for error in httpx_errors:
      with patch.object(agent.client, 'chat') as mock_chat:
        mock_chat.side_effect = error

        with pytest.raises(NetworkError) as exc_info:
          agent.process("test")

        assert exc_info.value.recoverable is True
