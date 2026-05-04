"""Tests for web search types (SearchResult, WebSearchError).

These tests verify the data structures used for web search results
and error handling.
"""

from dataclasses import FrozenInstanceError

import pytest

from yoker.tools.web_types import SearchResult, WebSearchError


class TestSearchResult:
  """Tests for SearchResult dataclass."""

  def test_search_result_is_frozen(self) -> None:
    """
    Given: A SearchResult instance
    When: Attempting to modify a field
    Then: Raises FrozenInstanceError
    """
    result = SearchResult(title="Test", url="https://example.com", snippet="Test snippet")

    with pytest.raises(FrozenInstanceError):
      result.title = "Modified"

  def test_search_result_has_all_fields(self) -> None:
    """
    Given: Creating a SearchResult
    When: Providing all required fields
    Then: SearchResult contains all fields correctly
    """
    result = SearchResult(
      title="Test Title",
      url="https://example.com",
      snippet="Test snippet",
      source="test_source",
    )

    assert result.title == "Test Title"
    assert result.url == "https://example.com"
    assert result.snippet == "Test snippet"
    assert result.source == "test_source"

  def test_search_result_default_source(self) -> None:
    """
    Given: Creating a SearchResult without source field
    When: Creating SearchResult(title=..., url=..., snippet=...)
    Then: Uses 'unknown' as default source
    """
    result = SearchResult(title="Test", url="https://example.com", snippet="Test snippet")

    assert result.source == "unknown"

  def test_search_result_to_dict(self) -> None:
    """
    Given: A SearchResult instance
    When: Converting to dictionary
    Then: Returns dict with all fields
    """
    result = SearchResult(
      title="Test Title",
      url="https://example.com",
      snippet="Test snippet",
      source="test_source",
    )

    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["title"] == "Test Title"
    assert result_dict["url"] == "https://example.com"
    assert result_dict["snippet"] == "Test snippet"
    assert result_dict["source"] == "test_source"

  def test_search_result_from_dict(self) -> None:
    """
    Given: A dictionary with search result fields
    When: Creating SearchResult from dict
    Then: Returns SearchResult with correct values
    """
    data = {
      "title": "Test Title",
      "url": "https://example.com",
      "snippet": "Test snippet",
      "source": "test_source",
    }

    result = SearchResult.from_dict(data)

    assert result.title == "Test Title"
    assert result.url == "https://example.com"
    assert result.snippet == "Test snippet"
    assert result.source == "test_source"

  def test_search_result_equality(self) -> None:
    """
    Given: Two SearchResult instances with same values
    When: Comparing them
    Then: They are equal
    """
    result1 = SearchResult(
      title="Test",
      url="https://example.com",
      snippet="Snippet",
      source="test",
    )
    result2 = SearchResult(
      title="Test",
      url="https://example.com",
      snippet="Snippet",
      source="test",
    )

    assert result1 == result2

  def test_search_result_repr(self) -> None:
    """
    Given: A SearchResult instance
    When: Calling repr()
    Then: Returns readable string representation
    """
    result = SearchResult(
      title="Test Title",
      url="https://example.com",
      snippet="Test snippet",
      source="test_source",
    )

    repr_str = repr(result)

    assert "SearchResult" in repr_str
    assert "Test Title" in repr_str


class TestWebSearchError:
  """Tests for WebSearchError exception."""

  def test_error_message(self) -> None:
    """
    Given: Creating WebSearchError with message
    When: Accessing error message
    Then: Returns the provided message
    """
    error = WebSearchError("Test error message")

    assert error.message == "Test error message"

  def test_error_backend(self) -> None:
    """
    Given: Creating WebSearchError with backend name
    When: Accessing backend attribute
    Then: Returns the provided backend name
    """
    error = WebSearchError("Test error", backend="ollama")

    assert error.backend == "ollama"

  def test_error_default_backend(self) -> None:
    """
    Given: Creating WebSearchError without backend
    When: Accessing backend attribute
    Then: Returns 'unknown' as default
    """
    error = WebSearchError("Test error")

    assert error.backend == "unknown"

  def test_error_cause(self) -> None:
    """
    Given: Creating WebSearchError with cause exception
    When: Accessing cause attribute
    Then: Returns the original exception
    """
    original_error = ValueError("Original error")
    error = WebSearchError("Test error", cause=original_error)

    assert error.cause is original_error

  def test_error_default_cause(self) -> None:
    """
    Given: Creating WebSearchError without cause
    When: Accessing cause attribute
    Then: Returns None
    """
    error = WebSearchError("Test error")

    assert error.cause is None

  def test_error_str_representation(self) -> None:
    """
    Given: A WebSearchError instance
    When: Converting to string
    Then: Returns readable string with message
    """
    error = WebSearchError("Test error message", backend="ollama")

    str_repr = str(error)

    assert "ollama" in str_repr
    assert "Test error message" in str_repr

  def test_error_inheritance(self) -> None:
    """
    Given: A WebSearchError instance
    When: Checking isinstance
    Then: Is instance of Exception
    """
    error = WebSearchError("Test error")

    assert isinstance(error, Exception)


class TestSearchResultList:
  """Tests for list of SearchResult objects."""

  def test_empty_result_list(self) -> None:
    """
    Given: An empty list of SearchResult
    When: Checking the list
    Then: List is empty but valid
    """
    results: list[SearchResult] = []

    assert len(results) == 0
    assert isinstance(results, list)

  def test_result_list_iteration(self) -> None:
    """
    Given: A list of SearchResult objects
    When: Iterating over the list
    Then: Each item is a SearchResult instance
    """
    results = [
      SearchResult(title="A", url="https://a.com", snippet="A"),
      SearchResult(title="B", url="https://b.com", snippet="B"),
    ]

    for result in results:
      assert isinstance(result, SearchResult)

  def test_result_list_serialization(self) -> None:
    """
    Given: A list of SearchResult objects
    When: Converting to JSON-compatible format
    Then: Each result can be serialized to dict
    """
    results = [
      SearchResult(title="A", url="https://a.com", snippet="A", source="test"),
      SearchResult(title="B", url="https://b.com", snippet="B", source="test"),
    ]

    serialized = [r.to_dict() for r in results]

    assert len(serialized) == 2
    assert all(isinstance(d, dict) for d in serialized)
    assert all("title" in d and "url" in d for d in serialized)
