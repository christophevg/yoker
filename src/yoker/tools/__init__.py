"""Tools package for Yoker.

Provides the tool framework including result types, guardrails, registry,
annotation markers, and built-in tools.
"""

from yoker.annotations import (
  GuardType,
  Path,
  Query,
  Text,
  Url,
)
from yoker.tools.agent import make_agent_tool
from yoker.tools.base import ToolResult, ValidationResult
from yoker.tools.context import ToolContext
from yoker.tools.git import OPERATION_ARGS, git
from yoker.tools.guardrails import Guardrail
from yoker.tools.path_guardrail import PathGuardrail
from yoker.tools.registry import ToolRegistry
from yoker.tools.skill import make_skill_tool
from yoker.tools.update import update
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
from yoker.tools.webfetch import webfetch
from yoker.tools.websearch import websearch
from yoker.tools.write import write

__all__ = [
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
  "write",
  "update",
  "git",
  "make_agent_tool",
  "make_skill_tool",
  "websearch",
  "webfetch",
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
  "OPERATION_ARGS",
]
