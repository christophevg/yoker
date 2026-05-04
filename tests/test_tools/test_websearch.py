"""Tests for WebSearchTool implementation.

These tests verify the behavior of the WebSearchTool, including backend integration,
parameter validation, result formatting, and error handling.
"""

from unittest.mock import MagicMock

import pytest

from yoker.tools.web_backend import WebSearchBackend
from yoker.tools.web_guardrail import WebGuardrail, WebGuardrailConfig
from yoker.tools.web_types import SearchResult, WebSearchError
from yoker.tools.websearch import WebSearchTool


class TestWebSearchToolSchema:
  """Tests for WebSearchTool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A WebSearchTool instance
    When: Checking the tool name property
    Then: Returns 'web_search'
    """
    tool = WebSearchTool()

    assert tool.name == "web_search"

  def test_description(self) -> None:
    """
    Given: A WebSearchTool instance
    When: Checking the tool description property
    Then: Returns description mentioning web search
    """
    tool = WebSearchTool()

    assert "web" in tool.description.lower()
    assert "search" in tool.description.lower()

  def test_schema_structure(self) -> None:
    """
    Given: A WebSearchTool instance
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with query and max_results parameters
    """
    tool = WebSearchTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert "function" in schema
    assert "parameters" in schema["function"]
    assert "properties" in schema["function"]["parameters"]

  def test_schema_query_required(self) -> None:
    """
    Given: The WebSearchTool schema
    When: Checking required parameters
    Then: 'query' is required, 'max_results' is optional
    """
    tool = WebSearchTool()
    schema = tool.get_schema()

    required = schema["function"]["parameters"]["required"]
    assert "query" in required
    assert "max_results" not in required

  def test_schema_max_results_bounds(self) -> None:
    """
    Given: The WebSearchTool schema
    When: Checking max_results parameter
    Then: Has minimum=1 and maximum=50 constraints
    """
    tool = WebSearchTool()
    schema = tool.get_schema()

    max_results_prop = schema["function"]["parameters"]["properties"]["max_results"]
    assert max_results_prop["minimum"] == 1
    assert max_results_prop["maximum"] == 50


class TestWebSearchToolExecution:
  """Tests for WebSearchTool execute method."""

  def test_execute_returns_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebSearchTool with mocked backend
    When: Executing a valid search query
    Then: Returns ToolResult with search results
    """
    tool = WebSearchTool(backend=mock_backend)
    result = tool.execute(query="test query")

    assert result.success
    assert "results" in result.result

  def test_execute_with_default_max_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebSearchTool with mocked backend
    When: Executing search without max_results parameter
    Then: Uses default max_results value (10)
    """
    tool = WebSearchTool(backend=mock_backend)
    tool.execute(query="test query")

    # Check that backend was called with default max_results=10
    mock_backend.search.assert_called_once()
    call_args = mock_backend.search.call_args
    assert call_args.kwargs.get("max_results", call_args[1] if len(call_args.args) > 1 else 10) == 10

  def test_execute_with_custom_max_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebSearchTool with mocked backend
    When: Executing search with max_results=5
    Then: Passes max_results=5 to backend
    """
    tool = WebSearchTool(backend=mock_backend)
    tool.execute(query="test query", max_results=5)

    mock_backend.search.assert_called_once()
    call_kwargs = mock_backend.search.call_args.kwargs
    assert call_kwargs.get("max_results") == 5

  def test_execute_query_required(self) -> None:
    """
    Given: A WebSearchTool execute call without query
    When: Calling execute without query parameter
    Then: Returns error ToolResult
    """
    tool = WebSearchTool()
    result = tool.execute()

    assert not result.success
    assert result.error is not None
    assert "query" in result.error.lower()

  def test_execute_empty_query_rejected(self) -> None:
    """
    Given: A WebSearchTool execute call with empty query
    When: Calling execute with query=""
    Then: Returns error ToolResult
    """
    tool = WebSearchTool()
    result = tool.execute(query="")

    assert not result.success
    assert result.error is not None

  def test_execute_whitespace_query_rejected(self) -> None:
    """
    Given: A WebSearchTool execute call with whitespace-only query
    When: Calling execute with query="   "
    Then: Returns error ToolResult
    """
    tool = WebSearchTool()
    result = tool.execute(query="   ")

    assert not result.success
    assert result.error is not None

  def test_execute_clamps_max_results(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebSearchTool with max_results=100 (exceeds maximum)
    When: Executing search
    Then: Clamps max_results to 50
    """
    tool = WebSearchTool(backend=mock_backend)
    tool.execute(query="test query", max_results=100)

    call_kwargs = mock_backend.search.call_args.kwargs
    assert call_kwargs.get("max_results") == 50

  def test_execute_guardrail_validation_failure(self) -> None:
    """
    Given: A WebSearchTool with guardrail that rejects query
    When: Executing search with blocked query
    Then: Returns error ToolResult without calling backend
    """
    guardrail = WebGuardrail(WebGuardrailConfig(domain_blocklist=("blocked.com",)))
    mock_backend = MagicMock()
    tool = WebSearchTool(backend=mock_backend, guardrail=guardrail)

    # Query containing blocked domain
    result = tool.execute(query="site:blocked.com secret data")

    assert not result.success
    assert result.error is not None
    mock_backend.search.assert_not_called()


