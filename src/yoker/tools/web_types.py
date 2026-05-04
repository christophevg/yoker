"""Web search types: SearchResult dataclass and WebSearchError exception.

Provides structured result types for web search operations.
"""

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class FetchedContent:
  """Content fetched from a web URL.

  Attributes:
    url: The URL that was fetched.
    title: Page title (extracted or derived).
    content: Fetched content (markdown, text, or original).
    content_type: Content format ("markdown", "text", "html").
    source: Backend that fetched this content ("ollama", "local").
    metadata: Additional metadata (e.g., links, images, word_count).
  """

  url: str
  title: str
  content: str
  content_type: str = "markdown"
  source: str = "unknown"
  metadata: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for ToolResult.

    Returns:
      Dictionary with all fields.
    """
    return {
      "url": self.url,
      "title": self.title,
      "content": self.content,
      "content_type": self.content_type,
      "source": self.source,
      "metadata": self.metadata,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "FetchedContent":
    """Create from dictionary.

    Args:
      data: Dictionary with content fields.

    Returns:
      FetchedContent instance.
    """
    return cls(
      url=str(data.get("url", "")),
      title=str(data.get("title", "")),
      content=str(data.get("content", "")),
      content_type=str(data.get("content_type", "markdown")),
      source=str(data.get("source", "unknown")),
      metadata=dict(data.get("metadata", {})),
    )


class WebFetchError(Exception):
  """Exception for web fetch errors.

  Attributes:
    message: Human-readable error message.
    url: URL that failed (if applicable).
    backend: Backend that raised the error.
    cause: Original exception if wrapped.
    error_type: Type of error (ssrf, timeout, size, invalid_url, etc.).
  """

  def __init__(
    self,
    message: str,
    url: str = "",
    backend: str = "unknown",
    cause: Exception | None = None,
    error_type: str = "unknown",
  ) -> None:
    """Initialize error with context.

    Args:
      message: Human-readable error message.
      url: URL that failed.
      backend: Backend identifier (e.g., "ollama").
      cause: Original exception if wrapping another error.
      error_type: Error type (e.g., "timeout", "size_limit", "ssrf").
    """
    self.message = message
    self.url = url
    self.backend = backend
    self.cause = cause
    self.error_type = error_type
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
  "FetchedContent",
  "WebFetchError",
]
