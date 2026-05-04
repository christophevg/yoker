"""WebFetchTool implementation.

Provides web content fetching capability using pluggable backends with comprehensive
security guardrails including SSRF protection.
"""

import logging
from typing import TYPE_CHECKING, Any

from .base import Tool, ToolResult
from .web_backend import WebFetchBackend
from .web_guardrail import WebGuardrail
from .web_types import WebFetchError

if TYPE_CHECKING:
  pass

logger = logging.getLogger(__name__)


class WebFetchTool(Tool):
  """Tool for fetching web content using pluggable backends.

  Fetches content from URLs and returns structured results.
  Uses a configurable backend (Ollama native or local httpx).
  Validates URLs through WebGuardrail before execution.

  Example:
    tool = WebFetchTool(backend=OllamaWebFetchBackend(client))
    result = tool.execute(url="https://example.com", content_type="markdown")
  """

  _guardrail: WebGuardrail | None
  _backend: WebFetchBackend | None

  def __init__(
    self,
    backend: WebFetchBackend | None = None,
    guardrail: WebGuardrail | None = None,
  ) -> None:
    """Initialize WebFetchTool with optional backend and guardrail.

    Args:
      backend: Optional backend for web fetch (defaults to None).
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
    return "Fetch content from a web URL"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema.

    Returns:
      Schema with url, content_type, and max_size_kb parameters.
    """
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
              "description": "URL to fetch",
            },
            "content_type": {
              "type": "string",
              "description": "Output format (markdown, text, html)",
              "enum": ["markdown", "text", "html"],
              "default": "markdown",
            },
            "max_size_kb": {
              "type": "integer",
              "description": "Maximum content size in KB",
              "default": 2048,
              "minimum": 1,
              "maximum": 10240,
            },
          },
          "required": ["url"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute web fetch with the given parameters.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate URL parameter.
      3. Delegate to backend for fetch execution.
      4. Return structured results or error.

    Args:
      **kwargs: Must contain 'url', optionally 'content_type', 'max_size_kb'.

    Returns:
      ToolResult with FetchedContent dict or error.
    """
    # Step 1: Extract URL parameter
    url = kwargs.get("url", "")
    if not url:
      return ToolResult(
        success=False,
        result={},
        error="URL is required",
      )

    # Strip whitespace and validate
    url = url.strip()
    if not url:
      return ToolResult(
        success=False,
        result={},
        error="URL cannot be empty or whitespace",
      )

    # Step 2: Extract optional parameters
    content_type = kwargs.get("content_type", "markdown")
    if content_type not in ("markdown", "text", "html"):
      content_type = "markdown"

    max_size_kb = kwargs.get("max_size_kb", 2048)
    if not isinstance(max_size_kb, int):
      try:
        max_size_kb = int(max_size_kb)
      except (ValueError, TypeError):
        max_size_kb = 2048
    max_size_kb = max(1, min(10240, max_size_kb))

    # Step 3: Validate via guardrail
    if self._guardrail:
      validation = self._guardrail.validate_url(url)
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
        error="No backend configured for web fetch",
      )

    # Step 5: Execute fetch
    try:
      content = self._backend.fetch(
        url=url,
        content_type=content_type,
        max_size_kb=max_size_kb,
      )

      return ToolResult(
        success=True,
        result=content.to_dict(),
      )

    except WebFetchError as e:
      logger.error(f"Web fetch error: {e}")
      return ToolResult(
        success=False,
        result={},
        error=str(e),
      )
    except Exception as e:
      logger.error(f"Unexpected error in web fetch: {e}")
      return ToolResult(
        success=False,
        result={},
        error=f"Fetch failed: {e}",
      )


__all__ = [
  "WebFetchTool",
]
