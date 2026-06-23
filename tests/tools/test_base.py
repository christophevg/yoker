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

  def test_tool_registry_accepts_function(self) -> None:
    """ToolRegistry can register a plain function and retrieve its spec."""

    async def hello() -> str:
      """Say hello."""
      return "hello"

    registry = ToolRegistry()
    spec = registry.register(hello)
    assert registry.get("hello") is spec
    assert registry.names == ["hello"]
