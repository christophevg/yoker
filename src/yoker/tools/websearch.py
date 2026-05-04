"""WebSearchTool implementation.

Provides web search capability using pluggable backends with comprehensive
security guardrails.
"""

import logging
from typing import TYPE_CHECKING, Any

from .base import Tool, ToolResult
from .web_backend import WebSearchBackend
from .web_guardrail import WebGuardrail
from .web_types import WebSearchError

if TYPE_CHECKING:
  pass

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
  """Tool for searching the web using pluggable backends.

  Searches the web for information and returns structured results.
  Uses a configurable backend (Ollama native or local DDGS).
  Validates queries through WebGuardrail before execution.

  Example:
    tool = WebSearchTool(backend=OllamaWebSearchBackend())
    result = tool.execute(query="Python async best practices", max_results=5)
  """

  def __init__(
    self,
    backend: WebSearchBackend | None = None,
    guardrail: WebGuardrail | None = None,
  ) -> None:
    """Initialize WebSearchTool with optional backend and guardrail.

    Args:
      backend: Optional backend for web search (defaults to None).
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
    return "Search the web for information"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema.

    Returns:
      Schema with query and max_results parameters.
    """
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
              "description": "Search query",
            },
            "max_results": {
              "type": "integer",
              "description": "Maximum number of results to return",
              "default": 10,
              "minimum": 1,
              "maximum": 50,
            },
          },
          "required": ["query"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute web search with the given parameters.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate query parameter.
      3. Delegate to backend for search execution.
      4. Return structured results or error.

    Args:
      **kwargs: Must contain 'query', optionally 'max_results'.

    Returns:
      ToolResult with list of SearchResult dicts or error.
    """
    # Step 1: Extract query parameter
    query = kwargs.get("query", "")
    if not query:
      return ToolResult(
        success=False,
        result={},
        error="Query is required",
      )

    # Check for empty or whitespace query
    if isinstance(query, str):
      stripped_query = query.strip()
      if not stripped_query:
        return ToolResult(
          success=False,
          result={},
          error="Query cannot be empty or whitespace",
        )

    # Step 2: Extract max_results parameter
    max_results = kwargs.get("max_results", 10)
    if not isinstance(max_results, int):
      try:
        max_results = int(max_results)
      except (ValueError, TypeError):
        max_results = 10

    # Clamp max_results to valid range
    max_results = max(1, min(50, max_results))

    # Step 3: Validate via guardrail
    if self._guardrail:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        return ToolResult(
          success=False,
          result={},
          error=validation.reason,
        )

    # Step 4: Check backend
    if self._backend is None:
      return ToolResult(
        success=False,
        result={},
        error="No backend configured for web search",
      )

    # Step 5: Execute search
    try:
      results = self._backend.search(query=query, max_results=max_results)

      # Convert SearchResult objects to dicts for ToolResult
      results_list = [r.to_dict() for r in results]

      return ToolResult(
        success=True,
        result={"results": results_list, "count": len(results_list)},
      )

    except WebSearchError as e:
      logger.error(f"Web search error: {e}")
      return ToolResult(
        success=False,
        result={},
        error=str(e),
      )
    except Exception as e:
      logger.error(f"Unexpected error in web search: {e}")
      return ToolResult(
        success=False,
        result={},
        error=f"Search failed: {e}",
      )


__all__ = [
  "WebSearchTool",
]
