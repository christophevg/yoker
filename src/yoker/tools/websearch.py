"""Web search tool implementation for Yoker.

Provides the ``make_websearch_tool`` factory that returns a callable for
searching the web through pluggable backends.
"""

import logging
from typing import Annotated, Any

from yoker.annotations import Query
from yoker.tools.base import ToolResult
from yoker.tools.web_backend import WebSearchBackend
from yoker.tools.web_types import WebSearchError

logger = logging.getLogger(__name__)


def make_websearch_tool(backend: WebSearchBackend | None = None) -> Any:
  """Create the web search tool callable."""

  async def websearch(
    query: Annotated[str, Query("Search query")],
    max_results: int = 10,
  ) -> ToolResult:
    """Search the web for information."""
    if not query:
      return ToolResult(success=False, error="Query is required")

    if isinstance(query, str):
      if not query.strip():
        return ToolResult(success=False, error="Query cannot be empty or whitespace")

    if not isinstance(max_results, int):
      try:
        max_results = int(max_results)
      except (ValueError, TypeError):
        max_results = 10

    max_results = max(1, min(50, max_results))

    if backend is None:
      return ToolResult(success=False, error="No backend configured for web search")

    try:
      results = await backend.search(query=query, max_results=max_results)
      results_list = [r.to_dict() for r in results]
      return ToolResult(
        success=True,
        result={"results": results_list, "count": len(results_list)},
      )
    except WebSearchError as e:
      logger.error("Web search error: %s", e)
      return ToolResult(success=False, error=str(e))
    except Exception as e:
      logger.error("Unexpected error in web search: %s", e)
      return ToolResult(success=False, error=f"Search failed: {e}")

  return websearch


__all__ = ["make_websearch_tool"]
