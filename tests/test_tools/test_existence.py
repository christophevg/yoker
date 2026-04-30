"""Tests for ExistenceTool implementation."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.tools.base import ValidationResult
from yoker.tools.existence import ExistenceTool
from yoker.tools.guardrails import Guardrail


class TestExistenceToolSchema:
  """Tests for ExistenceTool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    tool = ExistenceTool()
    assert tool.name == "existence"

  def test_description(self) -> None:
    """Test tool description."""
    tool = ExistenceTool()
    assert "file or folder exists" in tool.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    tool = ExistenceTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "existence"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["path"]


class TestExistenceToolFileCheck:
  """Tests for file existence checking."""

  @pytest.fixture
  def temp_files(self, tmp_path: Path) -> Path:
    """Create a temporary directory with files for testing."""
    # Regular file
    (tmp_path / "file.txt").write_text("hello world")

    # Hidden file
    (tmp_path / ".hidden").write_text("hidden content")

    # Nested file
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested file")

    return tmp_path

  def test_existing_file(self, temp_files: Path) -> None:
    """Test existing file returns True."""
    tool = ExistenceTool()
    result = tool.execute(path=str(temp_files / "file.txt"))

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "file"
    assert "file.txt" in result.result["path"]

  def test_existing_hidden_file(self, temp_files: Path) -> None:
    """Test hidden file existence check."""
    tool = ExistenceTool()
    result = tool.execute(path=str(temp_files / ".hidden"))

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "file"

  def test_existing_nested_file(self, temp_files: Path) -> None:
    """Test nested file existence check."""
    tool = ExistenceTool()
    result = tool.execute(path=str(temp_files / "subdir" / "nested.txt"))

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "file"


class TestExistenceToolDirectoryCheck:
  """Tests for directory existence checking."""

  @pytest.fixture
  def temp_dirs(self, tmp_path: Path) -> Path:
    """Create a temporary directory structure for testing."""
    # Regular directory
    (tmp_path / "subdir").mkdir()

    # Hidden directory
    (tmp_path / ".hidden_dir").mkdir()

    # Nested directory
    nested = tmp_path / "nested" / "deep"
    nested.mkdir(parents=True)

    return tmp_path

  def test_existing_directory(self, temp_dirs: Path) -> None:
    """Test existing directory returns True."""
    tool = ExistenceTool()
    result = tool.execute(path=str(temp_dirs / "subdir"))

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  def test_existing_hidden_directory(self, temp_dirs: Path) -> None:
    """Test hidden directory existence check."""
    tool = ExistenceTool()
    result = tool.execute(path=str(temp_dirs / ".hidden_dir"))

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  def test_existing_nested_directory(self, temp_dirs: Path) -> None:
    """Test nested directory existence check."""
    tool = ExistenceTool()
    result = tool.execute(path=str(temp_dirs / "nested" / "deep"))

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"


class TestExistenceToolNonExistent:
  """Tests for non-existent path handling."""

  def test_nonexistent_file(self, tmp_path: Path) -> None:
    """Test non-existent file returns False."""
    tool = ExistenceTool()
    result = tool.execute(path=str(tmp_path / "nonexistent.txt"))

    assert result.success
    assert result.result["exists"] is False
    assert result.result["type"] is None
    assert "nonexistent.txt" in result.result["path"]

  def test_nonexistent_directory(self, tmp_path: Path) -> None:
    """Test non-existent directory returns False."""
    tool = ExistenceTool()
    result = tool.execute(path=str(tmp_path / "nonexistent_dir"))

    assert result.success
    assert result.result["exists"] is False
    assert result.result["type"] is None

  def test_nonexistent_nested_path(self, tmp_path: Path) -> None:
    """Test non-existent nested path returns False."""
    tool = ExistenceTool()
    result = tool.execute(path=str(tmp_path / "a" / "b" / "c" / "file.txt"))

    assert result.success
    assert result.result["exists"] is False
    assert result.result["type"] is None


class TestExistenceToolSymlinkRejection:
  """Tests for symlink rejection."""

  def test_symlink_rejected(self, tmp_path: Path) -> None:
    """Test that symlinks are rejected."""
    # Create regular file
    regular_file = tmp_path / "regular.txt"
    regular_file.write_text("content")

    # Create symlink
    symlink = tmp_path / "link_to_file"
    try:
      symlink.symlink_to(regular_file)
    except OSError:
      pytest.skip("Symlinks not supported on this platform")

    tool = ExistenceTool()
    result = tool.execute(path=str(symlink))

    assert not result.success
    assert "not accessible" in result.error.lower()

  def test_symlink_to_directory_rejected(self, tmp_path: Path) -> None:
    """Test that symlinks to directories are rejected."""
    # Create directory
    regular_dir = tmp_path / "regular_dir"
    regular_dir.mkdir()

    # Create symlink to directory
    symlink = tmp_path / "link_to_dir"
    try:
      symlink.symlink_to(regular_dir)
    except OSError:
      pytest.skip("Symlinks not supported on this platform")

    tool = ExistenceTool()
    result = tool.execute(path=str(symlink))

    assert not result.success
    assert "not accessible" in result.error.lower()


class TestExistenceToolValidation:
  """Tests for input validation and error handling."""

  def test_empty_path(self) -> None:
    """Test empty path returns error."""
    tool = ExistenceTool()
    result = tool.execute(path="")

    assert not result.success
    assert "empty" in result.error.lower()

  def test_whitespace_only_path(self) -> None:
    """Test whitespace-only path returns error."""
    tool = ExistenceTool()
    result = tool.execute(path="   ")

    assert not result.success
    assert "empty" in result.error.lower()

  def test_invalid_path_type(self) -> None:
    """Test non-string path returns error."""
    tool = ExistenceTool()
    result = tool.execute(path=123)

    assert not result.success
    assert "invalid" in result.error.lower()


