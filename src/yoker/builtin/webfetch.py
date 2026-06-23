"""Web fetch tool implementation for Yoker.

Provides the ``webfetch`` async function for fetching web content through
pluggable backends.
"""

from typing import TYPE_CHECKING, Annotated

from structlog import get_logger

from yoker.tools.annotations import Url
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult
from yoker.tools.web import WebFetchError

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


async def webfetch(
  url: Annotated[str, Url("URL to fetch")],
  ctx: ToolContext,
  content_type: str = "markdown",
  max_size_kb: int = 2048,
) -> ToolResult:
  """Fetch content from a web URL."""
  # Get backend from context
  backend = ctx.backends.get("webfetch")

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


__all__ = ["webfetch"]
