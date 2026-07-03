"""Unit tests for LitellmBackend implementation.

The LitellmBackend reads config.backend.config directly and flattens
parameters inline in chat_stream().
"""

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.backends.litellm import LitellmBackend
from yoker.backends.protocol import ChatChunkEvent
from yoker.config import (
  AnthropicConfig,
  AnthropicParameters,
  BackendConfig,
  Config,
  OllamaConfig,
  OllamaParameters,
  OpenAIConfig,
  OpenAIParameters,
)


class TestLitellmBackend:
  """Tests for LitellmBackend class."""

  @pytest.fixture
  def mock_config_openai(self) -> Config:
    """Create a mock Config with OpenAI backend."""
    return Config(
      backend=BackendConfig(
        provider="openai",
        openai=OpenAIConfig(
          api_key="test-openai-key",
          model="gpt-4o",
          parameters=OpenAIParameters(temperature=0.7),
        ),
      )
    )

  @pytest.fixture
  def mock_config_anthropic(self) -> Config:
    """Create a mock Config with Anthropic backend."""
    return Config(
      backend=BackendConfig(
        provider="anthropic",
        anthropic=AnthropicConfig(
          api_key="test-anthropic-key",
          model="claude-3-5-sonnet-20241022",
          parameters=AnthropicParameters(temperature=0.7),
        ),
      )
    )

  @pytest.fixture
  def mock_config_ollama(self) -> Config:
    """Create a mock Config with Ollama backend."""
    return Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          api_key="test-ollama-key",
          model="llama3.2",
          base_url="http://localhost:11434",
          parameters=OllamaParameters(temperature=0.7),
        ),
      )
    )

  @pytest.mark.asyncio
  async def test_chat_stream_content(self, mock_config_openai: Config) -> None:
    """Test chat_stream yields content events."""
    backend = LitellmBackend(mock_config_openai)

    # Mock litellm.acompletion
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "Hello"
    mock_chunk.choices[0].delta.tool_calls = None
    mock_chunk.usage.prompt_tokens = 10
    mock_chunk.usage.completion_tokens = 5

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
      # Setup mock to return async iterator
      async def async_gen():
        yield mock_chunk

      mock_acompletion.return_value = async_gen()

      # Collect chunks
      chunks = []
      async for chunk in backend.chat_stream(
        model="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
      ):
        chunks.append(chunk)

      # Verify we got content events
      assert any(c.event == ChatChunkEvent.CONTENT_START for c in chunks)
      assert any(c.event == ChatChunkEvent.CONTENT_DELTA for c in chunks)
      assert any(c.event == ChatChunkEvent.CONTENT_STOP for c in chunks)
      assert any(c.event == ChatChunkEvent.USAGE for c in chunks)
      assert any(c.event == ChatChunkEvent.DONE for c in chunks)

  @pytest.mark.asyncio
  async def test_chat_stream_thinking(self, mock_config_openai: Config) -> None:
    """Test chat_stream yields thinking events for reasoning_content."""
    backend = LitellmBackend(mock_config_openai)

    # Mock litellm.acompletion with reasoning_content
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.reasoning_content = "Thinking..."
    mock_chunk.choices[0].delta.content = None
    mock_chunk.choices[0].delta.tool_calls = None
    mock_chunk.usage.prompt_tokens = 10
    mock_chunk.usage.completion_tokens = 5

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:

      async def async_gen():
        yield mock_chunk

      mock_acompletion.return_value = async_gen()

      chunks = []
      async for chunk in backend.chat_stream(
        model="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
      ):
        chunks.append(chunk)

      # Verify we got thinking events
      assert any(c.event == ChatChunkEvent.THINKING_START for c in chunks)
      assert any(c.event == ChatChunkEvent.THINKING_DELTA for c in chunks)
      assert any(c.event == ChatChunkEvent.THINKING_STOP for c in chunks)

  @pytest.mark.asyncio
  async def test_chat_stream_tool_calls(self, mock_config_openai: Config) -> None:
    """Test chat_stream yields tool call events."""
    backend = LitellmBackend(mock_config_openai)

    # Mock litellm.acompletion with tool calls
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = None
    mock_chunk.choices[0].delta.tool_calls = None
    mock_chunk.usage.prompt_tokens = 10
    mock_chunk.usage.completion_tokens = 5

    # Create mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.index = 0
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "test_tool"
    mock_tool_call.function.arguments = '{"arg": "value"}'

    mock_chunk.choices[0].delta.tool_calls = [mock_tool_call]

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:

      async def async_gen():
        yield mock_chunk

      mock_acompletion.return_value = async_gen()

      chunks = []
      async for chunk in backend.chat_stream(
        model="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
      ):
        chunks.append(chunk)

      # Verify we got tool call events
      assert any(c.event == ChatChunkEvent.TOOL_CALL_START for c in chunks)
      assert any(c.event == ChatChunkEvent.TOOL_CALL_DELTA for c in chunks)
      assert any(c.event == ChatChunkEvent.TOOL_CALL_STOP for c in chunks)

  @pytest.mark.asyncio
  async def test_chat_stream_does_not_mutate_caller_messages(
    self, mock_config_openai: Config
  ) -> None:
    """Regression test for issue #38.

    LitellmBackend.chat_stream must NOT mutate the caller's messages list
    when converting tool-call arguments from dict to JSON string. The
    context stores arguments as dicts (generic format) and relies on
    get_context() returning a shallow copy; mutating inner dicts
    corrupts the stored context and breaks cross-backend resumption
    (e.g. Ollama requires dict arguments).
    """
    backend = LitellmBackend(mock_config_openai)

    # Mock litellm.acompletion to return an empty stream ending with DONE.
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "Hello"
    mock_chunk.choices[0].delta.tool_calls = None
    mock_chunk.usage.prompt_tokens = 10
    mock_chunk.usage.completion_tokens = 5

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:

      async def async_gen():
        yield mock_chunk

      mock_acompletion.return_value = async_gen()

      # Messages with a tool_calls entry whose arguments is a dict (generic format).
      messages = [
        {"role": "user", "content": "do a thing"},
        {
          "role": "assistant",
          "content": "",
          "tool_calls": [
            {
              "id": "call_1",
              "function": {
                "name": "test_tool",
                "arguments": {"arg": "value"},
              },
            }
          ],
        },
      ]
      # Snapshot a deep copy for later comparison.
      original = copy.deepcopy(messages)

      async for _ in backend.chat_stream(
        model="gpt-4o",
        messages=messages,
      ):
        pass

      # The caller's messages must be unchanged, including the nested
      # tool_call arguments which must remain a dict.
      assert messages == original, (
        "LitellmBackend.chat_stream mutated the caller's messages list; "
        "it must deep-copy before converting dict arguments to JSON strings."
      )
      assert isinstance(messages[1]["tool_calls"][0]["function"]["arguments"], dict), (
        "tool_call arguments must remain a dict in the caller's messages"
      )

  @pytest.mark.asyncio
  async def test_chat_stream_passes_json_string_arguments_to_litellm(
    self, mock_config_openai: Config
  ) -> None:
    """LitellmBackend must still pass JSON-string arguments to litellm.acompletion.

    Even though it must not mutate the caller's messages, the backend is
    responsible for converting dict arguments to JSON strings before
    handing them to litellm (which expects OpenAI-format JSON strings).
    """
    backend = LitellmBackend(mock_config_openai)

    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta.content = "Hello"
    mock_chunk.choices[0].delta.tool_calls = None
    mock_chunk.usage.prompt_tokens = 10
    mock_chunk.usage.completion_tokens = 5

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:

      async def async_gen():
        yield mock_chunk

      mock_acompletion.return_value = async_gen()

      messages = [
        {
          "role": "assistant",
          "content": "",
          "tool_calls": [
            {
              "id": "call_1",
              "function": {
                "name": "test_tool",
                "arguments": {"arg": "value"},
              },
            }
          ],
        },
      ]

      async for _ in backend.chat_stream(
        model="gpt-4o",
        messages=messages,
      ):
        pass

      # Inspect the messages actually passed to litellm.acompletion.
      call_kwargs = mock_acompletion.call_args
      sent_messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
      sent_args = sent_messages[0]["tool_calls"][0]["function"]["arguments"]
      assert isinstance(sent_args, str), (
        "litellm.acompletion must receive JSON-string tool-call arguments"
      )
      import json as _json

      assert _json.loads(sent_args) == {"arg": "value"}
