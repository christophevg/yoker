"""Tools framework for Yoker.

Provides the tool framework including result types, guardrails, registry,
annotation markers, and context. Built-in tools are in yoker.builtin.
"""

from yoker.tools.annotations import (
  GuardType,
  Query,
  ReadPath,
  Text,
  Url,
  WritePath,
)
from yoker.tools.context import ToolContext
from yoker.tools.guardrails import Guardrail
from yoker.tools.guardrails.path import ReadPathGuardrail, WritePathGuardrail
from yoker.tools.registry import ToolRegistry
from yoker.tools.schema import ToolResult, ValidationResult
from yoker.tools.web import (
  FetchedContent,
  OllamaWebFetchBackend,
  OllamaWebSearchBackend,
  QueryWebGuardrail,
  SearchResult,
  UrlWebGuardrail,
  WebFetchBackend,
  WebFetchError,
  WebGuardrail,
  WebGuardrailConfig,
  WebSearchBackend,
  WebSearchError,
)

__all__ = [
  # Framework
  "ToolResult",
  "ValidationResult",
  "Guardrail",
  "ReadPathGuardrail",
  "WritePathGuardrail",
  "ToolRegistry",
  "ToolContext",
  # Annotations
  "GuardType",
  "Text",
  "ReadPath",
  "WritePath",
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
