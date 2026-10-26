"""Tests for websearch tool implementation.

These tests verify the behavior of the websearch tool, including backend integration,
parameter validation, result formatting, and error handling.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.builtin import websearch
from yoker.config import Config, ToolsConfig, WebSearchToolConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.web.backend import WebSearchBackend
from yoker.tools.web.guardrail import WebGuardrail, WebGuardrailConfig
from yoker.tools.web.types import SearchResult, WebSearchError


def _websearch_spec():
  """Create and register the websearch tool."""
  registry = ToolRegistry()
  return registry.register(websearch, name="websearch")


def _websearch_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for websearch tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.websearch,
    shared=config.tools_shared,
    backends={},
  )


def _get_ctx(backend=None) -> ToolContext | None:
  """Get ToolContext for tests that need backend."""
  from yoker.config import ToolsSharedConfig

  if backend:
    return ToolContext(
      config=None,
      shared=ToolsSharedConfig(),
      backends={"websearch": backend},
    )
  return None


class TestWebSearchToolSchema:
  """Tests for websearch tool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A websearch tool spec
    When: Checking the spec name
    Then: Returns 'websearch'
    """
    spec = _websearch_spec()
    assert spec.name == "websearch"

  def test_description(self) -> None:
    """
    Given: A websearch tool spec
    When: Checking the spec description
    Then: Returns description mentioning web search
    """
    spec = _websearch_spec()
    assert "web" in spec.description.lower()
    assert "search" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """
    Given: A websearch tool spec
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with query and max_results parameters
    """
    spec = _websearch_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert "function" in schema
    assert "parameters" in schema["function"]
    assert "properties" in schema["function"]["parameters"]

  def test_schema_query_required(self) -> None:
    """
    Given: The websearch tool schema
    When: Checking required parameters
    Then: 'query' is required, 'max_results' is optional
    """
    spec = _websearch_spec()
    schema = spec.schema

    required = schema["function"]["parameters"]["required"]
    assert "query" in required
    assert "max_results" not in required


class TestWebSearchToolExecution:
  """Tests for websearch tool execute method."""

  @pytest.mark.asyncio
  async def test_execute_returns_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A websearch tool with mocked backend
    When: Executing a valid search query
    Then: Returns ToolResult with search results
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    result = await spec.execute(query="test query", ctx=ctx)

    assert result.success
    assert "results" in result.result

  @pytest.mark.asyncio
  async def test_execute_with_default_max_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A websearch tool with mocked backend
    When: Executing search without max_results parameter
    Then: Uses default max_results value (10)
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    await spec.execute(query="test query", ctx=ctx)

    # Check that backend was called with default max_results=10
    mock_backend.search.assert_called_once()
    call_args = mock_backend.search.call_args
    assert (
      call_args.kwargs.get("max_results", call_args.args[1] if len(call_args.args) > 1 else 10)
      == 10
    )

  @pytest.mark.asyncio
  async def test_execute_with_custom_max_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A websearch tool with mocked backend
    When: Executing search with max_results=5
    Then: Passes max_results=5 to backend
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    await spec.execute(query="test query", max_results=5, ctx=ctx)

    mock_backend.search.assert_called_once()
    call_kwargs = mock_backend.search.call_args.kwargs
    assert call_kwargs.get("max_results") == 5

  @pytest.mark.asyncio
  async def test_execute_query_required(self) -> None:
    """
    Given: A websearch tool execute call with empty query
    When: Calling execute with empty query string
    Then: Returns error ToolResult
    """
    spec = _websearch_spec()
    ctx = _websearch_context()
    result = await spec.execute(query="", ctx=ctx)

    assert not result.success
    assert result.error is not None
    assert "query" in result.error.lower()

  @pytest.mark.asyncio
  async def test_execute_empty_query_rejected(self) -> None:
    """
    Given: A websearch tool execute call with empty query
    When: Calling execute with query=""
    Then: Returns error ToolResult
    """
    spec = _websearch_spec()
    ctx = _websearch_context()
    result = await spec.execute(query="", ctx=ctx)

    assert not result.success
    assert result.error is not None

  @pytest.mark.asyncio
  async def test_execute_whitespace_query_rejected(self) -> None:
    """
    Given: A websearch tool execute call with whitespace-only query
    When: Calling execute with query="   "
    Then: Returns error ToolResult
    """
    spec = _websearch_spec()
    ctx = _websearch_context()
    result = await spec.execute(query="   ", ctx=ctx)

    assert not result.success
    assert result.error is not None

  @pytest.mark.asyncio
  async def test_execute_clamps_max_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A websearch tool with max_results=100 (exceeds maximum)
    When: Executing search
    Then: Clamps max_results to 50
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    await spec.execute(query="test query", max_results=100, ctx=ctx)

    call_kwargs = mock_backend.search.call_args.kwargs
    assert call_kwargs.get("max_results") == 50

  @pytest.mark.asyncio
  async def test_execute_guardrail_validation_failure(self) -> None:
    """
    Given: A web query guardrail that rejects blocked domains
    When: Validating a query containing a blocked domain
    Then: Guardrail reports the blocked domain
    """
    guardrail = WebGuardrail(WebGuardrailConfig(domain_blocklist=("blocked.com",)))
    spec = _websearch_spec()
    _websearch_context()

    validation = guardrail.validate(spec.name, {"query": "site:blocked.com secret data"})

    assert not validation.valid
    assert validation.reason is not None


class TestWebSearchToolBackendIntegration:
  """Tests for websearch tool backend integration."""

  @pytest.mark.asyncio
  async def test_backend_receives_valid_parameters(self, mock_backend: MagicMock) -> None:
    """
    Given: A websearch tool with mocked backend
    When: Executing search with valid parameters
    Then: Backend.search() receives validated query and max_results
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    await spec.execute(query="test query", max_results=5, ctx=ctx)

    mock_backend.search.assert_called_once_with(query="test query", max_results=5)

  @pytest.mark.asyncio
  async def test_backend_error_returns_error_result(self, mock_backend_error: MagicMock) -> None:
    """
    Given: A backend that raises WebSearchError
    When: Executing search
    Then: Returns error ToolResult with backend error message
    """
    mock_backend_error.search = AsyncMock(
      side_effect=WebSearchError("Backend unavailable", backend="test")
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend_error)
    result = await spec.execute(query="test query", ctx=ctx)

    assert not result.success
    assert result.error is not None

  @pytest.mark.asyncio
  async def test_backend_timeout_returns_error_result(
    self, mock_backend_timeout: MagicMock
  ) -> None:
    """
    Given: A backend that times out
    When: Executing search
    Then: Returns error ToolResult with timeout message
    """
    mock_backend_timeout.search = AsyncMock(
      side_effect=WebSearchError("Search timeout after 30s", backend="test")
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend_timeout)
    result = await spec.execute(query="test query", ctx=ctx)

    assert not result.success
    assert result.error is not None