class TestExistenceToolWithGuardrail:
  """Tests for guardrail integration."""

  def test_guardrail_blocks_path(self, tmp_path: Path) -> None:
    """Test that guardrail can block paths."""
    # Create a file
    (tmp_path / "test.txt").write_text("content")

    # Create a mock guardrail that blocks all paths
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(valid=False, reason="Path not allowed")

    tool = ExistenceTool(guardrail=mock_guardrail)
    result = tool.execute(path=str(tmp_path / "test.txt"))

    assert not result.success
    assert "Path not allowed" in result.error
    mock_guardrail.validate.assert_called_once()

  def test_guardrail_allows_path(self, tmp_path: Path) -> None:
    """Test that guardrail can allow paths."""
    # Create a file
    (tmp_path / "test.txt").write_text("content")

    # Create a mock guardrail that allows all paths
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(valid=True)

    tool = ExistenceTool(guardrail=mock_guardrail)
    result = tool.execute(path=str(tmp_path / "test.txt"))

    assert result.success
    assert result.result["exists"] is True
    mock_guardrail.validate.assert_called_once()

  def test_guardrail_not_provided(self, tmp_path: Path) -> None:
    """Test tool works without guardrail."""
    # Create a file
    (tmp_path / "test.txt").write_text("content")

    tool = ExistenceTool()  # No guardrail
    result = tool.execute(path=str(tmp_path / "test.txt"))

    assert result.success
    assert result.result["exists"] is True

  def test_guardrail_blocks_nonexistent_path(self, tmp_path: Path) -> None:
    """Test that guardrail blocks access to paths outside allowed directories."""
    # Create a mock guardrail that blocks the path
    mock_guardrail = MagicMock(spec=Guardrail)
    mock_guardrail.validate.return_value = ValidationResult(
      valid=False, reason="Path outside allowed directories: /etc/passwd"
    )

    tool = ExistenceTool(guardrail=mock_guardrail)
    result = tool.execute(path="/etc/passwd")

    assert not result.success
    assert "Path outside allowed directories" in result.error


class TestExistenceToolPathResolution:
  """Tests for path resolution."""

  def test_relative_path_resolved(self, tmp_path: Path) -> None:
    """Test relative paths are resolved to absolute."""
    # Create a file
    (tmp_path / "file.txt").write_text("content")

    tool = ExistenceTool()
    result = tool.execute(path=str(tmp_path / "file.txt"))

    assert result.success
    # Path should be absolute
    assert Path(result.result["path"]).is_absolute()

  def test_path_with_dot_segments(self, tmp_path: Path) -> None:
    """Test paths with . segments are resolved."""
    # Create a file
    (tmp_path / "file.txt").write_text("content")

    tool = ExistenceTool()
    # Use path with ./ segments
    result = tool.execute(path=str(tmp_path / "." / "file.txt"))

    assert result.success
    assert result.result["exists"] is True
    # Path should be normalized
    assert "/./" not in result.result["path"]


class TestExistenceToolSpecialCases:
  """Tests for special cases and edge conditions."""

  def test_root_directory(self) -> None:
    """Test checking root directory exists."""
    tool = ExistenceTool()
    result = tool.execute(path="/")

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  def test_current_directory(self) -> None:
    """Test checking current directory exists."""
    tool = ExistenceTool()
    result = tool.execute(path=".")

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  def test_parent_directory(self) -> None:
    """Test checking parent directory exists."""
    tool = ExistenceTool()
    result = tool.execute(path="..")

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"


class TestExistenceToolErrorHandling:
  """Tests for error handling scenarios."""

  def test_permission_error(self, tmp_path: Path, mocker: Any) -> None:
    """Test PermissionError during existence check."""
    tool = ExistenceTool()

    # Mock Path.exists to raise PermissionError
    mock_path = mocker.MagicMock(spec=Path)
    mock_path.is_symlink.return_value = False
    mock_path.exists.side_effect = PermissionError("Access denied")
    mock_path.__str__ = lambda self: "/test/path"

    # Patch Path to return our mock
    mocker.patch("yoker.tools.existence.Path", return_value=mock_path)

    result = tool.execute(path="/test/path")

    assert not result.success
    assert "failed" in result.error.lower()

  def test_os_error(self, tmp_path: Path, mocker: Any) -> None:
    """Test OSError during existence check."""
    tool = ExistenceTool()

    # Mock Path.exists to raise OSError
    mock_path = mocker.MagicMock(spec=Path)
    mock_path.is_symlink.return_value = False
    mock_path.exists.side_effect = OSError("IO error")
    mock_path.__str__ = lambda self: "/test/path"

    # Patch Path to return our mock
    mocker.patch("yoker.tools.existence.Path", return_value=mock_path)

    result = tool.execute(path="/test/path")

    assert not result.success
    assert "failed" in result.error.lower()

  def test_realpath_os_error(self, mocker: Any) -> None:
    """Test OSError during path resolution."""
    tool = ExistenceTool()

    # Mock os.path.realpath to raise OSError
    mocker.patch("os.path.realpath", side_effect=OSError("Resolution failed"))

    result = tool.execute(path="/test/path")

    assert not result.success
    assert "invalid" in result.error.lower()
