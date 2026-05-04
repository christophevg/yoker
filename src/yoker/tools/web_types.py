"""Web search types: SearchResult dataclass and WebSearchError exception.

Provides structured result types for web search operations.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchResult:
  """A single web search result.

  Attributes:
    title: Page title.
    url: Result URL.
    snippet: Short text snippet/summary.
    source: Backend that produced this result (e.g., "ollama", "duckduckgo").
  """

  title: str
  url: str
  snippet: str
  source: str = "unknown"

  def to_dict(self) -> dict[str, str]:
    """Convert SearchResult to dictionary.

    Returns:
      Dictionary with all fields.
    """
    return {
      "title": self.title,
      "url": self.url,
      "snippet": self.snippet,
      "source": self.source,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "SearchResult":
    """Create SearchResult from dictionary.

    Args:
      data: Dictionary with result fields.

    Returns:
      SearchResult instance.
    """
    return cls(
      title=str(data.get("title", "")),
      url=str(data.get("url", "")),
      snippet=str(data.get("snippet", "")),
      source=str(data.get("source", "unknown")),
    )


class WebSearchError(Exception):
  """Base exception for web search errors.

  Attributes:
    message: Human-readable error message.
    backend: Backend that raised the error.
    cause: Original exception if wrapped.
  """

  def __init__(
    self,
    message: str,
    backend: str = "unknown",
    cause: Exception | None = None,
  ) -> None:
    """Initialize error with context.

    Args:
      message: Human-readable error message.
      backend: Backend identifier (e.g., "ollama").
      cause: Original exception if wrapping another error.
    """
    self.message = message
    self.backend = backend
    self.cause = cause
    super().__init__(message)

  def __str__(self) -> str:
    """Return readable string representation.

    Returns:
      Error message with backend context.
    """
    if self.backend != "unknown":
      return f"[{self.backend}] {self.message}"
    return self.message


__all__ = [
  "SearchResult",
  "WebSearchError",
]
