"""Tests for OllamaBackend adapter."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from yoker.backends.ollama import OllamaBackend
from yoker.backends.protocol import ChatChunkEvent
from yoker.config import BackendConfig, Config, OllamaConfig


@dataclass
class MockToolCallFunction:
  """Mock tool call function."""

  name: str
  arguments: str


@dataclass
class MockToolCall:
  """Mock tool call."""

  function: MockToolCallFunction
  id: str | None = None


@dataclass
class MockMessage:
  """Mock Ollama message chunk."""

  content: str | None = None
  thinking: str | None = None
  tool_calls: list[MockToolCall] | None = None


@dataclass
class MockChunk:
  """Mock Ollama streaming chunk."""

  message: MockMessage
  done: bool = False
  prompt_eval_count: int | None = None
  eval_count: int | None = None
  total_duration: int | None = None  # nanoseconds


async def _async_iter(items: list[Any]) -> AsyncIterator[Any]:
  """Convert a list to an async iterator."""
  for item in items:
    yield item


def _create_mock_config() -> Config:
  """Create a mock Config with Ollama backend."""
  return Config(
    backend=BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(
        model="test-model",
        base_url="http://localhost:11434",
      ),
    )
  )


class TestOllamaBackend:
  """Tests for OllamaBackend class."""

  @pytest.mark.asyncio
  async def test_chat_stream_yields_content_blocks(self):
    """OllamaBackend.chat_stream yields CONTENT_START/DELTA/STOP for content."""
    from ollama import AsyncClient

    # Create mock chunks
    chunks = [
      MockChunk(message=MockMessage(content="Hello")),
      MockChunk(message=MockMessage(content=" world")),
      MockChunk(
        message=MockMessage(),
        done=True,
        prompt_eval_count=10,
        eval_count=5,
        total_duration=100_000_000,  # 100ms in nanoseconds
      ),
    ]

    # Create mock client
    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=_async_iter(chunks))

    config = _create_mock_config()

    # Patch AsyncClient creation
    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)

      # Collect all chunks
      events = []
      async for chunk in backend.chat_stream(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
      ):
        events.append(chunk)

      # Verify sequence: CONTENT_START, CONTENT_DELTA, CONTENT_DELTA, CONTENT_STOP, USAGE, DONE
      assert len(events) == 6
      assert events[0].event == ChatChunkEvent.CONTENT_START
      assert events[0].index == 0

      assert events[1].event == ChatChunkEvent.CONTENT_DELTA
      assert events[1].text == "Hello"

      assert events[2].event == ChatChunkEvent.CONTENT_DELTA
      assert events[2].text == " world"

      assert events[3].event == ChatChunkEvent.CONTENT_STOP
      assert events[3].index == 0

      assert events[4].event == ChatChunkEvent.USAGE
      assert events[4].usage is not None
      assert events[4].usage.prompt_eval_count == 10
      assert events[4].usage.eval_count == 5
      assert events[4].usage.total_duration_ms == 100

      assert events[5].event == ChatChunkEvent.DONE

  @pytest.mark.asyncio
  async def test_chat_stream_yields_thinking_blocks(self):
    """OllamaBackend.chat_stream yields THINKING_START/DELTA/STOP for thinking."""
    from ollama import AsyncClient

    # Create mock chunks with thinking content
    chunks = [
      MockChunk(message=MockMessage(thinking="Let me think...")),
      MockChunk(message=MockMessage(thinking=" hmm...")),
      MockChunk(message=MockMessage(content="The answer is 42")),
      MockChunk(
        message=MockMessage(),
        done=True,
        prompt_eval_count=5,
        eval_count=3,
        total_duration=50_000_000,
      ),
    ]

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=_async_iter(chunks))

    config = _create_mock_config()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)

      events = []
      async for chunk in backend.chat_stream(
        model="test-model",
        messages=[{"role": "user", "content": "What is the answer?"}],
        think=True,
      ):
        events.append(chunk)

      # Verify sequence: THINKING_START, THINKING_DELTA, THINKING_DELTA, THINKING_STOP,
      #                  CONTENT_START, CONTENT_DELTA, CONTENT_STOP, USAGE, DONE
      assert len(events) == 9

      # Thinking block
      assert events[0].event == ChatChunkEvent.THINKING_START
      assert events[1].event == ChatChunkEvent.THINKING_DELTA
      assert events[1].text == "Let me think..."
      assert events[2].event == ChatChunkEvent.THINKING_DELTA
      assert events[2].text == " hmm..."
      assert events[3].event == ChatChunkEvent.THINKING_STOP

      # Content block
      assert events[4].event == ChatChunkEvent.CONTENT_START
      assert events[5].event == ChatChunkEvent.CONTENT_DELTA
      assert events[5].text == "The answer is 42"
      assert events[6].event == ChatChunkEvent.CONTENT_STOP

      # Stats
      assert events[7].event == ChatChunkEvent.USAGE
      assert events[8].event == ChatChunkEvent.DONE

  @pytest.mark.asyncio
  async def test_chat_stream_yields_tool_call_blocks(self):
    """OllamaBackend.chat_stream yields TOOL_CALL_START/DELTA/STOP for tool calls."""
    from ollama import AsyncClient

    # Create mock chunks with tool calls
    tool_call = MockToolCall(
      id="call_123",
      function=MockToolCallFunction(
        name="get_weather",
        arguments={"location": "San Francisco"},
      ),
    )

    chunks = [
      MockChunk(message=MockMessage(tool_calls=[tool_call])),
      MockChunk(
        message=MockMessage(),
        done=True,
        prompt_eval_count=8,
        eval_count=2,
        total_duration=30_000_000,
      ),
    ]

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=_async_iter(chunks))

    config = _create_mock_config()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)

      events = []
      async for chunk in backend.chat_stream(
        model="test-model",
        messages=[{"role": "user", "content": "What's the weather?"}],
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
      ):
        events.append(chunk)

      # Verify sequence: TOOL_CALL_START, TOOL_CALL_DELTA, TOOL_CALL_STOP, USAGE, DONE
      assert len(events) == 5

      assert events[0].event == ChatChunkEvent.TOOL_CALL_START
      assert events[0].index == 0
      assert events[0].tool_call is not None
      assert events[0].tool_call.id == "call_123"
      assert events[0].tool_call.name == "get_weather"

      assert events[1].event == ChatChunkEvent.TOOL_CALL_DELTA
      assert events[1].tool_call is not None
      # Arguments should be JSON string
      assert events[1].tool_call.arguments_delta == '{"location": "San Francisco"}'

      assert events[2].event == ChatChunkEvent.TOOL_CALL_STOP
      assert events[2].index == 0

      assert events[3].event == ChatChunkEvent.USAGE
      assert events[4].event == ChatChunkEvent.DONE

  @pytest.mark.asyncio
  async def test_chat_stream_tool_call_with_string_arguments(self):
    """OllamaBackend passes through string arguments without double-encoding.

    Some cloud models may return tool call arguments as a JSON string
    instead of a dict. The backend should pass it through as-is rather
    than calling json.dumps on it (which would double-encode).
    """
    from ollama import AsyncClient

    tool_call = MockToolCall(
      id="call_456",
      function=MockToolCallFunction(
        name="get_weather",
        arguments='{"location": "Paris"}',
      ),
    )

    chunks = [
      MockChunk(message=MockMessage(tool_calls=[tool_call])),
      MockChunk(
        message=MockMessage(),
        done=True,
        prompt_eval_count=5,
        eval_count=1,
        total_duration=20_000_000,
      ),
    ]

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=_async_iter(chunks))

    config = _create_mock_config()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)

      events = []
      async for chunk in backend.chat_stream(
        model="test-model",
        messages=[{"role": "user", "content": "Weather?"}],
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
      ):
        events.append(chunk)

      # The DELTA should contain the original string, not double-encoded.
      delta_event = next(e for e in events if e.event == ChatChunkEvent.TOOL_CALL_DELTA)
      assert delta_event.tool_call.arguments_delta == '{"location": "Paris"}'

  @pytest.mark.asyncio
  async def test_chat_stream_handles_empty_content(self):
    """OllamaBackend.chat_stream handles chunks with no content."""
    from ollama import AsyncClient

    # Create mock chunks with only done flag
    chunks = [
      MockChunk(
        message=MockMessage(),
        done=True,
        prompt_eval_count=2,
        eval_count=1,
        total_duration=10_000_000,
      ),
    ]

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=_async_iter(chunks))

    config = _create_mock_config()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)

      events = []
      async for chunk in backend.chat_stream(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
      ):
        events.append(chunk)

      # Should only emit USAGE and DONE
      assert len(events) == 2
      assert events[0].event == ChatChunkEvent.USAGE
      assert events[1].event == ChatChunkEvent.DONE

  @pytest.mark.asyncio
  async def test_chat_stream_passes_parameters_to_client(self):
    """OllamaBackend.chat_stream passes model, messages, tools, and think to client."""
    from ollama import AsyncClient

    # Create minimal chunks
    chunks = [
      MockChunk(
        message=MockMessage(),
        done=True,
        prompt_eval_count=1,
        eval_count=1,
        total_duration=5_000_000,
      ),
    ]

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=_async_iter(chunks))

    config = _create_mock_config()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)

      messages = [{"role": "user", "content": "Test"}]
      tools = [{"type": "function", "function": {"name": "test_tool"}}]

      async for _ in backend.chat_stream(
        model="test-model",
        messages=messages,
        tools=tools,
        think=True,
      ):
        pass

      # Verify client.chat was called with correct parameters
      mock_client.chat.assert_called_once()
      call_kwargs = mock_client.chat.call_args.kwargs
      assert call_kwargs["model"] == "test-model"
      assert call_kwargs["messages"] == messages
      assert call_kwargs["tools"] == tools
      assert call_kwargs["think"] is True
      assert call_kwargs["stream"] is True


class TestOllamaBackendFetchUsage:
  """Tests for OllamaBackend.fetch_usage method."""

  @pytest.mark.asyncio
  async def test_fetch_usage_returns_none_without_api_key(self):
    """fetch_usage returns None when no API key is configured."""
    config = _create_mock_config()  # No api_key set
    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
    result = await backend.fetch_usage()
    assert result is None

  @pytest.mark.asyncio
  async def test_fetch_usage_returns_data_with_api_key(self):
    """fetch_usage returns parsed JSON when API key is set."""
    config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          model="test-model",
          base_url="http://localhost:11434",
          api_key="test-token",
        ),
      )
    )

    class FakeResponse:
      def raise_for_status(self) -> None:
        pass

      def json(self) -> dict[str, Any]:
        return {"limits": {"session": {"usage": 0.975}, "weekly": {"usage": 0.531}}}

    class FakeClient:
      async def __aenter__(self):
        return self

      async def __aexit__(self, *args):
        return None

      async def get(self, url, headers=None):
        return FakeResponse()

    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
    with patch("yoker.backends.ollama.httpx.AsyncClient", return_value=FakeClient()):
      result = await backend.fetch_usage()
    assert result is not None
    assert "limits" in result
    assert result["limits"]["session"]["usage"] == 0.975

  @pytest.mark.asyncio
  async def test_fetch_usage_returns_none_on_error(self):
    """fetch_usage returns None on network error."""
    config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          model="test-model",
          base_url="http://localhost:11434",
          api_key="test-token",
        ),
      )
    )

    class FailingClient:
      async def __aenter__(self):
        return self

      async def __aexit__(self, *args):
        return None

      async def get(self, url, headers=None):
        raise httpx.ConnectError("fail")

    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
    with patch("yoker.backends.ollama.httpx.AsyncClient", return_value=FailingClient()):
      result = await backend.fetch_usage()
    assert result is None
