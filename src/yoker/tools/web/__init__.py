"""Web-related tool components for Yoker.

Provides backends for web search and fetch, plus guardrails for
web operations.
"""

from yoker.tools.web.backend import (
  OllamaWebFetchBackend,
  OllamaWebSearchBackend,
  WebFetchBackend,
  WebSearchBackend,
)
from yoker.tools.web.guardrail import (
  QueryWebGuardrail,
  UrlWebGuardrail,
  WebGuardrail,
  WebGuardrailConfig,
)
from yoker.tools.web.types import FetchedContent, SearchResult, WebFetchError, WebSearchError

__all__ = [
  # Backends
  "WebSearchBackend",
  "OllamaWebSearchBackend",
  "WebFetchBackend",
  "OllamaWebFetchBackend",
  # Guardrails
  "WebGuardrail",
  "WebGuardrailConfig",
  "QueryWebGuardrail",
  "UrlWebGuardrail",
  # Types
  "SearchResult",
  "WebSearchError",
  "FetchedContent",
  "UrlWebGuardrail",
  "WebFetchError",
]
