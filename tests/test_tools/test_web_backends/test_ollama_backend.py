"""Tests for OllamaWebSearchBackend implementation.

These tests verify the behavior of the Ollama backend for web search,
including result parsing, error handling, and API integration.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from yoker.tools.web_backend import OllamaWebSearchBackend
from yoker.tools.web_types import WebSearchError


@dataclass
class MockWebSearchResult:
  """Mock result matching ollama's WebSearchResult structure."""

  title: str
  url: str
  content: str


@dataclass
class MockWebSearchResponse:
  """Mock response matching ollama's WebSearchResponse structure."""

  results: list[MockWebSearchResult]


def mock_response(items: list[dict[str, str]]) -> MockWebSearchResponse:
  """Create a mock WebSearchResponse from list of dicts."""
  return MockWebSearchResponse(
    results=[
      MockWebSearchResult(title=i.get("title", ""), url=i.get("url", ""), content=i.get("content", ""))
      for i in items
    ]
  )


def create_mock_client(response: MockWebSearchResponse | None = None) -> MagicMock:
  """Create a mock Ollama Client with web_search method."""
  client = MagicMock()
  client.web_search = MagicMock(return_value=response or mock_response([]))
  return client


class TestOllamaWebSearchBackendSchema:
  """Tests for OllamaWebSearchBackend initialization and configuration."""

  def test_initialization_with_client(self) -> None:
    """
    Given: Creating OllamaWebSearchBackend with a client
    When: Initializing the backend
    Then: Creates backend with client and default settings
    """
    client = create_mock_client()
    backend = OllamaWebSearchBackend(client=client)

    assert backend._backend_name == "ollama"
    assert backend._timeout_seconds == 30
    assert backend._client is client

  def test_custom_timeout(self) -> None:
    """
    Given: Creating OllamaWebSearchBackend with custom timeout
    When: Initializing the backend
    Then: Uses provided timeout
    """
    client = create_mock_client()
    backend = OllamaWebSearchBackend(client=client, timeout_seconds=60)

    assert backend._timeout_seconds == 60

  def test_backend_type_is_ollama(self) -> None:
    """
    Given: An OllamaWebSearchBackend instance
    When: Checking backend type/identifier
    Then: Returns 'ollama' as backend identifier
    """
    client = create_mock_client()
    backend = OllamaWebSearchBackend(client=client)

    assert backend._backend_name == "ollama"


