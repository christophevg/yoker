"""Async versions of WebSearch and WebFetch tools.

These tools use AsyncClient for non-blocking operation in async contexts.
"""

import logging
from typing import TYPE_CHECKING, Any

from .base import Tool, ToolResult
from .web_guardrail import WebGuardrail
from .web_types import FetchedContent, SearchResult, WebFetchError, WebSearchError

if TYPE_CHECKING:
  from ollama import AsyncClient

logger = logging.getLogger(__name__)


class AsyncWebSearchTool(Tool):
  """Async tool for searching the web using Ollama's native web_search.

  Uses AsyncClient for non-blocking operation. Requires OLLAMA_API_KEY
  for cloud-based search.

  Example:
    tool = AsyncWebSearchTool(backend=AsyncOllamaWebSearchBackend(client))
    result = await tool.execute_async(query="Python async", max_results=5)
  """

  def __init__(
    self,
    backend: "AsyncOllamaWebSearchBackend",
    guardrail: WebGuardrail | None = None,
  ) -> None:
    """Initialize AsyncWebSearchTool.

    Args:
      backend: Async backend for web search.
      guardrail: Optional guardrail for query validation.
    """
    super().__init__(guardrail=guardrail)
    self._backend = backend

  @property
  def name(self) -> str:
    """Tool name used for registration."""
    return "web_search"

  @property
  def description(self) -> str:
    """Tool description shown to the LLM."""
    return "Search the web for information. Returns a list of search results."

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible function schema."""
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "The search query.",
            },
            "max_results": {
              "type": "integer",
              "description": "Maximum number of results to return (1-10).",
              "default": 5,
            },
          },
          "required": ["query"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute is not supported for async tools.

    Use execute_async() instead.
    """
    raise RuntimeError("AsyncWebSearchTool requires async execution. Use execute_async().")

  async def execute_async(self, query: str, max_results: int = 5) -> ToolResult:
    """Execute async web search.

    Args:
      query: Search query string.
      max_results: Maximum results (1-10).

    Returns:
      ToolResult with search results.
    """
    # Validate query through guardrail
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, {"query": query})
      if not validation.valid:
        return ToolResult(success=False, result={}, error=validation.reason)

    try:
      results = await self._backend.search(query, max_results=max_results)

      # Format results for display
      formatted = []
      for r in results:
        formatted.append(f"**{r.title}**\n{r.url}\n{r.snippet}")

      return ToolResult(
        success=True,
        result="\n\n".join(formatted),
        content_metadata={
          "operation": "search",
          "content_type": "summary",
          "metadata": {"result_count": len(results)},
        },
      )
    except WebSearchError as e:
      return ToolResult(success=False, result={}, error=str(e))


class AsyncOllamaWebSearchBackend:
  """Async web search backend using Ollama's native web_search function.

  Uses AsyncClient for non-blocking operation.
  """

  def __init__(self, client: "AsyncClient", timeout_seconds: int = 30) -> None:
    """Initialize async backend.

    Args:
      client: AsyncClient instance.
      timeout_seconds: Request timeout in seconds.
    """
    self._client = client
    self._timeout_seconds = timeout_seconds
    self._backend_name = "ollama"

  async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
    """Execute async search via Ollama web_search function.

    Args:
      query: Search query string.
      max_results: Maximum results (capped at 10).

    Returns:
      List of SearchResult objects.

    Raises:
      WebSearchError: If search fails.
    """
    capped_results = min(max_results, 10)

    try:
      response = await self._client.web_search(query, max_results=capped_results)

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
      return results[:capped_results]

    except Exception as e:
      error_name = type(e).__name__
      if "Timeout" in error_name:
        raise WebSearchError(
          f"Search timeout after {self._timeout_seconds}s",
          backend=self._backend_name,
          cause=e,
        ) from e
      raise WebSearchError(
        f"Search failed: {e}",
        backend=self._backend_name,
        cause=e,
      ) from e


