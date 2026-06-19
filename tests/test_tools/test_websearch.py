"""Tests for websearch tool implementation.

These tests verify the behavior of the websearch tool, including backend integration,
parameter validation, result formatting, and error handling.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.tools import ToolRegistry, make_websearch_tool
from yoker.tools.web_backend import WebSearchBackend
from yoker.tools.web_guardrail import WebGuardrail, WebGuardrailConfig
from yoker.tools.web_types import SearchResult, WebSearchError


def _websearch_spec(backend=None):
  """Create and register the websearch tool."""
  registry = ToolRegistry()
  return registry.register(make_websearch_tool(backend=backend))


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
    spec = _websearch_spec(backend=mock_backend)
    result = await spec.execute(query="test query")

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
    spec = _websearch_spec(backend=mock_backend)
    await spec.execute(query="test query")

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
    spec = _websearch_spec(backend=mock_backend)
    await spec.execute(query="test query", max_results=5)

    mock_backend.search.assert_called_once()
    call_kwargs = mock_backend.search.call_args.kwargs
    assert call_kwargs.get("max_results") == 5

  @pytest.mark.asyncio
  async def test_execute_query_required(self) -> None:
    """
    Given: A websearch tool execute call without query
    When: Calling execute without query parameter
    Then: Returns error ToolResult
    """
    spec = _websearch_spec()
    result = await spec.execute()

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
    result = await spec.execute(query="")

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
    result = await spec.execute(query="   ")

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
    spec = _websearch_spec(backend=mock_backend)
    await spec.execute(query="test query", max_results=100)

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
    spec = _websearch_spec(backend=mock_backend)
    await spec.execute(query="test query", max_results=5)

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
    spec = _websearch_spec(backend=mock_backend_error)
    result = await spec.execute(query="test query")

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
    spec = _websearch_spec(backend=mock_backend_timeout)
    result = await spec.execute(query="test query")

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
    spec = _websearch_spec(backend=mock_backend)
    result = await spec.execute(query="test query")

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
    result = await spec.execute()  # No query provided

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
    spec = _websearch_spec(backend=mock_backend_empty)
    result = await spec.execute(query="test query")

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
    spec = _websearch_spec(backend=mock_backend)
    await spec.execute(query="test query")

    mock_backend.search.assert_called_once()

  @pytest.mark.asyncio
  async def test_no_backend_returns_error(self) -> None:
    """
    Given: websearch tool without backend configured
    When: Executing search
    Then: Returns error about missing backend
    """
    spec = _websearch_spec()
    result = await spec.execute(query="test query")

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