class TestWebSearchToolResultFormat:
  """Tests for websearch tool result formatting."""

  @pytest.mark.asyncio
  async def test_success_result_format(self, mock_backend: MagicMock) -> None:
    """
    Given: A successful web search
    When: Checking the ToolResult
    Then: success=True, result contains formatted search results
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    result = await spec.execute(query="test query", ctx=ctx)

    assert result.success
    assert isinstance(result.result, dict)
    assert "results" in result.result
    assert "count" in result.result

  @pytest.mark.asyncio
  async def test_error_result_format(self) -> None:
    """
    Given: A failed web search
    When: Checking the ToolResult
    Then: success=False, result is empty, error contains message
    """
    spec = _websearch_spec()
    ctx = _websearch_context()
    result = await spec.execute(query="", ctx=ctx)  # Empty query

    assert not result.success
    assert result.result == ""
    assert result.error is not None

  @pytest.mark.asyncio
  async def test_empty_results_returns_empty_list(self, mock_backend_empty: MagicMock) -> None:
    """
    Given: A backend that returns empty results
    When: Executing search
    Then: Returns success with empty results list
    """
    mock_backend_empty.search = AsyncMock(return_value=[])
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend_empty)
    result = await spec.execute(query="test query", ctx=ctx)

    assert result.success
    assert result.result["results"] == []
    assert result.result["count"] == 0


class TestWebSearchToolConfiguration:
  """Tests for websearch tool configuration."""

  @pytest.mark.asyncio
  async def test_custom_backend_used(self, mock_backend: MagicMock) -> None:
    """
    Given: Creating websearch tool with custom backend
    When: Executing search
    Then: Uses provided backend instead of default
    """
    mock_backend.search = AsyncMock(
      return_value=[
        SearchResult(title="Test", url="http://test.com", snippet="Test snippet", source="ollama")
      ]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    await spec.execute(query="test query", ctx=ctx)

    mock_backend.search.assert_called_once()

  @pytest.mark.asyncio
  async def test_no_backend_returns_error(self) -> None:
    """
    Given: websearch tool without backend configured
    When: Executing search
    Then: Returns error about missing backend
    """
    spec = _websearch_spec()
    ctx = _websearch_context()
    result = await spec.execute(query="test query", ctx=ctx)

    assert not result.success
    assert "backend" in result.error.lower()


# Fixtures


@pytest.fixture
def mock_backend() -> MagicMock:
  """Mock WebSearchBackend that returns sample results."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search = AsyncMock(
    return_value=[
      SearchResult(
        title="Result 1", url="https://example.com/1", snippet="Snippet 1", source="test"
      ),
      SearchResult(
        title="Result 2", url="https://example.com/2", snippet="Snippet 2", source="test"
      ),
    ]
  )
  return backend


# T7 (websearch): output-size protection — snippet cap, byte budget, hint.


def _config_with_budget(kb: int) -> Config:
  """Build a Config with the websearch tool's max_output_kb set."""
  return Config(tools=ToolsConfig(websearch=WebSearchToolConfig(max_output_kb=kb)))


def _giant_results(n: int, snippet_len: int = 2000) -> list[SearchResult]:
  """Build n SearchResult objects with oversized snippets."""
  return [
    SearchResult(
      title=f"Result {i}",
      url=f"https://example.com/{i}",
      snippet="x" * snippet_len,
      source="test",
    )
    for i in range(n)
  ]


