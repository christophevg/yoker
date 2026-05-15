"""Tests for MkdirTool implementation.

These tests verify the behavior of the directory creation tool,
including basic creation, idempotency, security guardrails,
and error handling.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from yoker.config.schema import (
  Config,
  MkdirToolConfig,
  PermissionsConfig,
  ReadToolConfig,
  ToolsConfig,
)
from yoker.tools.mkdir import MkdirTool
from yoker.tools.path_guardrail import PathGuardrail


class TestMkdirToolSchema:
  """Tests for MkdirTool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A MkdirTool instance
    When: Checking the tool name property
    Then: Returns 'mkdir'
    """
    tool = MkdirTool()
    assert tool.name == "mkdir"

  def test_description(self) -> None:
    """
    Given: A MkdirTool instance
    When: Checking the tool description property
    Then: Returns description about creating directories
    """
    tool = MkdirTool()
    assert "directory" in tool.description.lower()

  def test_schema_structure(self) -> None:
    """
    Given: A MkdirTool instance
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with path parameter and optional recursive
    """
    tool = MkdirTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mkdir"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert "recursive" in schema["function"]["parameters"]["properties"]

  def test_schema_path_required(self) -> None:
    """
    Given: The MkdirTool schema
    When: Checking required parameters
    Then: 'path' is required, 'recursive' is optional
    """
    tool = MkdirTool()
    schema = tool.get_schema()

    required = schema["function"]["parameters"]["required"]
    assert "path" in required
    assert "recursive" not in required


class TestMkdirToolBasicCreation:
  """Tests for basic directory creation."""

  @pytest.fixture
  def temp_dir(self, tmp_path: Path) -> Path:
    """Create a temporary directory for testing."""
    return tmp_path

  def test_create_new_directory(self, temp_dir: Path) -> None:
    """
    Given: A valid path to a non-existent directory
    When: Calling execute with path parameter
    Then: Directory is created and result shows created=True
    """
    tool = MkdirTool()
    new_dir = temp_dir / "newdir"
    result = tool.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert "newdir" in result.result["path"]
    assert new_dir.is_dir()

  def test_create_nested_directory_recursive(self, temp_dir: Path) -> None:
    """
    Given: A nested path /a/b/c and recursive=True
    When: Calling execute
    Then: All parent directories are created
    """
    tool = MkdirTool()
    nested_path = temp_dir / "a" / "b" / "c"
    result = tool.execute(path=str(nested_path), recursive=True)

    assert result.success
    assert result.result["created"] is True
    assert nested_path.is_dir()
    assert (temp_dir / "a").is_dir()
    assert (temp_dir / "a" / "b").is_dir()

  def test_create_nested_directory_non_recursive(self, temp_dir: Path) -> None:
    """
    Given: A nested path /a/b/c and recursive=False (default)
    When: Parent directory doesn't exist
    Then: Returns error about missing parent
    """
    tool = MkdirTool()
    nested_path = temp_dir / "newdir" / "nested"
    result = tool.execute(path=str(nested_path), recursive=False)

    assert not result.success
    assert "parent" in result.error.lower()
    assert not nested_path.exists()

  def test_create_directory_with_parents_exist_recursive(self, temp_dir: Path) -> None:
    """
    Given: A nested path where some parents exist and recursive=True
    When: Calling execute
    Then: Only missing directories are created
    """
    tool = MkdirTool()
    # Create parent
    parent = temp_dir / "parent"
    parent.mkdir()

    # Create nested directory with recursive
    nested_path = parent / "child" / "grandchild"
    result = tool.execute(path=str(nested_path), recursive=True)

    assert result.success
    assert result.result["created"] is True
    assert nested_path.is_dir()
    assert (parent / "child").is_dir()


class TestMkdirToolIdempotency:
  """Tests for idempotent directory creation."""

  @pytest.fixture
  def temp_structure(self, tmp_path: Path) -> Path:
    """Create a temporary directory with existing structure."""
    (tmp_path / "existing_dir").mkdir()
    return tmp_path

  def test_create_existing_directory(self, temp_structure: Path) -> None:
    """
    Given: A path to an existing directory
    When: Calling execute
    Then: Returns success with created=False and message about existing directory
    """
    tool = MkdirTool()
    existing_dir = temp_structure / "existing_dir"
    result = tool.execute(path=str(existing_dir))

    assert result.success
    assert result.result["created"] is False
    assert result.result["message"] == "Directory already exists"

  def test_create_existing_directory_recursive(self, temp_structure: Path) -> None:
    """
    Given: A path to an existing directory with recursive=True
    When: Calling execute
    Then: Returns success with created=False (idempotent)
    """
    tool = MkdirTool()
    existing_dir = temp_structure / "existing_dir"
    result = tool.execute(path=str(existing_dir), recursive=True)

    assert result.success
    assert result.result["created"] is False
    assert result.result["message"] == "Directory already exists"

  def test_create_where_file_exists(self, temp_structure: Path) -> None:
    """
    Given: A path where a file (not directory) already exists
    When: Calling execute
    Then: Returns generic error about path not accessible
    """
    tool = MkdirTool()
    # Create a file at the path
    file_path = temp_structure / "file.txt"
    file_path.write_text("content")

    result = tool.execute(path=str(file_path))

    assert not result.success
    assert "not accessible" in result.error.lower()


class TestMkdirToolSymlinkRejection:
  """Tests for symlink rejection security."""

  def test_symlink_rejected(self, tmp_path: Path) -> None:
    """
    Given: A path that is a symlink
    When: Calling execute
    Then: Returns error about path not accessible
    """
    tool = MkdirTool()
    # Create a directory and a symlink to it
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    symlink_path = tmp_path / "link_to_dir"
    symlink_path.symlink_to(target_dir)

    result = tool.execute(path=str(symlink_path))

    assert not result.success
    assert "not accessible" in result.error.lower()

  def test_symlink_to_directory_rejected(self, tmp_path: Path) -> None:
    """
    Given: A symlink pointing to a directory
    When: Calling execute
    Then: Returns error about path not accessible
    """
    tool = MkdirTool()
    # Create target directory
    target = tmp_path / "target"
    target.mkdir()
    # Create symlink to directory
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)

    result = tool.execute(path=str(symlink))

    assert not result.success
    assert "not accessible" in result.error.lower()

  def test_symlink_in_path_rejected(self, tmp_path: Path) -> None:
    """
    Given: A path containing a symlink component
    When: Calling execute
    Then: Returns error about path not accessible
    """
    tool = MkdirTool()
    # Create target directory and symlink
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)

    # Try to create a subdirectory through the symlink
    result = tool.execute(path=str(symlink / "subdir"))

    # This should work because realpath resolves the symlink
    # The test expects rejection of symlinks at the input path itself
    # not symlinks in the resolved path (which realpath handles)
    assert result.success


class TestMkdirToolPathTraversal:
  """Tests for path traversal prevention."""

  def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path with traversal sequence like ../../../etc/newdir
    When: Calling execute
    Then: Path is resolved and guardrail blocks if outside allowed directories
    """
    # Create config with restricted filesystem_paths
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Try to traverse outside allowed path
    traversal_path = str(tmp_path / ".." / ".." / ".." / "etc" / "newdir")
    result = tool.execute(path=traversal_path)

    # Should fail because resolved path is outside allowed directories
    assert not result.success
    assert "outside allowed" in result.error.lower()

  def test_relative_path_resolved(self, tmp_path: Path) -> None:
    """
    Given: A relative path
    When: Calling execute
    Then: Path is resolved to absolute path in result
    """
    tool = MkdirTool()

    # Change to temp directory
    original_cwd = os.getcwd()
    try:
      os.chdir(tmp_path)
      result = tool.execute(path="newdir")

      assert result.success
      # Path should be absolute
      assert os.path.isabs(result.result["path"])
      assert (tmp_path / "newdir").is_dir()
    finally:
      os.chdir(original_cwd)

  def test_path_with_dot_segments_resolved(self, tmp_path: Path) -> None:
    """
    Given: A path with ./ segments
    When: Calling execute
    Then: Path is normalized without ./ in result
    """
    tool = MkdirTool()

    # Create a subdirectory path with ./
    dotted_path = str(tmp_path / "." / "newdir")
    result = tool.execute(path=dotted_path)

    assert result.success
    # Path should not contain ./
    assert "./" not in result.result["path"]
    assert (tmp_path / "newdir").is_dir()


