"""Tests for Agent._tool_backends population (bug M.5).

Verifies that the Agent populates ``_tool_backends`` with
``OllamaWebSearchBackend`` / ``OllamaWebFetchBackend`` instances when the
configured provider is Ollama and an API key is available, so the
``websearch`` / ``webfetch`` built-in tools execute successfully instead of
failing with "No backend configured".

Since the per-call-client refactor, the web backends hold a CLIENT
FACTORY (``OllamaBackend._build_client``) instead of a client instance;
the backend has no client of its own. Execution tests patch the
``AsyncClient`` class, so every constructed client per call is the
shared mock — mirroring the per-call pattern with zero network use.
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.backends.ollama import OllamaBackend
from yoker.config import BackendConfig, Config, OllamaConfig
from yoker.core import Agent
from yoker.core._processing import _build_tool_context
from yoker.tools.web.backend import OllamaWebFetchBackend, OllamaWebSearchBackend


@dataclass
class _MockWebSearchResult:
  """Mock result matching ollama's WebSearchResult structure."""

  title: str
  url: str
  content: str


@dataclass
class _MockWebSearchResponse:
  """Mock response matching ollama's WebSearchResponse structure."""

  results: list[_MockWebSearchResult]


@dataclass
class _MockWebFetchResponse:
  """Mock response matching ollama's WebFetchResponse structure."""

  content: str
  title: str


def _mock_ollama_client() -> MagicMock:
  """Create a mock Ollama AsyncClient usable through the per-call pattern.

  web_search/web_fetch are AsyncMocks; the async context manager protocol
  (used by the web backends as ``async with factory() as client:``) is
  configured via the documented magic-mock pattern so the client yields
  ITSELF inside the with block.
  """
  client = MagicMock()
  client.web_search = AsyncMock(
    return_value=_MockWebSearchResponse(
      results=[
        _MockWebSearchResult(
          title="Result 1",
          url="https://example.com/1",
          content="Snippet 1",
        )
      ]
    )
  )
  client.web_fetch = AsyncMock(
    return_value=_MockWebFetchResponse(
      content="# Fetched Page\nHello world.",
      title="Fetched Page",
    )
  )
  client.__aenter__.return_value = client
  client.__aexit__.return_value = False
  return client


def _ollama_config_with_api_key() -> Config:
  """Return an Ollama-backed config with an API key set."""
  return Config(
    backend=BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(model="test-model", api_key="test-key"),
    )
  )


class TestToolBackendsPopulation:
  """Tests for _tool_backends population during Agent setup."""

  def test_websearch_backend_populated_for_ollama(self) -> None:
    """
    Given: An Agent configured with the Ollama provider and an API key
    When: Inspecting Agent._tool_backends after initialization
    Then: Contains an OllamaWebSearchBackend bound to the backend's factory
    """
    config = _ollama_config_with_api_key()

    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      backend_obj = agent._tool_backends.get("websearch")
      assert isinstance(backend_obj, OllamaWebSearchBackend)
      assert backend_obj._client_factory.__func__ is backend._build_client.__func__

  def test_webfetch_backend_populated_for_ollama(self) -> None:
    """
    Given: An Agent configured with the Ollama provider and an API key
    When: Inspecting Agent._tool_backends after initialization
    Then: Contains an OllamaWebFetchBackend bound to the backend's factory
    """
    config = _ollama_config_with_api_key()

    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      backend_obj = agent._tool_backends.get("webfetch")
      assert isinstance(backend_obj, OllamaWebFetchBackend)
      assert backend_obj._client_factory.__func__ is backend._build_client.__func__

  def test_backends_share_backend_client_factory(self) -> None:
    """
    Given: An Agent built with an explicit Ollama backend
    When: Inspecting the populated web backends
    Then: Both backends reference the backend's _build_client; the
      factory produces a client per call (the patched class construct)
    """
    config = _ollama_config_with_api_key()

    with patch("yoker.backends.ollama.AsyncClient") as client_cls:
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      assert (
        agent._tool_backends["websearch"]._client_factory.__func__ is backend._build_client.__func__
      )
      assert (
        agent._tool_backends["webfetch"]._client_factory.__func__ is backend._build_client.__func__
      )
      # Per-call: every factory call constructs a fresh "client" — the
      # patched class uses side_effect so each call yields a distinct mock.
      client_cls.side_effect = lambda *a, **k: MagicMock()
      first = backend._build_client()
      second = backend._build_client()
      assert first is not second
      assert client_cls.call_count >= 2

  def test_backends_not_populated_without_api_key(self) -> None:
    """
    Given: An Agent configured without an Ollama API key
    When: Inspecting Agent._tool_backends after initialization
    Then: _tool_backends is empty (the web tools are not registered either)
    """
    config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(model="test-model", api_key=""),
      )
    )

    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      assert agent._tool_backends == {}

  def test_websearch_backend_not_populated_when_disabled(self) -> None:
    """
    Given: An Agent with websearch disabled in config
    When: Inspecting Agent._tool_backends after initialization
    Then: No websearch backend is populated
    """
    from dataclasses import replace

    config = _ollama_config_with_api_key()
    config = replace(
      config,
      tools=replace(
        config.tools,
        websearch=replace(config.tools.websearch, enabled=False),
      ),
    )

    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      assert "websearch" not in agent._tool_backends
      # webfetch still populated
      assert isinstance(agent._tool_backends.get("webfetch"), OllamaWebFetchBackend)