class TestWebSearchOutputBudget:
  """Output-size protection for websearch: snippet cap, byte budget, hint."""

  @pytest.mark.asyncio
  async def test_giant_snippet_capped(self, mock_backend: MagicMock) -> None:
    """Given a backend returning a giant snippet, when executed,
    Then the snippet is elided at MAX_SNIPPET_CHARS with a marker."""
    from yoker.builtin.websearch import MAX_SNIPPET_CHARS

    mock_backend.search = AsyncMock(
      return_value=[SearchResult(title="T", url="https://x.com", snippet="y" * 5000, source="t")]
    )
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    result = await spec.execute(query="test", ctx=ctx)

    assert result.success
    snippet = result.result["results"][0]["snippet"]
    assert len(snippet) <= MAX_SNIPPET_CHARS + 120  # marker adds ~100 chars
    assert "chars truncated" in snippet
    assert "webfetch" in snippet

  @pytest.mark.asyncio
  async def test_normal_snippet_not_capped(self, mock_backend: MagicMock) -> None:
    """Given normal-length snippets, when executed,
    Then they pass through unchanged (no marker)."""
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    result = await spec.execute(query="test", ctx=ctx)

    assert result.success
    assert result.result["results"][0]["snippet"] == "Snippet 1"
    assert result.result["results"][1]["snippet"] == "Snippet 2"

  @pytest.mark.asyncio
  async def test_budget_stops_inclusion_and_sets_truncated(self, mock_backend: MagicMock) -> None:
    """Given a tiny budget and 20 giant-snippet results, when executed,
    Then inclusion stops early, truncated=True, hint present,
    And the result stays under the budget (backstop never false-trips)."""
    mock_backend.search = AsyncMock(return_value=_giant_results(20))
    spec = _websearch_spec()
    ctx = ToolContext(
      config=_config_with_budget(5).tools.websearch,
      shared=Config().tools_shared,
      backends={"websearch": mock_backend},
    )
    result = await spec.execute(query="test", ctx=ctx)

    assert result.success
    assert result.result["truncated"] is True
    assert result.result["count"] < 20
    assert result.result["total_hits"] == 20
    assert "output-size budget" in result.result["hint"]
    assert len(str(result.result).encode("utf-8")) < 5 * 1024

  @pytest.mark.asyncio
  async def test_budget_default_config_allows_typical_results(
    self, mock_backend: MagicMock
  ) -> None:
    """Given the default 50KB budget and small results, when executed,
    Then nothing is truncated and no hint is set."""
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    result = await spec.execute(query="test", ctx=ctx)

    assert result.success
    assert result.result["count"] == 2
    assert "truncated" not in result.result
    assert "hint" not in result.result

  def test_max_output_kb_defaults_to_50(self) -> None:
    """Given WebSearchToolConfig, when defaults are inspected,
    Then max_output_kb is 50 and 0 is rejected."""
    from yoker.exceptions import ValidationError

    cfg = WebSearchToolConfig()
    assert cfg.max_output_kb == 50
    with pytest.raises(ValidationError):
      WebSearchToolConfig(max_output_kb=0)


class TestWebSearchOutputBudgetBackstop:
  """The central _enforce_output_limit gate engages for websearch config."""

  def test_websearch_config_exposes_max_output_kb_for_central_gate(self) -> None:
    """Given a default Config, when the tool config is resolved by name,
    Then the gate's getattr contract finds max_output_kb."""
    from yoker.config import ToolsConfig

    config = Config()
    assert config.tools.websearch.max_output_kb == 50

    # The gate resolves tool config by simple name and reads the attr:
    tool_config = ToolsConfig()["websearch"]
    assert getattr(tool_config, "max_output_kb", None) == 50

  @pytest.mark.asyncio
  async def test_giant_ollama_response_stays_under_backstop_size(
    self, mock_backend: MagicMock
  ) -> None:
    """Given the default config and a 300KB-snippet backend response
    (observed in the field), when executed, Then the snippet cap alone
    keeps the serialized result far below the central gate's 50KB."""
    # Field observation: Ollama returned ~300KB per "snippet".
    mock_backend.search = AsyncMock(return_value=_giant_results(10, snippet_len=300_000))
    spec = _websearch_spec()
    ctx = _get_ctx(backend=mock_backend)
    result = await spec.execute(query="test", ctx=ctx)

    assert result.success
    assert result.result["count"] == 10
    assert len(str(result.result).encode("utf-8")) < 50 * 1024


@pytest.fixture
def mock_backend_error() -> MagicMock:
  """Mock WebSearchBackend that raises error."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search = AsyncMock(side_effect=WebSearchError("Backend unavailable", backend="test"))
  return backend


@pytest.fixture
def mock_backend_timeout() -> MagicMock:
  """Mock WebSearchBackend that times out."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search = AsyncMock(side_effect=WebSearchError("Search timeout after 30s", backend="test"))
  return backend


@pytest.fixture
def mock_backend_empty() -> MagicMock:
  """Mock WebSearchBackend that returns empty results."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search = AsyncMock(return_value=[])
  return backend