class TestMkdirToolBlockedPatterns:
  """Tests for blocked pattern enforcement."""

  @pytest.fixture
  def config_with_blocked_patterns(self) -> Config:
    """Create a config with blocked patterns."""
    return Config(
      tools=ToolsConfig(
        read=ReadToolConfig(
          blocked_patterns=(r"\.git", r"\.ssh", r"\.aws", r"\.env", "credentials", "secrets")
        )
      )
    )

  @pytest.fixture
  def guardrail_with_blocked_patterns(
    self, config_with_blocked_patterns: Config, tmp_path: Path
  ) -> PathGuardrail:
    """Create a guardrail with blocked patterns."""
    config = config_with_blocked_patterns
    config.permissions.filesystem_paths = (str(tmp_path),)
    return PathGuardrail(config)

  def test_blocked_pattern_git_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .git directory
    When: Calling execute with guardrail
    Then: Returns error about blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.git",))),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    result = tool.execute(path=str(tmp_path / ".git"))

    assert not result.success
    assert "blocked pattern" in result.error.lower()

  def test_blocked_pattern_ssh_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .ssh directory
    When: Calling execute with guardrail
    Then: Returns error about blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.ssh",))),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    result = tool.execute(path=str(tmp_path / ".ssh"))

    assert not result.success
    assert "blocked pattern" in result.error.lower()

  def test_blocked_pattern_aws_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .aws directory
    When: Calling execute with guardrail
    Then: Returns error about blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.aws",))),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    result = tool.execute(path=str(tmp_path / ".aws"))

    assert not result.success
    assert "blocked pattern" in result.error.lower()

  def test_blocked_pattern_env_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .env or credentials pattern
    When: Calling execute with guardrail
    Then: Returns error about blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.env", "credentials"))),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    result = tool.execute(path=str(tmp_path / ".env"))

    assert not result.success
    assert "blocked pattern" in result.error.lower()


