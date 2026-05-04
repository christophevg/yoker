"""Web search backend protocol and implementations.

Provides pluggable backend architecture for web search.
"""

import logging
from typing import TYPE_CHECKING, Protocol

from .web_types import SearchResult, WebSearchError

if TYPE_CHECKING:
  from ollama import Client

logger = logging.getLogger(__name__)


class WebSearchBackend(Protocol):
  """Protocol for web search backend implementations.

  Defines the interface that all search backends must implement.
  Supports both synchronous Ollama native tools and async local backends.

  Implementations:
    - OllamaWebSearchBackend: Uses Ollama's native web_search function
    - LocalWebSearchBackend: Uses DDGS library (future)
  """

  def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
    """Execute a web search and return results.

    Args:
      query: Search query string.
      max_results: Maximum number of results to return (1-50).

    Returns:
      List of SearchResult objects.

    Raises:
      WebSearchError: If search fails.
    """
    ...


class OllamaWebSearchBackend:
  """Web search backend using Ollama's native web_search function.

  Uses the Ollama Python SDK's built-in web_search capability.
  Requires an authenticated Client for cloud-based web search.

  Features:
    - Native Ollama SDK integration
    - No model selection needed
    - Built-in result formatting

  Limitations:
    - Requires OLLAMA_API_KEY for cloud-based search
    - Limited to 10 results
    - No domain filtering on client side
  """

  def __init__(self, client: "Client", timeout_seconds: int = 30) -> None:
    """Initialize backend.

    Args:
      client: Authenticated Ollama Client instance.
      timeout_seconds: Request timeout in seconds.
    """
    self._client = client
    self._timeout_seconds = timeout_seconds
    self._backend_name = "ollama"

  def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
    """Execute search via Ollama web_search function.

    Uses client.web_search() which returns structured results directly.

    Args:
      query: Search query string.
      max_results: Maximum results (capped at 10 for Ollama).

    Returns:
      List of SearchResult objects.

    Raises:
      WebSearchError: If Ollama request fails.
    """
    # Cap results at 10 (Ollama hard limit)
    capped_results = min(max_results, 10)

    try:
      # Use client's web_search method
      # Returns WebSearchResponse with .results attribute
      response = self._client.web_search(query, max_results=capped_results)

      # Parse the response into SearchResult objects
      results: list[SearchResult] = []
      for item in response.results:
        results.append(
          SearchResult(
            title=str(item.title or ""),
            url=str(item.url or ""),
            snippet=str(item.content or ""),
            source=self._backend_name,
          )
        )
      # Slice to ensure we don't return more than requested
      return results[:capped_results]

    except ConnectionError as e:
      logger.error(f"Ollama connection error: {e}")
      raise WebSearchError(
        "Failed to connect to Ollama server",
        backend=self._backend_name,
        cause=e,
      ) from e
    except Exception as e:
      error_name = type(e).__name__
      if "Timeout" in error_name:
        logger.error(f"Ollama timeout: {e}")
        raise WebSearchError(
          f"Search timeout after {self._timeout_seconds}s",
          backend=self._backend_name,
          cause=e,
        ) from e
      if "Rate" in error_name or "429" in str(e):
        logger.error(f"Ollama rate limit: {e}")
        raise WebSearchError(
          "Rate limit exceeded, try again later",
          backend=self._backend_name,
          cause=e,
        ) from e
      logger.error(f"Ollama search error: {e}")
      raise WebSearchError(
        f"Search failed: {e}",
        backend=self._backend_name,
        cause=e,
      ) from e


__all__ = [
  "WebSearchBackend",
  "OllamaWebSearchBackend",
]
