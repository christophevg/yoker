"""Tests for backend context-management support (IP-12).

Verifies the ``supports_context_management`` flag and the
``context_management`` kwarg on ``chat_stream``:
  - Anthropic via LitellmBackend: flag True, directive forwarded.
  - OpenAI/Gemini via LitellmBackend: flag False, directive dropped.
  - OllamaBackend: flag False, directive accepted but ignored.
  - ModelBackend Protocol declares the attribute and kwarg.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from yoker.backends.litellm import LitellmBackend
from yoker.backends.ollama import OllamaBackend
from yoker.backends.protocol import ModelBackend
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


def _cfg(provider: str) -> Config:
  if provider == "anthropic":
    return Config(
      backend=BackendConfig(
        provider="anthropic",
        anthropic=AnthropicConfig(
          api_key="k",
          model="claude-3-5-sonnet-20241022",
          parameters=AnthropicParameters(),
        ),
      )
    )
  if provider == "openai":
    return Config(
      backend=BackendConfig(
        provider="openai",
        openai=OpenAIConfig(
          api_key="k",
          model="gpt-4o",
          parameters=OpenAIParameters(),
        ),
      )
    )
  return Config(
    backend=BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(
        api_key="k",
        model="llama3.2",
        base_url="http://localhost:11434",
        parameters=OllamaParameters(),
      ),
    )
  )


class TestSupportsContextManagement:
  """The supports_context_management flag reflects the provider."""

  def test_litellm_anthropic_supports(self) -> None:
    """Anthropic via LiteLLM sets supports_context_management = True."""
    backend = LitellmBackend(_cfg("anthropic"))
    assert backend.supports_context_management is True

  def test_litellm_openai_does_not_support(self) -> None:
    """OpenAI via LiteLLM does not support the directive."""
    backend = LitellmBackend(_cfg("openai"))
    assert backend.supports_context_management is False

  def test_ollama_does_not_support(self) -> None:
    """Ollama does not support a provider-side context_management directive."""
    backend = OllamaBackend(_cfg("ollama"))
    assert backend.supports_context_management is False

  def test_protocol_declares_attribute(self) -> None:
    """The ModelBackend Protocol declares supports_context_management."""
    assert "supports_context_management" in ModelBackend.__annotations__
    assert "context_management" in ModelBackend.chat_stream.__annotations__


class TestContextManagementKwarg:
  """The context_management kwarg is forwarded only when supported."""

  @pytest.mark.asyncio
  async def test_litellm_anthropic_forwards_directive(self) -> None:
    """Anthropic backend forwards context_management to litellm.acompletion."""
    backend = LitellmBackend(_cfg("anthropic"))
    directive: dict[str, Any] = {"edits": [{"type": "clear_thinking_20251015"}]}

    captured: dict[str, Any] = {}

    async def fake_acompletion(**kwargs: Any) -> Any:
      captured.update(kwargs)

      async def gen() -> Any:
        if False:  # pragma: no cover
          yield

      return gen()

    with patch("yoker.backends.litellm.litellm.acompletion", new=fake_acompletion):
      async for _ in backend.chat_stream(
        model="claude-3-5-sonnet-20241022",
        messages=[{"role": "user", "content": "hi"}],
        context_management=directive,
      ):
        pass

    assert captured.get("context_management") == directive

  @pytest.mark.asyncio
  async def test_litellm_openai_drops_directive(self) -> None:
    """OpenAI backend drops context_management (no provider support)."""
    backend = LitellmBackend(_cfg("openai"))
    directive: dict[str, Any] = {"edits": []}

    captured: dict[str, Any] = {}

    async def fake_acompletion(**kwargs: Any) -> Any:
      captured.update(kwargs)

      async def gen() -> Any:
        if False:  # pragma: no cover
          yield

      return gen()

    with patch("yoker.backends.litellm.litellm.acompletion", new=fake_acompletion):
      async for _ in backend.chat_stream(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        context_management=directive,
      ):
        pass

    assert "context_management" not in captured

  @pytest.mark.asyncio
  async def test_ollama_accepts_and_ignores_directive(self) -> None:
    """Ollama accepts the kwarg (ignored) without raising."""
    from ollama import AsyncClient

    async def empty_gen() -> Any:
      if False:  # pragma: no cover
        yield

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.chat = AsyncMock(return_value=empty_gen())

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(_cfg("ollama"))
      # Should not raise even with context_management passed.
      async for _ in backend.chat_stream(
        model="llama3.2",
        messages=[{"role": "user", "content": "hi"}],
        context_management={"edits": []},
      ):
        pass
