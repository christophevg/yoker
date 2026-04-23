"""Tests for tool base types."""

import pytest

from yoker.tools.base import Tool, ToolResult, ValidationResult


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


class TestToolABC:
  """Tests for Tool abstract base class."""

  def test_cannot_instantiate(self) -> None:
    """Tool ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
      Tool()

  def test_concrete_tool(self) -> None:
    """Concrete Tool subclass can be instantiated."""

    class MyTool(Tool):
      @property
      def name(self) -> str:
        return "my_tool"

      @property
      def description(self) -> str:
        return "A test tool"

      def get_schema(self) -> dict:
        return {"type": "function", "function": {"name": "my_tool"}}

      def execute(self, value: str = "") -> ToolResult:
        return ToolResult(success=True, result=value)

    tool = MyTool()
    assert tool.name == "my_tool"
    assert tool.description == "A test tool"
    assert tool.get_schema()["function"]["name"] == "my_tool"
    result = tool.execute(value="hello")
    assert result.success is True
    assert result.result == "hello"