class TestOllamaWebSearchBackendSearch:
  """Tests for OllamaWebSearchBackend.search() method."""

  def test_search_returns_list_of_results(self) -> None:
    """
    Given: A backend with mocked client
    When: Calling search() with valid query
    Then: Returns list of SearchResult objects
    """
    client = create_mock_client(mock_response([
      {"title": "Result 1", "url": "https://example.com/1", "content": "Content 1"}
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query")

    assert isinstance(results, list)
    assert len(results) == 1

  def test_search_result_has_required_fields(self) -> None:
    """
    Given: A backend with mocked client
    When: Getting search results
    Then: Each SearchResult has title, url, snippet, source fields
    """
    client = create_mock_client(mock_response([
      {"title": "Test", "url": "https://example.com", "content": "Snippet"}
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query")

    for result in results:
      assert hasattr(result, "title")
      assert hasattr(result, "url")
      assert hasattr(result, "snippet")
      assert hasattr(result, "source")

  def test_search_result_source_is_ollama(self) -> None:
    """
    Given: Ollama backend returning results
    When: Getting search results
    Then: source field is 'ollama' for all results
    """
    client = create_mock_client(mock_response([
      {"title": "Test", "url": "https://example.com", "content": "Content"}
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query")

    for result in results:
      assert result.source == "ollama"

  def test_search_with_default_max_results(self) -> None:
    """
    Given: A backend with mocked client
    When: Calling search() without max_results
    Then: Returns up to 10 results (Ollama default)
    """
    client = create_mock_client(mock_response([
      {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": f"Content {i}"}
      for i in range(15)
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query")

    assert len(results) == 10  # Capped at 10

  def test_search_with_custom_max_results(self) -> None:
    """
    Given: A backend with mocked client
    When: Calling search() with max_results=5
    Then: Returns only 5 results
    """
    client = create_mock_client(mock_response([
      {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": f"Content {i}"}
      for i in range(10)
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query", max_results=5)

    assert len(results) == 5

  def test_search_caps_at_10_results(self) -> None:
    """
    Given: Ollama returns more than 10 results
    When: Calling search() with max_results=20
    Then: Returns only 10 results (Ollama hard limit)
    """
    client = create_mock_client(mock_response([
      {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": f"Content {i}"}
      for i in range(20)
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query", max_results=20)

    assert len(results) == 10  # Hard cap at 10

  def test_search_empty_results(self) -> None:
    """
    Given: Ollama returns empty list
    When: Calling search()
    Then: Returns empty list
    """
    client = create_mock_client(mock_response([]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test query")

    assert results == []

  def test_search_preserves_query(self) -> None:
    """
    Given: A backend with mocked client
    When: Calling search() with specific query
    Then: Passes query to client.web_search
    """
    client = create_mock_client(mock_response([]))
    backend = OllamaWebSearchBackend(client=client)
    backend.search(query="Python asyncio tutorial")

    client.web_search.assert_called_once_with("Python asyncio tutorial", max_results=10)


class TestOllamaWebSearchBackendErrorHandling:
  """Tests for error handling in OllamaWebSearchBackend."""

  def test_ollama_connection_error(self) -> None:
    """
    Given: A backend with mocked client that fails to connect
    When: Calling search()
    Then: Raises WebSearchError with connection message
    """
    client = create_mock_client()
    client.web_search.side_effect = ConnectionError("Connection refused")
    backend = OllamaWebSearchBackend(client=client)

    with pytest.raises(WebSearchError) as exc_info:
      backend.search(query="test query")

    assert "connect" in str(exc_info.value).lower()

  def test_ollama_timeout_error(self) -> None:
    """
    Given: A backend with mocked client that times out
    When: Calling search()
    Then: Raises WebSearchError with timeout message
    """
    client = create_mock_client()
    client.web_search.side_effect = TimeoutError("Request timed out")
    backend = OllamaWebSearchBackend(client=client)

    with pytest.raises(WebSearchError) as exc_info:
      backend.search(query="test query")

    assert "timeout" in str(exc_info.value).lower()

  def test_ollama_rate_limit_error(self) -> None:
    """
    Given: A backend with mocked client that returns rate limit error
    When: Calling search()
    Then: Raises WebSearchError with rate limit message
    """
    client = create_mock_client()
    client.web_search.side_effect = Exception("429 Rate Limited")
    backend = OllamaWebSearchBackend(client=client)

    with pytest.raises(WebSearchError) as exc_info:
      backend.search(query="test query")

    assert "rate limit" in str(exc_info.value).lower()

  def test_ollama_error_includes_backend_name(self) -> None:
    """
    Given: A backend with mocked client that raises error
    When: Catching WebSearchError
    Then: Error includes backend name
    """
    client = create_mock_client()
    client.web_search.side_effect = Exception("Unknown error")
    backend = OllamaWebSearchBackend(client=client)

    with pytest.raises(WebSearchError) as exc_info:
      backend.search(query="test query")

    assert exc_info.value.backend == "ollama"


class TestOllamaWebSearchBackendResultParsing:
  """Tests for parsing Ollama web_search results."""

  def test_handles_unicode_in_results(self) -> None:
    """
    Given: A backend with mocked client returning Unicode text
    When: Calling search()
    Then: Preserves Unicode characters in SearchResult fields
    """
    client = create_mock_client(mock_response([
      {
        "title": "Pythön 中文 文档",
        "url": "https://example.com/python-中文",
        "content": "Python异步编程最佳实践 🐍",
      }
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test")

    assert len(results) > 0
    assert "中文" in results[0].title or "中文" in results[0].snippet

  def test_handles_empty_url_in_result(self) -> None:
    """
    Given: A backend with mocked client returning result with empty URL
    When: Calling search()
    Then: Returns result with empty URL (graceful handling)
    """
    client = create_mock_client(mock_response([
      {"title": "Result with empty URL", "url": "", "content": "This result has no URL"}
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test")

    assert isinstance(results, list)
    assert results[0].url == ""

  def test_handles_long_snippets(self) -> None:
    """
    Given: A backend with mocked client returning very long snippets
    When: Calling search()
    Then: Returns results (snippets may be truncated or kept as-is)
    """
    long_content = "A" * 10000
    client = create_mock_client(mock_response([
      {"title": "Long Result", "url": "https://example.com", "content": long_content}
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="test")

    assert isinstance(results, list)
    # Should handle long content gracefully


class TestOllamaWebSearchBackendTimeout:
  """Tests for timeout configuration."""

  def test_default_timeout_applied(self) -> None:
    """
    Given: Creating backend without explicit timeout
    When: Checking timeout configuration
    Then: Uses default 30 seconds
    """
    client = create_mock_client()
    backend = OllamaWebSearchBackend(client=client)

    assert backend._timeout_seconds == 30

  def test_custom_timeout_applied(self) -> None:
    """
    Given: Creating backend with custom timeout
    When: Checking timeout configuration
    Then: Uses provided timeout
    """
    client = create_mock_client()
    backend = OllamaWebSearchBackend(client=client, timeout_seconds=60)

    assert backend._timeout_seconds == 60


class TestOllamaWebSearchBackendIntegration:
  """Integration tests for OllamaWebSearchBackend."""

  def test_real_ollama_client_format(self) -> None:
    """
    Given: A backend with mocked client returning typical format
    When: Calling search()
    Then: Parses results correctly
    """
    # Typical Ollama web_search response format
    client = create_mock_client(mock_response([
      {
        "title": "Python Asyncio Tutorial",
        "url": "https://docs.python.org/3/library/asyncio.html",
        "content": "Official Python asyncio documentation",
      },
      {
        "title": "Async IO in Python: A Complete Walkthrough",
        "url": "https://realpython.com/async-io-python/",
        "content": "Real Python tutorial on async programming",
      },
    ]))
    backend = OllamaWebSearchBackend(client=client)
    results = backend.search(query="Python asyncio", max_results=2)

    assert len(results) == 2
    assert "Python" in results[0].title
    assert "async" in results[1].url.lower()