class TestWebSearchToolBackendIntegration:
  """Tests for WebSearchTool backend integration."""

  def test_backend_receives_valid_parameters(self, mock_backend: MagicMock) -> None:
    """
    Given: A WebSearchTool with mocked backend
    When: Executing search with valid parameters
    Then: Backend.search() receives validated query and max_results
    """
    tool = WebSearchTool(backend=mock_backend)
    tool.execute(query="test query", max_results=5)

    mock_backend.search.assert_called_once_with(query="test query", max_results=5)

  def test_backend_error_returns_error_result(self, mock_backend_error: MagicMock) -> None:
    """
    Given: A backend that raises WebSearchError
    When: Executing search
    Then: Returns error ToolResult with backend error message
    """
    tool = WebSearchTool(backend=mock_backend_error)
    result = tool.execute(query="test query")

    assert not result.success
    assert result.error is not None

  def test_backend_timeout_returns_error_result(self, mock_backend_timeout: MagicMock) -> None:
    """
    Given: A backend that times out
    When: Executing search
    Then: Returns error ToolResult with timeout message
    """
    tool = WebSearchTool(backend=mock_backend_timeout)
    result = tool.execute(query="test query")

    assert not result.success
    assert result.error is not None


class TestWebSearchToolResultFormat:
  """Tests for WebSearchTool result formatting."""

  def test_success_result_format(self, mock_backend: MagicMock) -> None:
    """
    Given: A successful web search
    When: Checking the ToolResult
    Then: success=True, result contains formatted search results
    """
    tool = WebSearchTool(backend=mock_backend)
    result = tool.execute(query="test query")

    assert result.success
    assert isinstance(result.result, dict)
    assert "results" in result.result
    assert "count" in result.result

  def test_error_result_format(self) -> None:
    """
    Given: A failed web search
    When: Checking the ToolResult
    Then: success=False, result is empty, error contains message
    """
    tool = WebSearchTool()
    result = tool.execute()  # No query provided

    assert not result.success
    assert result.result == {}
    assert result.error is not None

  def test_empty_results_returns_empty_list(self, mock_backend_empty: MagicMock) -> None:
    """
    Given: A backend that returns empty results
    When: Executing search
    Then: Returns success with empty results list
    """
    tool = WebSearchTool(backend=mock_backend_empty)
    result = tool.execute(query="test query")

    assert result.success
    assert result.result["results"] == []
    assert result.result["count"] == 0


class TestWebSearchToolConfiguration:
  """Tests for WebSearchTool configuration."""

  def test_default_backend_is_ollama(self) -> None:
    """
    Given: Creating WebSearchTool without explicit backend
    When: Checking backend type
    Then: Backend is None (requires explicit configuration)
    """
    tool = WebSearchTool()

    assert tool._backend is None

  def test_custom_backend_used(self, mock_backend: MagicMock) -> None:
    """
    Given: Creating WebSearchTool with custom backend
    When: Executing search
    Then: Uses provided backend instead of default
    """
    tool = WebSearchTool(backend=mock_backend)
    tool.execute(query="test query")

    mock_backend.search.assert_called_once()

  def test_no_backend_returns_error(self) -> None:
    """
    Given: WebSearchTool without backend configured
    When: Executing search
    Then: Returns error about missing backend
    """
    tool = WebSearchTool()
    result = tool.execute(query="test query")

    assert not result.success
    assert "backend" in result.error.lower()


# Fixtures


@pytest.fixture
def mock_backend() -> MagicMock:
  """Mock WebSearchBackend that returns sample results."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search.return_value = [
    SearchResult(title="Result 1", url="https://example.com/1", snippet="Snippet 1", source="test"),
    SearchResult(title="Result 2", url="https://example.com/2", snippet="Snippet 2", source="test"),
  ]
  return backend


@pytest.fixture
def mock_backend_error() -> MagicMock:
  """Mock WebSearchBackend that raises error."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search.side_effect = WebSearchError("Backend unavailable", backend="test")
  return backend


@pytest.fixture
def mock_backend_timeout() -> MagicMock:
  """Mock WebSearchBackend that times out."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search.side_effect = WebSearchError("Search timeout after 30s", backend="test")
  return backend


@pytest.fixture
def mock_backend_empty() -> MagicMock:
  """Mock WebSearchBackend that returns empty results."""
  backend = MagicMock(spec=WebSearchBackend)
  backend.search.return_value = []
  return backend
