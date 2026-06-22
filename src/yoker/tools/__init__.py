"""Tools framework for Yoker.

Provides the tool framework including result types, guardrails, registry,
annotation markers, and context. Built-in tools are in yoker.builtin.
"""

from yoker.annotations import (
  GuardType,
  Path,
  Query,
  Text,
  Url,
)
from yoker.tools.base import ToolResult, ValidationResult
from yoker.tools.context import ToolContext
from yoker.tools.guardrails import Guardrail
from yoker.tools.path_guardrail import PathGuardrail
from yoker.tools.registry import ToolRegistry
from yoker.tools.web_backend import (
  OllamaWebFetchBackend,
  OllamaWebSearchBackend,
  WebFetchBackend,
  WebSearchBackend,
)
from yoker.tools.web_guardrail import (
  QueryWebGuardrail,
  UrlWebGuardrail,
  WebGuardrail,
  WebGuardrailConfig,
)
from yoker.tools.web_types import FetchedContent, SearchResult, WebFetchError, WebSearchError

__all__ = [
  # Framework
  "ToolResult",
  "ValidationResult",
  "Guardrail",
  "PathGuardrail",
  "ToolRegistry",
  "ToolContext",
  "GuardType",
  "Text",
  "Path",
  "Url",
  "Query",
  # Web framework
  "WebSearchBackend",
  "OllamaWebSearchBackend",
  "WebFetchBackend",
  "OllamaWebFetchBackend",
  "WebGuardrail",
  "WebGuardrailConfig",
  "QueryWebGuardrail",
  "SearchResult",
  "WebSearchError",
  "FetchedContent",
  "UrlWebGuardrail",
  "WebFetchError",
]