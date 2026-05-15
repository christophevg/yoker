"""Tests for Tool base class."""

from pathlib import Path
from unittest.mock import MagicMock

from yoker.tools.base import Tool, ToolResult, ValidationResult
from yoker.tools.registry import ToolRegistry


class ConcreteTool(Tool):
  """Concrete implementation of Tool for testing."""

  @property
  def name(self) -> str:
    return "test_tool"

  @property
  def description(self) -> str:
    return "Test tool for unit tests"

  def get_schema(self) -> dict:
    return {"type": "function", "function": {"name": self.name, "description": self.description}}

  def execute(self, **kwargs) -> ToolResult:
    return ToolResult(success=True, result="test")


class TestToolExists:
  """Tests for Tool.exists method."""

  def test_exists_without_guardrail_returns_true_for_existing_file(
    self, tmp_path: Path
  ) -> None:
    """Without guardrail, exists() returns True for existing file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    tool = ConcreteTool()
    assert tool.exists(str(test_file)) is True

  def test_exists_without_guardrail_returns_false_for_nonexistent_file(
    self, tmp_path: Path
  ) -> None:
    """Without guardrail, exists() returns False for nonexistent file."""
    tool = ConcreteTool()
    assert tool.exists(str(tmp_path / "nonexistent.txt")) is False

  def test_exists_without_guardrail_returns_true_for_existing_directory(
    self, tmp_path: Path
  ) -> None:
    """Without guardrail, exists() returns True for existing directory."""
    tool = ConcreteTool()
    assert tool.exists(str(tmp_path)) is True

  def test_exists_with_guardrail_validates_before_checking(
    self, tmp_path: Path
  ) -> None:
    """With guardrail, exists() validates path before checking existence."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    # Create mock guardrail that rejects all paths
    mock_guardrail = MagicMock()
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Path rejected by guardrail"
    )

    tool = ConcreteTool(guardrail=mock_guardrail)

    # Even though file exists, guardrail blocks it
    assert tool.exists(str(test_file)) is False
    mock_guardrail.validate.assert_called_once_with("test_tool", {"path": str(test_file)})

  def test_exists_with_guardrail_passes_when_valid(
    self, tmp_path: Path
  ) -> None:
    """When guardrail validates, exists() checks file existence."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    # Create mock guardrail that allows all paths
    mock_guardrail = MagicMock()
    mock_guardrail.validate.return_value = ValidationResult(valid=True)

    tool = ConcreteTool(guardrail=mock_guardrail)

    assert tool.exists(str(test_file)) is True
    mock_guardrail.validate.assert_called_once_with("test_tool", {"path": str(test_file)})

  def test_exists_with_guardrail_rejects_nonexistent_path(
    self, tmp_path: Path
  ) -> None:
    """When guardrail validates but file doesn't exist, returns False."""
    nonexistent = tmp_path / "nonexistent.txt"

    # Create mock guardrail that allows all paths
    mock_guardrail = MagicMock()
    mock_guardrail.validate.return_value = ValidationResult(valid=True)

    tool = ConcreteTool(guardrail=mock_guardrail)

    assert tool.exists(str(nonexistent)) is False


class TestToolRegistryExists:
  """Tests for ToolRegistry.exists method."""

  def test_exists_returns_false_for_unregistered_tool(self, tmp_path: Path) -> None:
    """Registry.exists returns False if tool not found."""
    registry = ToolRegistry()
    assert registry.exists("nonexistent", str(tmp_path)) is False

  def test_exists_delegates_to_tool(self, tmp_path: Path) -> None:
    """Registry.exists delegates to the registered tool's exists method."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    tool = ConcreteTool()
    registry = ToolRegistry()
    registry.register(tool)

    assert registry.exists("test_tool", str(test_file)) is True

  def test_exists_returns_false_when_tool_rejects_path(
    self, tmp_path: Path
  ) -> None:
    """Registry.exists returns False when tool's guardrail rejects."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")

    # Create mock guardrail that rejects all paths
    mock_guardrail = MagicMock()
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Path rejected"
    )

    tool = ConcreteTool(guardrail=mock_guardrail)
    registry = ToolRegistry()
    registry.register(tool)

    assert registry.exists("test_tool", str(test_file)) is False
