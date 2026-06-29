"""Unit tests for LitellmBackend implementation (simplified design).

The simplified design uses:
  - config.backend.params for all provider parameters (flattened dict)
  - litellm-specific transforms (base_url → api_base, provider/model prefix)
"""

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

  def test_params_includes_api_key(self, mock_config_openai: Config) -> None:
    """Test that params includes api_key from config."""
    params = mock_config_openai.backend.params
    assert params["api_key"] == "test-openai-key"

  def test_params_includes_model(self, mock_config_openai: Config) -> None:
    """Test that params includes model from config."""
    params = mock_config_openai.backend.params
    assert params["model"] == "gpt-4o"

  def test_params_includes_base_url(self, mock_config_ollama: Config) -> None:
    """Test that params includes base_url from config."""
    params = mock_config_ollama.backend.params
    assert params["base_url"] == "http://localhost:11434"

  def test_params_filters_none_values(self, mock_config_openai: Config) -> None:
    """Test that params filters out None values."""
    params = mock_config_openai.backend.params
    # base_url is None for default OpenAI config
    assert "base_url" not in params

  def test_params_includes_parameters(self, mock_config_openai: Config) -> None:
    """Test that params includes nested parameters dict."""
    params = mock_config_openai.backend.params
    # Nested parameters are included (asdict behavior)
    assert "parameters" in params

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

      # Verify thinking events
      assert any(c.event == ChatChunkEvent.THINKING_START for c in chunks)
      assert any(c.event == ChatChunkEvent.THINKING_DELTA for c in chunks)
      assert any(c.event == ChatChunkEvent.THINKING_STOP for c in chunks)

  @pytest.mark.asyncio
  async def test_chat_stream_with_base_url_transform(
    self,
  ) -> None:
    """Test that base_url is transformed to api_base for litellm."""
    config = Config(
      backend=BackendConfig(
        provider="openai",
        openai=OpenAIConfig(
          api_key="test-key",
          model="gpt-4o",
          base_url="https://custom.api.com/v1",
        ),
      )
    )
    backend = LitellmBackend(config)

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

      async for _chunk in backend.chat_stream(
        model="gpt-4o",
        messages=[{"role": "user", "content": "test"}],
      ):
        pass  # Just consume the stream

      # Verify litellm.acompletion was called with api_base (not base_url)
      call_kwargs = mock_acompletion.call_args.kwargs
      assert "api_base" in call_kwargs
      assert call_kwargs["api_base"] == "https://custom.api.com/v1"
      assert "base_url" not in call_kwargs
