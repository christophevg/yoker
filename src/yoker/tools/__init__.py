"""Tools package for Yoker.

Provides the tool framework including result types, guardrails, registry,
annotation markers, and built-in tool factories.
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
from yoker.tools.existence import make_existence_tool
from yoker.tools.git import OPERATION_ARGS, make_git_tool
from yoker.tools.guardrails import Guardrail
from yoker.tools.list import make_list_tool
from yoker.tools.mkdir import make_mkdir_tool
from yoker.tools.path_guardrail import PathGuardrail
from yoker.tools.read import make_read_tool
from yoker.tools.registry import ToolRegistry
from yoker.tools.search import make_search_tool
from yoker.tools.skill import make_skill_tool
from yoker.tools.update import make_update_tool
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
from yoker.tools.webfetch import make_webfetch_tool
from yoker.tools.websearch import make_websearch_tool
from yoker.tools.write import make_write_tool

__all__ = [
  "ToolResult",
  "ValidationResult",
  "Guardrail",
  "PathGuardrail",
  "ToolRegistry",
  "GuardType",
  "Text",
  "Path",
  "Url",
  "Query",
  "make_read_tool",
  "make_list_tool",
  "make_write_tool",
  "make_update_tool",
  "make_search_tool",
  "make_existence_tool",
  "make_mkdir_tool",
  "make_git_tool",
  "make_agent_tool",
  "make_skill_tool",
  "make_websearch_tool",
  "make_webfetch_tool",
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