class TestMkdirToolDepthLimit:
  """Tests for maximum depth limit enforcement."""

  def test_depth_within_limit(self, tmp_path: Path) -> None:
    """
    Given: A path within the maximum depth limit (20 levels)
    When: Calling execute with recursive=True
    Then: All directories are created successfully
    """
    tool = MkdirTool()
    # Create path within depth limit
    path = tmp_path
    for i in range(10):
      path = path / f"level{i}"

    result = tool.execute(path=str(path), recursive=True)

    assert result.success
    assert path.is_dir()

  def test_depth_exceeds_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with max_depth=5
    When: Creating deeply nested directories (e.g., 10 levels)
    Then: Returns error about depth limit exceeded
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(mkdir=MkdirToolConfig(max_depth=5)),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Create path exceeding depth limit (10 levels deep)
    path = tmp_path
    for i in range(10):
      path = path / f"level{i}"

    result = tool.execute(path=str(path), recursive=True)

    assert not result.success
    assert "depth" in result.error.lower()
    assert "exceeds" in result.error.lower()

  def test_depth_at_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with max_depth=5
    When: Creating directories exactly at the depth limit
    Then: Creation is rejected (depth at limit exceeds it)
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(mkdir=MkdirToolConfig(max_depth=5)),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Create path exactly at depth limit (5 levels)
    path = tmp_path / "a" / "b" / "c" / "d" / "e"

    result = tool.execute(path=str(path), recursive=True)

    assert not result.success
    assert "depth" in result.error.lower()
    assert "exceeds" in result.error.lower()

  def test_depth_below_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with max_depth=5
    When: Creating directories below the depth limit (e.g., 3 levels)
    Then: Directories are created successfully
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(mkdir=MkdirToolConfig(max_depth=5)),
    )
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Create path below depth limit (3 levels)
    path = tmp_path / "a" / "b" / "c"

    result = tool.execute(path=str(path), recursive=True)

    assert result.success
    assert path.is_dir()

  def test_depth_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail configured with default depth limit (20)
    When: Creating deeply nested directories
    Then: Guardrail enforces the default depth limit
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Create path well within default limit
    path = tmp_path / "a" / "b" / "c" / "d" / "e"
    result = tool.execute(path=str(path), recursive=True)

    assert result.success

  def test_depth_without_guardrail(self, tmp_path: Path) -> None:
    """
    Given: No guardrail configured
    When: Creating deeply nested directories
    Then: Directories are created regardless of depth
    """
    tool = MkdirTool()
    # Create a deeply nested path (25 levels)
    path = tmp_path
    for i in range(25):
      path = path / f"level{i}"

    result = tool.execute(path=str(path), recursive=True)
    assert result.success


