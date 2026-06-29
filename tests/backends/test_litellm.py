"""Unit tests for LitellmBackend implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.backends.litellm import LitellmBackend, model_has_reasoning
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

  def test_provider_property_openai(self, mock_config_openai: Config) -> None:
    """Test provider property returns 'openai' for OpenAI backend."""
    backend = LitellmBackend(mock_config_openai)
    assert backend.provider == "openai"

  def test_provider_property_anthropic(self, mock_config_anthropic: Config) -> None:
    """Test provider property returns 'anthropic' for Anthropic backend."""
    backend = LitellmBackend(mock_config_anthropic)
    assert backend.provider == "anthropic"

  def test_provider_property_ollama(self, mock_config_ollama: Config) -> None:
    """Test provider property returns 'ollama' for Ollama backend."""
    backend = LitellmBackend(mock_config_ollama)
    assert backend.provider == "ollama"

  def test_get_model_string_openai(self, mock_config_openai: Config) -> None:
    """Test model string conversion for OpenAI."""
    backend = LitellmBackend(mock_config_openai)
    model_string = backend._get_model_string("gpt-4o-mini")
    assert model_string == "openai/gpt-4o-mini"

  def test_get_model_string_anthropic(self, mock_config_anthropic: Config) -> None:
    """Test model string conversion for Anthropic."""
    backend = LitellmBackend(mock_config_anthropic)
    model_string = backend._get_model_string("claude-3-opus-20240229")
    assert model_string == "anthropic/claude-3-opus-20240229"

  def test_get_model_string_ollama(self, mock_config_ollama: Config) -> None:
    """Test model string conversion for Ollama."""
    backend = LitellmBackend(mock_config_ollama)
    model_string = backend._get_model_string("llama3.2:latest")
    assert model_string == "ollama/llama3.2:latest"

  def test_get_api_key_openai(self, mock_config_openai: Config) -> None:
    """Test API key extraction for OpenAI."""
    backend = LitellmBackend(mock_config_openai)
    api_key = backend._get_api_key()
    assert api_key == "test-openai-key"

  def test_get_api_key_anthropic(self, mock_config_anthropic: Config) -> None:
    """Test API key extraction for Anthropic."""
    backend = LitellmBackend(mock_config_anthropic)
    api_key = backend._get_api_key()
    assert api_key == "test-anthropic-key"

  def test_get_api_key_ollama(self, mock_config_ollama: Config) -> None:
    """Test API key extraction for Ollama."""
    backend = LitellmBackend(mock_config_ollama)
    api_key = backend._get_api_key()
    assert api_key == "test-ollama-key"

  def test_get_base_url_openai(self, mock_config_openai: Config) -> None:
    """Test base URL extraction for OpenAI (None = use default)."""
    backend = LitellmBackend(mock_config_openai)
    base_url = backend._get_base_url()
    assert base_url is None

  def test_get_base_url_anthropic(self, mock_config_anthropic: Config) -> None:
    """Test base URL extraction for Anthropic (None = use default)."""
    backend = LitellmBackend(mock_config_anthropic)
    base_url = backend._get_base_url()
    assert base_url is None

  def test_get_base_url_ollama(self, mock_config_ollama: Config) -> None:
    """Test base URL extraction for Ollama."""
    backend = LitellmBackend(mock_config_ollama)
    base_url = backend._get_base_url()
    assert base_url == "http://localhost:11434"

  def test_build_kwargs_openai(self, mock_config_openai: Config) -> None:
    """Test kwargs building for OpenAI."""
    backend = LitellmBackend(mock_config_openai)
    kwargs = backend._build_kwargs(think=False)

    assert kwargs["temperature"] == 0.7
    assert kwargs["top_p"] == 0.9

  def test_build_kwargs_anthropic(self, mock_config_anthropic: Config) -> None:
    """Test kwargs building for Anthropic."""
    backend = LitellmBackend(mock_config_anthropic)
    kwargs = backend._build_kwargs(think=False)

    assert kwargs["temperature"] == 0.7
    assert kwargs["top_p"] == 0.9
    assert kwargs["max_tokens"] == 4096

  def test_build_kwargs_anthropic_thinking(self, mock_config_anthropic: Config) -> None:
    """Test kwargs building for Anthropic with thinking enabled."""
    backend = LitellmBackend(mock_config_anthropic)
    kwargs = backend._build_kwargs(think=True)

    assert kwargs["budget_tokens"] == 1024  # From config

  def test_build_kwargs_ollama(self, mock_config_ollama: Config) -> None:
    """Test kwargs building for Ollama."""
    backend = LitellmBackend(mock_config_ollama)
    kwargs = backend._build_kwargs(think=False)

    assert kwargs["temperature"] == 0.7
    assert kwargs["top_p"] == 0.9
    assert kwargs["top_k"] == 40
    assert kwargs["num_ctx"] == 4096

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


class TestModelHasReasoning:
  """Tests for model_has_reasoning function."""

  def test_o1_model_has_reasoning(self) -> None:
    """Test OpenAI o1 models are detected as reasoning models."""
    assert model_has_reasoning("openai/o1-preview")
    assert model_has_reasoning("openai/o1-mini")
    assert model_has_reasoning("openai/O1-Preview")  # Case insensitive
    assert model_has_reasoning("openai/o1_2024_12_17")

  def test_o3_model_has_reasoning(self) -> None:
    """Test OpenAI o3 models are detected as reasoning models."""
    assert model_has_reasoning("openai/o3-mini")
    assert model_has_reasoning("openai/o3_2025_01_31")

  def test_gpt_model_no_reasoning(self) -> None:
    """Test GPT models are not reasoning models."""
    assert not model_has_reasoning("openai/gpt-4o")
    assert not model_has_reasoning("openai/gpt-4o-mini")
    assert not model_has_reasoning("openai/gpt-3.5-turbo")

  def test_anthropic_model_no_reasoning(self) -> None:
    """Test Anthropic models are not reasoning models."""
    assert not model_has_reasoning("anthropic/claude-3-5-sonnet-20241022")
    assert not model_has_reasoning("anthropic/claude-3-opus-20240229")

  def test_ollama_model_no_reasoning(self) -> None:
    """Test Ollama models are not reasoning models."""
    assert not model_has_reasoning("ollama/llama3.2")
    assert not model_has_reasoning("ollama/mistral")

