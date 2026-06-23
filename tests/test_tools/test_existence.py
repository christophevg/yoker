"""Tests for the existence tool implementation."""

import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from yoker.builtin import existence
from yoker.config import Config, PermissionsConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import PathGuardrail

# Import the actual module (not the function exported in __init__.py)
existence_module = sys.modules["yoker.builtin.existence"]


def _existence_spec():
  """Create and register the existence tool."""
  registry = ToolRegistry()
  return registry.register(existence)


def _existence_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for existence tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.existence,
    shared=config.tools_shared,
    backends={},
  )


class TestExistenceToolSchema:
  """Tests for existence tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    spec = _existence_spec()
    assert spec.name == "existence"

  def test_description(self) -> None:
    """Test tool description."""
    spec = _existence_spec()
    assert "file or folder exists" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    spec = _existence_spec()
    schema = spec.schema

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

  @pytest.mark.asyncio
  async def test_existing_file(self, temp_files: Path) -> None:
    """Test existing file returns True."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(temp_files / "file.txt"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "file"
    assert "file.txt" in result.result["path"]

  @pytest.mark.asyncio
  async def test_existing_hidden_file(self, temp_files: Path) -> None:
    """Test hidden file existence check."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(temp_files / ".hidden"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "file"

  @pytest.mark.asyncio
  async def test_existing_nested_file(self, temp_files: Path) -> None:
    """Test nested file existence check."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(temp_files / "subdir" / "nested.txt"), ctx=ctx)

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

  @pytest.mark.asyncio
  async def test_existing_directory(self, temp_dirs: Path) -> None:
    """Test existing directory returns True."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(temp_dirs / "subdir"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  @pytest.mark.asyncio
  async def test_existing_hidden_directory(self, temp_dirs: Path) -> None:
    """Test hidden directory existence check."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(temp_dirs / ".hidden_dir"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  @pytest.mark.asyncio
  async def test_existing_nested_directory(self, temp_dirs: Path) -> None:
    """Test nested directory existence check."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(temp_dirs / "nested" / "deep"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"


class TestExistenceToolNonExistent:
  """Tests for non-existent path handling."""

  @pytest.mark.asyncio
  async def test_nonexistent_file(self, tmp_path: Path) -> None:
    """Test non-existent file returns False."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(tmp_path / "nonexistent.txt"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is False
    assert result.result["type"] is None
    assert "nonexistent.txt" in result.result["path"]

  @pytest.mark.asyncio
  async def test_nonexistent_directory(self, tmp_path: Path) -> None:
    """Test non-existent directory returns False."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(tmp_path / "nonexistent_dir"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is False
    assert result.result["type"] is None

  @pytest.mark.asyncio
  async def test_nonexistent_nested_path(self, tmp_path: Path) -> None:
    """Test non-existent nested path returns False."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(tmp_path / "a" / "b" / "c" / "file.txt"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is False
    assert result.result["type"] is None


class TestExistenceToolSymlinkRejection:
  """Tests for symlink rejection."""

  @pytest.mark.asyncio
  async def test_symlink_rejected(self, tmp_path: Path) -> None:
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

    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(symlink), ctx=ctx)

    assert not result.success
    assert "not accessible" in result.error.lower()

  @pytest.mark.asyncio
  async def test_symlink_to_directory_rejected(self, tmp_path: Path) -> None:
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

    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(symlink), ctx=ctx)

    assert not result.success
    assert "not accessible" in result.error.lower()


