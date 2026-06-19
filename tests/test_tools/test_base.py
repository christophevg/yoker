"""Tests for ToolResult and ValidationResult base types."""

import pytest

from yoker.tools.base import ToolResult, ValidationResult


class TestToolResult:
  """Tests for ToolResult dataclass."""

  def test_default_success_result(self) -> None:
    """
    Given: A successful ToolResult with no result text
    When: Accessing its attributes
    Then: success is True, result is empty, error is None, metadata is None
    """
    result = ToolResult(success=True)

    assert result.success is True
    assert result.result == ""
    assert result.error is None
    assert result.content_metadata is None

  def test_success_with_result_text(self) -> None:
    """
    Given: A successful ToolResult with result text
    When: Accessing its attributes
    Then: result contains the provided text
    """
    result = ToolResult(success=True, result="hello")

    assert result.result == "hello"
    assert result.error is None

  def test_error_result(self) -> None:
    """
    Given: A failed ToolResult with an error message
    When: Accessing its attributes
    Then: success is False and error is set
    """
    result = ToolResult(success=False, error="something went wrong")

    assert result.success is False
    assert result.error == "something went wrong"
    assert result.result == ""

  def test_structured_result(self) -> None:
    """
    Given: A ToolResult carrying structured data
    When: Accessing its result attribute
    Then: Returns the provided dictionary
    """
    data = {"files": ["a.txt", "b.txt"]}
    result = ToolResult(success=True, result=data)

    assert result.result == data

  def test_content_metadata(self) -> None:
    """
    Given: A ToolResult with content metadata
    When: Accessing its content_metadata attribute
    Then: Returns the provided metadata dictionary
    """
    metadata = {"operation": "read", "path": "/tmp/file.txt"}
    result = ToolResult(success=True, result="content", content_metadata=metadata)

    assert result.content_metadata == metadata

  def test_immutability(self) -> None:
    """
    Given: A ToolResult instance
    When: Attempting to mutate an attribute
    Then: Raises FrozenInstanceError
    """
    result = ToolResult(success=True, result="content")

    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
      result.success = False  # type: ignore[misc]


class TestValidationResult:
  """Tests for ValidationResult dataclass."""

  def test_valid_result(self) -> None:
    """
    Given: A valid ValidationResult
    When: Accessing its attributes
    Then: valid is True and reason is None
    """
    validation = ValidationResult(valid=True)

    assert validation.valid is True
    assert validation.reason is None

  def test_invalid_result_with_reason(self) -> None:
    """
    Given: An invalid ValidationResult with a reason
    When: Accessing its attributes
    Then: valid is False and reason is set
    """
    validation = ValidationResult(valid=False, reason="path outside allowed directories")

    assert validation.valid is False
    assert validation.reason == "path outside allowed directories"