class TestWebToolExecutionViaAgent:
  """Tests that the websearch/webfetch tools execute via Agent tool context."""

  @pytest.mark.asyncio
  async def test_websearch_tool_executes_successfully(self) -> None:
    """
    Given: An Agent with populated web backends and a mocked SDK client
    When: Building a ToolContext for websearch and executing the tool
    Then: Returns a successful ToolResult with search results
    """
    from yoker.builtin import websearch
    from yoker.tools import ToolRegistry

    mock_client = _mock_ollama_client()
    config = _ollama_config_with_api_key()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      registry = ToolRegistry()
      spec = registry.register(websearch, name="websearch")

      ctx = _build_tool_context(agent, spec)
      result = await spec.execute(query="test query", ctx=ctx)

      assert result.success
      assert isinstance(result.result, dict)
      assert "results" in result.result
      assert result.result["count"] >= 1
      mock_client.web_search.assert_awaited()

  @pytest.mark.asyncio
  async def test_webfetch_tool_executes_successfully(self) -> None:
    """
    Given: An Agent with populated web backends and a mocked SDK client
    When: Building a ToolContext for webfetch and executing the tool
    Then: Returns a successful ToolResult with fetched content
    """
    from yoker.builtin import webfetch
    from yoker.tools import ToolRegistry

    mock_client = _mock_ollama_client()
    config = _ollama_config_with_api_key()

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      registry = ToolRegistry()
      spec = registry.register(webfetch, name="webfetch")

      ctx = _build_tool_context(agent, spec)
      result = await spec.execute(url="https://example.com", ctx=ctx)

      assert result.success
      assert isinstance(result.result, dict)
      mock_client.web_fetch.assert_awaited()

  @pytest.mark.asyncio
  async def test_websearch_no_backend_when_no_api_key(self) -> None:
    """
    Given: An Agent without an Ollama API key (websearch not registered)
    When: Building a ToolContext for websearch and executing the tool
    Then: Returns an error result mentioning no backend configured
    """
    from yoker.builtin import websearch
    from yoker.tools import ToolRegistry

    mock_client = _mock_ollama_client()
    config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(model="test-model", api_key=""),
      )
    )

    with patch("yoker.backends.ollama.AsyncClient", return_value=mock_client):
      backend = OllamaBackend(config)
      agent = Agent(config=config, backend=backend)

      registry = ToolRegistry()
      spec = registry.register(websearch, name="websearch")

      ctx = _build_tool_context(agent, spec)
      result = await spec.execute(query="test query", ctx=ctx)

      assert not result.success