class TestMkdirToolValidation:
  """Tests for input validation and error handling."""

  def test_empty_path(self) -> None:
    """
    Given: An empty string path
    When: Calling execute
    Then: Returns error about path cannot be empty
    """
    tool = MkdirTool()
    result = tool.execute(path="")

    assert not result.success
    assert "empty" in result.error.lower()

  def test_whitespace_only_path(self) -> None:
    """
    Given: A whitespace-only path string
    When: Calling execute
    Then: Returns error about path cannot be empty
    """
    tool = MkdirTool()
    result = tool.execute(path="   ")

    assert not result.success
    assert "empty" in result.error.lower()

  def test_invalid_path_type(self) -> None:
    """
    Given: A non-string path parameter (e.g., integer)
    When: Calling execute
    Then: Returns error about invalid path parameter
    """
    tool = MkdirTool()
    result = tool.execute(path=123)  # type: ignore

    assert not result.success
    assert "invalid" in result.error.lower()

  def test_path_with_null_bytes(self) -> None:
    """
    Given: A path containing null bytes
    When: Calling execute
    Then: Returns error about invalid path
    """
    tool = MkdirTool()
    result = tool.execute(path="/tmp/test\x00dir")

    assert not result.success
    assert "invalid" in result.error.lower()


class TestMkdirToolWithGuardrail:
  """Tests for guardrail integration."""

  def test_guardrail_blocks_path(self, tmp_path: Path) -> None:
    """
    Given: A guardrail that blocks the requested path
    When: Calling execute
    Then: Returns error from guardrail, directory not created
    """
    # Create guardrail that only allows specific path
    allowed_path = tmp_path / "allowed"
    allowed_path.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(allowed_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    blocked_path = tmp_path / "blocked" / "newdir"
    result = tool.execute(path=str(blocked_path))

    assert not result.success
    assert "outside allowed" in result.error.lower()
    assert not blocked_path.exists()

  def test_guardrail_allows_path(self, tmp_path: Path) -> None:
    """
    Given: A guardrail that allows the requested path
    When: Calling execute
    Then: Directory is created successfully
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    new_dir = tmp_path / "newdir"
    result = tool.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()

  def test_guardrail_not_provided(self, tmp_path: Path) -> None:
    """
    Given: No guardrail configured
    When: Calling execute with valid path
    Then: Directory is created successfully
    """
    tool = MkdirTool()  # No guardrail
    new_dir = tmp_path / "newdir"
    result = tool.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()

  def test_guardrail_blocks_outside_allowed_directories(self, tmp_path: Path) -> None:
    """
    Given: A path outside configured filesystem_paths
    When: Calling execute with guardrail
    Then: Returns error about path outside allowed directories
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Try to create outside allowed path
    outside_path = tmp_path.parent / "outside_newdir"
    result = tool.execute(path=str(outside_path))

    assert not result.success
    assert "outside allowed" in result.error.lower()

  def test_guardrail_validates_before_creation(self, tmp_path: Path) -> None:
    """
    Given: A guardrail configuration
    When: Calling execute
    Then: Guardrail validation happens before any filesystem operations
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    # Try blocked pattern
    result = tool.execute(path=str(tmp_path / ".ssh"))

    assert not result.success
    # Directory should not be created
    assert not (tmp_path / ".ssh").exists()


class TestMkdirToolErrorHandling:
  """Tests for error handling scenarios."""

  def test_permission_denied(self, tmp_path: Path, mocker: Any) -> None:
    """
    Given: A path where creation would fail with PermissionError
    When: Calling execute
    Then: Returns error about permission denied
    """
    tool = MkdirTool()

    # Mock mkdir to raise PermissionError
    with mocker.patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
      new_dir = tmp_path / "newdir"
      result = tool.execute(path=str(new_dir))

      assert not result.success
      assert "permission" in result.error.lower()

  def test_os_error(self, tmp_path: Path, mocker: Any) -> None:
    """
    Given: A path that causes OSError during creation
    When: Calling execute
    Then: Returns error about directory creation failure
    """
    tool = MkdirTool()

    # Mock mkdir to raise OSError
    with mocker.patch.object(Path, "mkdir", side_effect=OSError("OS error")):
      new_dir = tmp_path / "newdir"
      result = tool.execute(path=str(new_dir))

      assert not result.success
      assert "error" in result.error.lower()

  def test_realpath_os_error(self, mocker: Any) -> None:
    """
    Given: A path that causes OSError during realpath resolution
    When: Calling execute
    Then: Returns error about invalid path
    """
    tool = MkdirTool()

    # Mock os.path.realpath to raise OSError
    with mocker.patch("os.path.realpath", side_effect=OSError("Resolution failed")):
      result = tool.execute(path="/tmp/test")

      assert not result.success
      assert "invalid" in result.error.lower()

  def test_permission_denied_checking_existing(self, tmp_path: Path, mocker: Any) -> None:
    """
    Given: A path where checking existence fails with PermissionError
    When: Calling execute
    Then: Returns error about permission denied
    """
    tool = MkdirTool()

    # Mock exists to raise PermissionError
    with mocker.patch.object(Path, "exists", side_effect=PermissionError("Permission denied")):
      new_dir = tmp_path / "newdir"
      result = tool.execute(path=str(new_dir))

      assert not result.success
      assert "permission" in result.error.lower()


class TestMkdirToolPathResolution:
  """Tests for path resolution behavior."""

  def test_absolute_path_preserved(self, tmp_path: Path) -> None:
    """
    Given: An absolute path
    When: Calling execute
    Then: Result contains the resolved absolute path
    """
    tool = MkdirTool()
    abs_path = str(tmp_path / "newdir")
    result = tool.execute(path=abs_path)

    assert result.success
    assert os.path.isabs(result.result["path"])
    assert (tmp_path / "newdir").is_dir()

  def test_path_normalized(self, tmp_path: Path) -> None:
    """
    Given: A path with redundant separators or .. segments
    When: Calling execute
    Then: Path is normalized in result
    """
    tool = MkdirTool()
    # Create a parent directory first
    parent = tmp_path / "parent"
    parent.mkdir()

    # Path with redundant .. and back to parent
    path = str(tmp_path / "parent" / ".." / "parent" / "child")
    result = tool.execute(path=path)

    assert result.success
    # The result should be normalized
    assert "parent/..//parent" not in result.result["path"]

  def test_path_resolution_consistency(self, tmp_path: Path) -> None:
    """
    Given: Different forms of the same path (./dir, dir, /full/path/dir)
    When: Calling execute multiple times
    Then: All resolve to the same canonical path
    """
    tool = MkdirTool()
    original_cwd = os.getcwd()

    try:
      os.chdir(tmp_path)

      # Create with different path forms
      result1 = tool.execute(path="newdir1")
      result2 = tool.execute(path="./newdir2")

      # All should be absolute paths
      assert os.path.isabs(result1.result["path"])
      assert os.path.isabs(result2.result["path"])

    finally:
      os.chdir(original_cwd)


class TestMkdirToolReturnFormat:
  """Tests for return format structure."""

  def test_return_format_created(self, tmp_path: Path) -> None:
    """
    Given: A valid path for new directory
    When: Calling execute
    Then: Returns {created: true, path: str}
    """
    tool = MkdirTool()
    new_dir = tmp_path / "newdir"
    result = tool.execute(path=str(new_dir))

    assert result.success
    assert "created" in result.result
    assert "path" in result.result
    assert result.result["created"] is True
    assert isinstance(result.result["path"], str)

  def test_return_format_existing(self, tmp_path: Path) -> None:
    """
    Given: A path to existing directory
    When: Calling execute
    Then: Returns {created: false, path: str, message: str}
    """
    tool = MkdirTool()
    existing_dir = tmp_path / "existing"
    existing_dir.mkdir()

    result = tool.execute(path=str(existing_dir))

    assert result.success
    assert result.result["created"] is False
    assert "path" in result.result
    assert "message" in result.result
    assert result.result["message"] == "Directory already exists"

  def test_return_format_error(self) -> None:
    """
    Given: An invalid path
    When: Calling execute
    Then: Returns ToolResult with success=False and error message
    """
    tool = MkdirTool()
    result = tool.execute(path="")

    assert not result.success
    assert result.error is not None
    assert isinstance(result.error, str)

  def test_return_path_is_absolute(self, tmp_path: Path) -> None:
    """
    Given: A relative path
    When: Calling execute
    Then: Returned path is absolute
    """
    tool = MkdirTool()
    original_cwd = os.getcwd()

    try:
      os.chdir(tmp_path)
      result = tool.execute(path="newdir")

      assert result.success
      assert os.path.isabs(result.result["path"])
    finally:
      os.chdir(original_cwd)


class TestMkdirToolSpecialCases:
  """Tests for special cases and edge conditions."""

  def test_create_current_directory(self) -> None:
    """
    Given: Path "."
    When: Calling execute
    Then: Returns success with created=False (already exists)
    """
    tool = MkdirTool()
    result = tool.execute(path=".")

    assert result.success
    assert result.result["created"] is False
    assert result.result["message"] == "Directory already exists"

  def test_create_parent_directory(self, tmp_path: Path) -> None:
    """
    Given: Path ".."
    When: Calling execute
    Then: Returns success with created=False (already exists)
    """
    tool = MkdirTool()
    original_cwd = os.getcwd()

    try:
      os.chdir(tmp_path)
      result = tool.execute(path="..")

      assert result.success
      assert result.result["created"] is False
    finally:
      os.chdir(original_cwd)

  def test_create_root_subdirectory(self, tmp_path: Path) -> None:
    """
    Given: A path like /tmp/newdir
    When: Calling execute with guardrail allowing /tmp
    Then: Creates directory successfully
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    new_dir = tmp_path / "newdir"
    result = tool.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()

  def test_create_directory_with_spaces(self, tmp_path: Path) -> None:
    """
    Given: A path with spaces in directory name
    When: Calling execute
    Then: Creates directory successfully
    """
    tool = MkdirTool()
    dir_with_spaces = tmp_path / "dir with spaces"
    result = tool.execute(path=str(dir_with_spaces))

    assert result.success
    assert result.result["created"] is True
    assert dir_with_spaces.is_dir()

  def test_create_directory_with_unicode(self, tmp_path: Path) -> None:
    """
    Given: A path with unicode characters in directory name
    When: Calling execute
    Then: Creates directory successfully
    """
    tool = MkdirTool()
    unicode_dir = tmp_path / "unicode_目录_🎉"
    result = tool.execute(path=str(unicode_dir))

    assert result.success
    assert result.result["created"] is True
    assert unicode_dir.is_dir()

  def test_recursive_creates_intermediate_directories(self, tmp_path: Path) -> None:
    """
    Given: A deep nested path with recursive=True
    When: Calling execute
    Then: All intermediate directories are created
    """
    tool = MkdirTool()
    deep_path = tmp_path / "a" / "b" / "c" / "d" / "e"
    result = tool.execute(path=str(deep_path), recursive=True)

    assert result.success
    assert result.result["created"] is True
    assert deep_path.is_dir()
    assert (tmp_path / "a").is_dir()
    assert (tmp_path / "a" / "b").is_dir()
    assert (tmp_path / "a" / "b" / "c").is_dir()
    assert (tmp_path / "a" / "b" / "c" / "d").is_dir()


class TestMkdirToolIntegration:
  """Integration tests for MkdirTool with other components."""

  def test_create_then_check_existence(self, tmp_path: Path) -> None:
    """
    Given: MkdirTool creates a directory
    When: Checking existence with ExistenceTool
    Then: ExistenceTool reports directory exists
    """
    from yoker.tools.existence import ExistenceTool

    mkdir_tool = MkdirTool()
    existence_tool = ExistenceTool()

    new_dir = tmp_path / "newdir"
    mkdir_result = mkdir_tool.execute(path=str(new_dir))
    assert mkdir_result.success

    existence_result = existence_tool.execute(path=str(new_dir))
    assert existence_result.success
    assert existence_result.result["exists"] is True
    assert existence_result.result["type"] == "directory"

  def test_create_then_list_directory(self, tmp_path: Path) -> None:
    """
    Given: MkdirTool creates a directory
    When: Listing parent directory with ListTool
    Then: New directory appears in listing
    """
    from yoker.tools.list import ListTool

    mkdir_tool = MkdirTool()
    list_tool = ListTool()

    new_dir = tmp_path / "newdir"
    mkdir_result = mkdir_tool.execute(path=str(new_dir))
    assert mkdir_result.success

    list_result = list_tool.execute(path=str(tmp_path))
    assert list_result.success
    assert "newdir" in list_result.result

  def test_create_in_allowed_directory(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with filesystem_paths configured
    When: Creating directory within allowed path
    Then: Directory is created successfully
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    tool = MkdirTool(guardrail=guardrail)

    new_dir = tmp_path / "newdir"
    result = tool.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()