class TestExistenceToolValidation:
  """Tests for input validation and error handling."""

  @pytest.mark.asyncio
  async def test_empty_path(self) -> None:
    """Test empty path returns error."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path="", ctx=ctx)

    assert not result.success
    assert "empty" in result.error.lower()

  @pytest.mark.asyncio
  async def test_whitespace_only_path(self) -> None:
    """Test whitespace-only path returns error."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path="   ", ctx=ctx)

    assert not result.success
    assert "empty" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_path_type(self) -> None:
    """Test non-string path returns error."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=123, ctx=ctx)

    assert not result.success
    assert "invalid" in result.error.lower()


class TestExistenceToolWithGuardrail:
  """Tests for guardrail integration."""

  @pytest.mark.asyncio
  async def test_guardrail_blocks_path(self, tmp_path: Path) -> None:
    """Test that the path guardrail can block paths."""
    # Create a file
    (tmp_path / "test.txt").write_text("content")

    # Restrict allowed paths to a subdirectory so the target is blocked
    allowed_path = tmp_path / "allowed"
    allowed_path.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(allowed_path),)))
    guardrail = PathGuardrail(config)

    spec = _existence_spec()
    _existence_context()
    validation = guardrail.validate(spec.name, {"path": str(tmp_path / "test.txt")})

    assert not validation.valid
    assert "outside allowed" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_guardrail_allows_path(self, tmp_path: Path) -> None:
    """Test that the path guardrail can allow paths."""
    # Create a file
    (tmp_path / "test.txt").write_text("content")

    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)

    spec = _existence_spec()
    ctx = _existence_context()
    validation = guardrail.validate(spec.name, {"path": str(tmp_path / "test.txt")})
    assert validation.valid

    result = await spec.execute(path=str(tmp_path / "test.txt"), ctx=ctx)
    assert result.success
    assert result.result["exists"] is True

  @pytest.mark.asyncio
  async def test_guardrail_not_provided(self, tmp_path: Path) -> None:
    """Test tool works without guardrail."""
    # Create a file
    (tmp_path / "test.txt").write_text("content")

    spec = _existence_spec()  # No guardrail
    ctx = _existence_context()
    result = await spec.execute(path=str(tmp_path / "test.txt"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True

  @pytest.mark.asyncio
  async def test_guardrail_blocks_nonexistent_path(self, tmp_path: Path) -> None:
    """Test that the path guardrail blocks access to paths outside allowed directories."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)

    spec = _existence_spec()
    _existence_context()
    validation = guardrail.validate(spec.name, {"path": "/etc/passwd"})

    assert not validation.valid
    assert "outside allowed" in validation.reason.lower()


class TestExistenceToolPathResolution:
  """Tests for path resolution."""

  @pytest.mark.asyncio
  async def test_relative_path_resolved(self, tmp_path: Path) -> None:
    """Test relative paths are resolved to absolute."""
    # Create a file
    (tmp_path / "file.txt").write_text("content")

    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=str(tmp_path / "file.txt"), ctx=ctx)

    assert result.success
    # Path should be absolute
    assert Path(result.result["path"]).is_absolute()

  @pytest.mark.asyncio
  async def test_path_with_dot_segments(self, tmp_path: Path) -> None:
    """Test paths with . segments are resolved."""
    # Create a file
    (tmp_path / "file.txt").write_text("content")

    spec = _existence_spec()
    ctx = _existence_context()
    # Use path with ./ segments
    result = await spec.execute(path=str(tmp_path / "." / "file.txt"), ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    # Path should be normalized
    assert "/./" not in result.result["path"]


class TestExistenceToolSpecialCases:
  """Tests for special cases and edge conditions."""

  @pytest.mark.asyncio
  async def test_root_directory(self) -> None:
    """Test checking root directory exists."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path="/", ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  @pytest.mark.asyncio
  async def test_current_directory(self) -> None:
    """Test checking current directory exists."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path=".", ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"

  @pytest.mark.asyncio
  async def test_parent_directory(self) -> None:
    """Test checking parent directory exists."""
    spec = _existence_spec()
    ctx = _existence_context()
    result = await spec.execute(path="..", ctx=ctx)

    assert result.success
    assert result.result["exists"] is True
    assert result.result["type"] == "directory"


class TestExistenceToolErrorHandling:
  """Tests for error handling scenarios."""

  @pytest.mark.asyncio
  async def test_permission_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """Test PermissionError during existence check."""
    spec = _existence_spec()
    ctx = _existence_context()

    # Mock Path.exists to raise PermissionError
    mock_path = mocker.MagicMock(spec=Path)
    mock_path.is_symlink.return_value = False
    mock_path.exists.side_effect = PermissionError("Access denied")
    mock_path.__str__ = lambda self: "/test/path"

    # Patch Path in the existence module
    mocker.patch.object(existence_module, "Path", return_value=mock_path)

    result = await spec.execute(path="/test/path", ctx=ctx)

    assert not result.success
    assert "failed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_os_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """Test OSError during existence check."""
    spec = _existence_spec()
    ctx = _existence_context()

    # Mock Path.exists to raise OSError
    mock_path = mocker.MagicMock(spec=Path)
    mock_path.is_symlink.return_value = False
    mock_path.exists.side_effect = OSError("IO error")
    mock_path.__str__ = lambda self: "/test/path"

    # Patch Path in the existence module
    mocker.patch.object(existence_module, "Path", return_value=mock_path)

    result = await spec.execute(path="/test/path", ctx=ctx)

    assert not result.success
    assert "failed" in result.error.lower()

  @pytest.mark.asyncio
  async def test_realpath_os_error(self, mocker: Any) -> None:
    """Test OSError during path resolution."""
    spec = _existence_spec()
    ctx = _existence_context()

    # Mock os.path.realpath to raise OSError
    mocker.patch("os.path.realpath", side_effect=OSError("Resolution failed"))

    result = await spec.execute(path="/test/path", ctx=ctx)

    assert not result.success
    assert "invalid" in result.error.lower()
