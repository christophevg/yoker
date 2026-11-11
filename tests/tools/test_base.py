"""Tests for tool base types."""

from typing import Annotated

import pytest

from yoker.tools.annotations import Text
from yoker.tools.registry import ToolRegistry
from yoker.tools.schema import ToolResult, ValidationResult, build_tool_spec


class TestToolResult:
  """Tests for ToolResult dataclass."""

  def test_success_result(self) -> None:
    """ToolResult with success=True."""
    result = ToolResult(success=True, result="hello")
    assert result.success is True
    assert result.result == "hello"
    assert result.error is None

  def test_failure_result(self) -> None:
    """ToolResult with success=False."""
    result = ToolResult(success=False, result="", error="oops")
    assert result.success is False
    assert result.result == ""
    assert result.error == "oops"

  def test_frozen(self) -> None:
    """ToolResult is immutable."""
    result = ToolResult(success=True, result="x")
    with pytest.raises(AttributeError):
      result.success = False


class TestValidationResult:
  """Tests for ValidationResult dataclass."""

  def test_valid(self) -> None:
    """ValidationResult with valid=True."""
    result = ValidationResult(valid=True)
    assert result.valid is True
    assert result.reason is None

  def test_invalid(self) -> None:
    """ValidationResult with valid=False."""
    result = ValidationResult(valid=False, reason="not allowed")
    assert result.valid is False
    assert result.reason == "not allowed"

  def test_frozen(self) -> None:
    """ValidationResult is immutable."""
    result = ValidationResult(valid=True)
    with pytest.raises(AttributeError):
      result.valid = False


class TestToolSpec:
  """Tests for building ToolSpec from plain functions."""

  def test_build_tool_spec_from_function(self) -> None:
    """A plain async function becomes a ToolSpec."""

    async def my_tool(value: Annotated[str, Text("A value")]) -> str:
      """A test tool."""
      return value

    spec = build_tool_spec(my_tool)
    assert spec.name == "my_tool"
    assert "A test tool" in spec.description
    assert spec.schema["type"] == "function"
    assert spec.schema["function"]["name"] == "my_tool"
    assert "value" in spec.schema["function"]["parameters"]["properties"]

  def test_description_joins_wrapped_first_paragraph(self) -> None:
    """A summary wrapped over physical lines is joined, not cut mid-sentence."""

    async def my_tool(value: str) -> str:
      """Register a widget and return its id; the serial may be
      auto-assigned when none is supplied."""
      return value

    spec = build_tool_spec(my_tool)
    assert spec.description == (
      "Register a widget and return its id; the serial may be auto-assigned when none is supplied."
    )

  def test_description_stops_at_blank_line_before_sections(self) -> None:
    """The description is the first paragraph; Args/Returns stay out."""

    async def my_tool(value: str) -> str:
      """Split content into chunks.

      Args:
        value: The content to split.
      """
      return value

    spec = build_tool_spec(my_tool)
    assert spec.description == "Split content into chunks."

  def test_description_stops_at_section_header_without_blank_line(self) -> None:
    """A section header directly after the summary also ends it."""

    async def my_tool(value: str) -> str:
      """Split content into chunks.
      Args:
        value: The content to split.
      """
      return value

    spec = build_tool_spec(my_tool)
    assert spec.description == "Split content into chunks."

  def test_description_single_line_unchanged(self) -> None:
    """Single-line docstrings keep their exact behavior."""

    async def my_tool(value: str) -> str:
      """A concise tool."""
      return value

    spec = build_tool_spec(my_tool)
    assert spec.description == "A concise tool."

  def test_description_whitespace_only_docstring_raises(self) -> None:
    """A whitespace-only docstring still fails registration."""

    async def my_tool(value: str) -> str:
      """ """
      return value

    with pytest.raises(ValueError, match="needs a description"):
      build_tool_spec(my_tool)

  def test_tool_registry_accepts_function(self) -> None:
    """ToolRegistry can register a plain function and retrieve its spec."""

    async def hello() -> str:
      """Say hello."""
      return "hello"

    registry = ToolRegistry()
    spec = registry.register(hello)
    assert registry.get("hello") is spec
    assert registry.names == ["hello"]
