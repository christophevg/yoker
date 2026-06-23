"""Tests for webfetch tool implementation.

These tests verify the behavior of the webfetch tool, including backend integration,
URL validation, SSRF protection, domain filtering, and error handling.
"""

from yoker.builtin import webfetch
from yoker.config import Config
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext


def _webfetch_spec():
  """Create and register the webfetch tool."""
  registry = ToolRegistry()
  return registry.register(webfetch, name="webfetch")


def _webfetch_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for webfetch tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.webfetch,
    shared=config.tools_shared,
    backends={},
  )


def _get_ctx(backend=None) -> ToolContext | None:
  """Create a ToolContext with optional backend for testing."""
  if backend is None:
    return None
  return ToolContext(
    config=Config().tools.webfetch,
    shared=Config().tools_shared,
    backends={"webfetch": backend},
  )