class AsyncWebFetchTool(Tool):
  """Async tool for fetching web content using Ollama's native web_fetch.

  Uses AsyncClient for non-blocking operation. Requires OLLAMA_API_KEY
  for cloud-based fetch.

  Example:
    tool = AsyncWebFetchTool(backend=AsyncOllamaWebFetchBackend(client))
    result = await tool.execute_async(url="https://example.com")
  """

  def __init__(
    self,
    backend: "AsyncOllamaWebFetchBackend",
    guardrail: WebGuardrail | None = None,
  ) -> None:
    """Initialize AsyncWebFetchTool.

    Args:
      backend: Async backend for web fetch.
      guardrail: Optional guardrail for URL validation.
    """
    super().__init__(guardrail=guardrail)
    self._backend = backend

  @property
  def name(self) -> str:
    """Tool name used for registration."""
    return "web_fetch"

  @property
  def description(self) -> str:
    """Tool description shown to the LLM."""
    return "Fetch content from a web URL. Returns extracted and formatted content."

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible function schema."""
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "url": {
              "type": "string",
              "description": "The URL to fetch content from.",
            },
          },
          "required": ["url"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute is not supported for async tools.

    Use execute_async() instead.
    """
    raise RuntimeError("AsyncWebFetchTool requires async execution. Use execute_async().")

  async def execute_async(self, url: str) -> ToolResult:
    """Execute async web fetch.

    Args:
      url: URL to fetch.

    Returns:
      ToolResult with fetched content.
    """
    # Validate URL through guardrail
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, {"url": url})
      if not validation.valid:
        return ToolResult(success=False, result={}, error=validation.reason)

    try:
      content = await self._backend.fetch(url)

      return ToolResult(
        success=True,
        result=f"**{content.title}**\n\n{content.content}",
        content_metadata={
          "operation": "fetch",
          "path": url,
          "content_type": "markdown",
          "content": content.content,
          "metadata": {"size_kb": content.metadata.get("size_kb", 0)},
        },
      )
    except WebFetchError as e:
      return ToolResult(success=False, result={}, error=str(e))


class AsyncOllamaWebFetchBackend:
  """Async web fetch backend using Ollama's native web_fetch function.

  Uses AsyncClient for non-blocking operation.
  """

  def __init__(
    self,
    client: "AsyncClient",
    timeout_seconds: int = 30,
    max_size_kb: int = 2048,
  ) -> None:
    """Initialize async backend.

    Args:
      client: AsyncClient instance.
      timeout_seconds: Default fetch timeout in seconds.
      max_size_kb: Default maximum content size in KB.
    """
    self._client = client
    self._timeout_seconds = timeout_seconds
    self._max_size_kb = max_size_kb
    self._backend_name = "ollama"

  async def fetch(
    self,
    url: str,
    *,
    content_type: str = "markdown",
    max_size_kb: int | None = None,
    timeout_seconds: int | None = None,
  ) -> FetchedContent:
    """Fetch content via async Ollama web_fetch function.

    Args:
      url: URL to fetch.
      content_type: Output format (default "markdown").
      max_size_kb: Max content size (uses default if None).
      timeout_seconds: Timeout (uses default if None).

    Returns:
      FetchedContent with extracted content.

    Raises:
      WebFetchError: If fetch fails.
    """
    max_size = max_size_kb or self._max_size_kb

    try:
      response = await self._client.web_fetch(url)

      content = str(response.content or "")
      title = str(response.title or "")

      content_size_kb = len(content.encode("utf-8")) / 1024
      if content_size_kb > max_size:
        raise WebFetchError(
          f"Content size ({content_size_kb:.1f}KB) exceeds limit ({max_size}KB)",
          url=url,
          backend=self._backend_name,
          error_type="size_limit",
        )

      return FetchedContent(
        url=url,
        title=title,
        content=content,
        content_type=content_type,
        source=self._backend_name,
        metadata={"size_kb": content_size_kb},
      )

    except WebFetchError:
      raise
    except Exception as e:
      raise WebFetchError(
        f"Fetch failed: {e}",
        url=url,
        backend=self._backend_name,
        cause=e,
        error_type="unknown",
      ) from e


__all__ = [
  "AsyncWebSearchTool",
  "AsyncOllamaWebSearchBackend",
  "AsyncWebFetchTool",
  "AsyncOllamaWebFetchBackend",
]
