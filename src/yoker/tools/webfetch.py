"""Web fetch tool implementation for Yoker.

Provides the ``make_webfetch_tool`` factory that returns a callable for
fetching web content through pluggable backends.
"""

import logging
from typing import Annotated, Any

from yoker.annotations import Url
from yoker.tools.base import ToolResult
from yoker.tools.web_backend import WebFetchBackend
from yoker.tools.web_types import WebFetchError

logger = logging.getLogger(__name__)


def make_webfetch_tool(backend: WebFetchBackend | None = None) -> Any:
  """Create the web fetch tool callable."""

  async def webfetch(
    url: Annotated[str, Url("URL to fetch")],
    content_type: str = "markdown",
    max_size_kb: int = 2048,
  ) -> ToolResult:
    """Fetch content from a web URL."""
    if not url:
      return ToolResult(success=False, error="URL is required")

    url = url.strip()
    if not url:
      return ToolResult(success=False, error="URL cannot be empty or whitespace")

    if content_type not in ("markdown", "text", "html"):
      content_type = "markdown"

    if not isinstance(max_size_kb, int):
      try:
        max_size_kb = int(max_size_kb)
      except (ValueError, TypeError):
        max_size_kb = 2048
    max_size_kb = max(1, min(10240, max_size_kb))

    if backend is None:
      return ToolResult(success=False, error="No backend configured for web fetch")

    try:
      content = await backend.fetch(
        url=url,
        content_type=content_type,
        max_size_kb=max_size_kb,
      )
      return ToolResult(success=True, result=content.to_dict())
    except WebFetchError as e:
      logger.error("Web fetch error: %s", e)
      return ToolResult(success=False, error=str(e))
    except Exception as e:
      logger.error("Unexpected error in web fetch: %s", e)
      return ToolResult(success=False, error=f"Fetch failed: {e}")

  return webfetch


__all__ = ["make_webfetch_tool"]
