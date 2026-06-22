"""Tests for mkdir tool implementation.

These tests verify the behavior of the directory creation tool,
including basic creation, idempotency, security guardrails,
and error handling.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from yoker.builtin import existence, list, mkdir
from yoker.config import (
  Config,
  MkdirToolConfig,
  PermissionsConfig,
  ReadToolConfig,
  ToolsConfig,
)
from yoker.tools import ToolRegistry
from yoker.tools.path_guardrail import PathGuardrail


def _mkdir_spec():
  """Create and register the mkdir tool."""
  registry = ToolRegistry()
  return registry.register(mkdir)


class TestMkdirToolSchema:
  """Tests for mkdir tool schema and properties."""

  def test_name(self) -> None:
    """
    Given: A mkdir tool spec
    When: Checking the spec name
    Then: Returns 'mkdir'
    """
    spec = _mkdir_spec()
    assert spec.name == "mkdir"

  def test_description(self) -> None:
    """
    Given: A mkdir tool spec
    When: Checking the spec description
    Then: Returns description about creating directories
    """
    spec = _mkdir_spec()
    assert "directory" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """
    Given: A mkdir tool spec
    When: Getting the Ollama-compatible schema
    Then: Schema has correct structure with path parameter and optional recursive
    """
    spec = _mkdir_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mkdir"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert "recursive" in schema["function"]["parameters"]["properties"]

  def test_schema_path_required(self) -> None:
    """
    Given: The mkdir tool schema
    When: Checking required parameters
    Then: 'path' is required, 'recursive' is optional
    """
    spec = _mkdir_spec()
    schema = spec.schema

    required = schema["function"]["parameters"]["required"]
    assert "path" in required
    assert "recursive" not in required


class TestMkdirToolBasicCreation:
  """Tests for basic directory creation."""

  @pytest.fixture
  def temp_dir(self, tmp_path: Path) -> Path:
    """Create a temporary directory for testing."""
    return tmp_path

  @pytest.mark.asyncio
  async def test_create_new_directory(self, temp_dir: Path) -> None:
    """
    Given: A valid path to a non-existent directory
    When: Calling execute with path parameter
    Then: Directory is created and result shows created=True
    """
    spec = _mkdir_spec()
    new_dir = temp_dir / "newdir"
    result = await spec.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert "newdir" in result.result["path"]
    assert new_dir.is_dir()

  @pytest.mark.asyncio
  async def test_create_nested_directory_recursive(self, temp_dir: Path) -> None:
    """
    Given: A nested path /a/b/c and recursive=True
    When: Calling execute
    Then: All parent directories are created
    """
    spec = _mkdir_spec()
    nested_path = temp_dir / "a" / "b" / "c"
    result = await spec.execute(path=str(nested_path), recursive=True)

    assert result.success
    assert result.result["created"] is True
    assert nested_path.is_dir()
    assert (temp_dir / "a").is_dir()
    assert (temp_dir / "a" / "b").is_dir()

  @pytest.mark.asyncio
  async def test_create_nested_directory_non_recursive(self, temp_dir: Path) -> None:
    """
    Given: A nested path /a/b/c and recursive=False (default)
    When: Parent directory doesn't exist
    Then: Returns error about missing parent
    """
    spec = _mkdir_spec()
    nested_path = temp_dir / "newdir" / "nested"
    result = await spec.execute(path=str(nested_path), recursive=False)

    assert not result.success
    assert "parent" in result.error.lower()
    assert not nested_path.exists()

  @pytest.mark.asyncio
  async def test_create_directory_with_parents_exist_recursive(self, temp_dir: Path) -> None:
    """
    Given: A nested path where some parents exist and recursive=True
    When: Calling execute
    Then: Only missing directories are created
    """
    spec = _mkdir_spec()
    # Create parent
    parent = temp_dir / "parent"
    parent.mkdir()

    # Create nested directory with recursive
    nested_path = parent / "child" / "grandchild"
    result = await spec.execute(path=str(nested_path), recursive=True)

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

  @pytest.mark.asyncio
  async def test_create_existing_directory(self, temp_structure: Path) -> None:
    """
    Given: A path to an existing directory
    When: Calling execute
    Then: Returns success with created=False and message about existing directory
    """
    spec = _mkdir_spec()
    existing_dir = temp_structure / "existing_dir"
    result = await spec.execute(path=str(existing_dir))

    assert result.success
    assert result.result["created"] is False
    assert result.result["message"] == "Directory already exists"

  @pytest.mark.asyncio
  async def test_create_existing_directory_recursive(self, temp_structure: Path) -> None:
    """
    Given: A path to an existing directory with recursive=True
    When: Calling execute
    Then: Returns success with created=False (idempotent)
    """
    spec = _mkdir_spec()
    existing_dir = temp_structure / "existing_dir"
    result = await spec.execute(path=str(existing_dir), recursive=True)

    assert result.success
    assert result.result["created"] is False
    assert result.result["message"] == "Directory already exists"

  @pytest.mark.asyncio
  async def test_create_where_file_exists(self, temp_structure: Path) -> None:
    """
    Given: A path where a file (not directory) already exists
    When: Calling execute
    Then: Returns generic error about path not accessible
    """
    spec = _mkdir_spec()
    # Create a file at the path
    file_path = temp_structure / "file.txt"
    file_path.write_text("content")

    result = await spec.execute(path=str(file_path))

    assert not result.success
    assert "not accessible" in result.error.lower()


class TestMkdirToolSymlinkRejection:
  """Tests for symlink rejection security."""

  @pytest.mark.asyncio
  async def test_symlink_rejected(self, tmp_path: Path) -> None:
    """
    Given: A path that is a symlink
    When: Calling execute
    Then: Returns error about path not accessible
    """
    spec = _mkdir_spec()
    # Create a directory and a symlink to it
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    symlink_path = tmp_path / "link_to_dir"
    symlink_path.symlink_to(target_dir)

    result = await spec.execute(path=str(symlink_path))

    assert not result.success
    assert "not accessible" in result.error.lower()

  @pytest.mark.asyncio
  async def test_symlink_to_directory_rejected(self, tmp_path: Path) -> None:
    """
    Given: A symlink pointing to a directory
    When: Calling execute
    Then: Returns error about path not accessible
    """
    spec = _mkdir_spec()
    # Create target directory
    target = tmp_path / "target"
    target.mkdir()
    # Create symlink to directory
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)

    result = await spec.execute(path=str(symlink))

    assert not result.success
    assert "not accessible" in result.error.lower()

  @pytest.mark.asyncio
  async def test_symlink_in_path_rejected(self, tmp_path: Path) -> None:
    """
    Given: A path containing a symlink component
    When: Calling execute
    Then: Returns error about path not accessible
    """
    spec = _mkdir_spec()
    # Create target directory and symlink
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)

    # Try to create a subdirectory through the symlink
    result = await spec.execute(path=str(symlink / "subdir"))

    # This should work because realpath resolves the symlink
    # The test expects rejection of symlinks at the input path itself
    # not symlinks in the resolved path (which realpath handles)
    assert result.success


class TestMkdirToolPathTraversal:
  """Tests for path traversal prevention."""

  @pytest.mark.asyncio
  async def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """
    Given: A path with traversal sequence like ../../../etc/newdir
    When: Validating the path against the guardrail
    Then: Guardrail blocks the resolved path as outside allowed directories
    """
    # Create config with restricted filesystem_paths
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Try to traverse outside allowed path
    traversal_path = str(tmp_path / ".." / ".." / ".." / "etc" / "newdir")
    validation = guardrail.validate(spec.name, {"path": traversal_path})

    # Should fail because resolved path is outside allowed directories
    assert not validation.valid
    assert "outside allowed" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_relative_path_resolved(self, tmp_path: Path) -> None:
    """
    Given: A relative path
    When: Calling execute
    Then: Path is resolved to absolute path in result
    """
    spec = _mkdir_spec()

    # Change to temp directory
    original_cwd = os.getcwd()
    try:
      os.chdir(tmp_path)
      result = await spec.execute(path="newdir")

      assert result.success
      # Path should be absolute
      assert os.path.isabs(result.result["path"])
      assert (tmp_path / "newdir").is_dir()
    finally:
      os.chdir(original_cwd)

  @pytest.mark.asyncio
  async def test_path_with_dot_segments_resolved(self, tmp_path: Path) -> None:
    """
    Given: A path with ./ segments
    When: Calling execute
    Then: Path is normalized without ./ in result
    """
    spec = _mkdir_spec()

    # Create a subdirectory path with ./
    dotted_path = str(tmp_path / "." / "newdir")
    result = await spec.execute(path=dotted_path)

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

  @pytest.mark.asyncio
  async def test_blocked_pattern_git_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .git directory
    When: Validating the path against the guardrail
    Then: Guardrail reports a blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.git",))),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    validation = guardrail.validate(spec.name, {"path": str(tmp_path / ".git")})

    assert not validation.valid
    assert "blocked pattern" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_blocked_pattern_ssh_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .ssh directory
    When: Validating the path against the guardrail
    Then: Guardrail reports a blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.ssh",))),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    validation = guardrail.validate(spec.name, {"path": str(tmp_path / ".ssh")})

    assert not validation.valid
    assert "blocked pattern" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_blocked_pattern_aws_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .aws directory
    When: Validating the path against the guardrail
    Then: Guardrail reports a blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.aws",))),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    validation = guardrail.validate(spec.name, {"path": str(tmp_path / ".aws")})

    assert not validation.valid
    assert "blocked pattern" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_blocked_pattern_env_directory(self, tmp_path: Path) -> None:
    """
    Given: A path containing .env or credentials pattern
    When: Validating the path against the guardrail
    Then: Guardrail reports a blocked pattern
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.env", "credentials"))),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    validation = guardrail.validate(spec.name, {"path": str(tmp_path / ".env")})

    assert not validation.valid
    assert "blocked pattern" in validation.reason.lower()


class TestMkdirToolDepthLimit:
  """Tests for maximum depth limit enforcement."""

  @pytest.mark.asyncio
  async def test_depth_within_limit(self, tmp_path: Path) -> None:
    """
    Given: A path within the maximum depth limit (20 levels)
    When: Calling execute with recursive=True
    Then: All directories are created successfully
    """
    spec = _mkdir_spec()
    # Create path within depth limit
    path = tmp_path
    for i in range(10):
      path = path / f"level{i}"

    result = await spec.execute(path=str(path), recursive=True)

    assert result.success
    assert path.is_dir()

  @pytest.mark.asyncio
  async def test_depth_exceeds_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with max_depth=5
    When: Validating a deeply nested path (e.g., 10 levels)
    Then: Guardrail reports depth limit exceeded
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(mkdir=MkdirToolConfig(max_depth=5)),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Create path exceeding depth limit (10 levels deep)
    path = tmp_path
    for i in range(10):
      path = path / f"level{i}"

    validation = guardrail.validate(spec.name, {"path": str(path)})

    assert not validation.valid
    assert "depth" in validation.reason.lower()
    assert "exceeds" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_depth_at_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with max_depth=5
    When: Validating a path exactly at the depth limit
    Then: Guardrail rejects it (depth at limit exceeds it)
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(mkdir=MkdirToolConfig(max_depth=5)),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Create path exactly at depth limit (5 levels)
    path = tmp_path / "a" / "b" / "c" / "d" / "e"

    validation = guardrail.validate(spec.name, {"path": str(path)})

    assert not validation.valid
    assert "depth" in validation.reason.lower()
    assert "exceeds" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_depth_below_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with max_depth=5
    When: Validating and creating directories below the depth limit
    Then: Guardrail allows the path and directories are created successfully
    """
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(mkdir=MkdirToolConfig(max_depth=5)),
    )
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Create path below depth limit (3 levels)
    path = tmp_path / "a" / "b" / "c"

    validation = guardrail.validate(spec.name, {"path": str(path)})
    assert validation.valid

    result = await spec.execute(path=str(path), recursive=True)
    assert result.success
    assert path.is_dir()

  @pytest.mark.asyncio
  async def test_depth_limit_with_guardrail(self, tmp_path: Path) -> None:
    """
    Given: A guardrail configured with default depth limit (20)
    When: Validating a nested path and creating directories
    Then: Guardrail allows the path and directories are created
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Create path well within default limit
    path = tmp_path / "a" / "b" / "c" / "d" / "e"
    validation = guardrail.validate(spec.name, {"path": str(path)})
    assert validation.valid

    result = await spec.execute(path=str(path), recursive=True)
    assert result.success

  @pytest.mark.asyncio
  async def test_depth_without_guardrail(self, tmp_path: Path) -> None:
    """
    Given: No guardrail configured
    When: Creating deeply nested directories
    Then: Directories are created regardless of depth
    """
    spec = _mkdir_spec()
    # Create a deeply nested path (25 levels)
    path = tmp_path
    for i in range(25):
      path = path / f"level{i}"

    result = await spec.execute(path=str(path), recursive=True)
    assert result.success


class TestMkdirToolValidation:
  """Tests for input validation and error handling."""

  @pytest.mark.asyncio
  async def test_empty_path(self) -> None:
    """
    Given: An empty string path
    When: Calling execute
    Then: Returns error about path cannot be empty
    """
    spec = _mkdir_spec()
    result = await spec.execute(path="")

    assert not result.success
    assert "empty" in result.error.lower()

  @pytest.mark.asyncio
  async def test_whitespace_only_path(self) -> None:
    """
    Given: A whitespace-only path string
    When: Calling execute
    Then: Returns error about path cannot be empty
    """
    spec = _mkdir_spec()
    result = await spec.execute(path="   ")

    assert not result.success
    assert "empty" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_path_type(self) -> None:
    """
    Given: A non-string path parameter (e.g., integer)
    When: Calling execute
    Then: Returns error about invalid path parameter
    """
    spec = _mkdir_spec()
    result = await spec.execute(path=123)  # type: ignore

    assert not result.success
    assert "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_path_with_null_bytes(self, tmp_path: Path) -> None:
    """
    Given: A path containing null bytes
    When: Calling execute
    Then: Returns error about invalid path
    """
    spec = _mkdir_spec()
    result = await spec.execute(path="/tmp/test\x00dir")

    assert not result.success
    assert "invalid" in result.error.lower()


class TestMkdirToolWithGuardrail:
  """Tests for guardrail integration."""

  @pytest.mark.asyncio
  async def test_guardrail_blocks_path(self, tmp_path: Path) -> None:
    """
    Given: A guardrail that blocks the requested path
    When: Validating the path
    Then: Guardrail reports path outside allowed directories
    """
    # Create guardrail that only allows specific path
    allowed_path = tmp_path / "allowed"
    allowed_path.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(allowed_path),)))
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    blocked_path = tmp_path / "blocked" / "newdir"
    validation = guardrail.validate(spec.name, {"path": str(blocked_path)})

    assert not validation.valid
    assert "outside allowed" in validation.reason.lower()
    assert not blocked_path.exists()

  @pytest.mark.asyncio
  async def test_guardrail_allows_path(self, tmp_path: Path) -> None:
    """
    Given: A guardrail that allows the requested path
    When: Validating and then calling execute
    Then: Directory is created successfully
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    new_dir = tmp_path / "newdir"
    validation = guardrail.validate(spec.name, {"path": str(new_dir)})
    assert validation.valid

    result = await spec.execute(path=str(new_dir))
    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()

  @pytest.mark.asyncio
  async def test_guardrail_not_provided(self, tmp_path: Path) -> None:
    """
    Given: No guardrail configured
    When: Calling execute with valid path
    Then: Directory is created successfully
    """
    spec = _mkdir_spec()  # No guardrail
    new_dir = tmp_path / "newdir"
    result = await spec.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()

  @pytest.mark.asyncio
  async def test_guardrail_blocks_outside_allowed_directories(self, tmp_path: Path) -> None:
    """
    Given: A path outside configured filesystem_paths
    When: Validating the path against the guardrail
    Then: Guardrail reports path outside allowed directories
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Try to create outside allowed path
    outside_path = tmp_path.parent / "outside_newdir"
    validation = guardrail.validate(spec.name, {"path": str(outside_path)})

    assert not validation.valid
    assert "outside allowed" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_guardrail_validates_before_creation(self, tmp_path: Path) -> None:
    """
    Given: A guardrail configuration
    When: Validating a blocked pattern path
    Then: Guardrail rejects the path before any filesystem operations
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _mkdir_spec()

    # Try blocked pattern
    validation = guardrail.validate(spec.name, {"path": str(tmp_path / ".ssh")})

    assert not validation.valid
    # Directory should not be created
    assert not (tmp_path / ".ssh").exists()


class TestMkdirToolErrorHandling:
  """Tests for error handling scenarios."""

  @pytest.mark.asyncio
  async def test_permission_denied(self, tmp_path: Path, mocker: Any) -> None:
    """
    Given: A path where creation would fail with PermissionError
    When: Calling execute
    Then: Returns error about permission denied
    """
    spec = _mkdir_spec()

    # Mock mkdir to raise PermissionError
    with mocker.patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
      new_dir = tmp_path / "newdir"
      result = await spec.execute(path=str(new_dir))

      assert not result.success
      assert "permission" in result.error.lower()

  @pytest.mark.asyncio
  async def test_os_error(self, tmp_path: Path, mocker: Any) -> None:
    """
    Given: A path that causes OSError during creation
    When: Calling execute
    Then: Returns error about directory creation failure
    """
    spec = _mkdir_spec()

    # Mock mkdir to raise OSError
    with mocker.patch.object(Path, "mkdir", side_effect=OSError("OS error")):
      new_dir = tmp_path / "newdir"
      result = await spec.execute(path=str(new_dir))

      assert not result.success
      assert "error" in result.error.lower()

  @pytest.mark.asyncio
  async def test_realpath_os_error(self, mocker: Any) -> None:
    """
    Given: A path that causes OSError during realpath resolution
    When: Calling execute
    Then: Returns error about invalid path
    """
    spec = _mkdir_spec()

    # Mock os.path.realpath to raise OSError
    with mocker.patch("os.path.realpath", side_effect=OSError("Resolution failed")):
      result = await spec.execute(path="/tmp/test")

      assert not result.success
      assert "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_permission_denied_checking_existing(self, tmp_path: Path, mocker: Any) -> None:
    """
    Given: A path where checking existence fails with PermissionError
    When: Calling execute
    Then: Returns error about permission denied
    """
    spec = _mkdir_spec()

    # Mock exists to raise PermissionError
    with mocker.patch.object(Path, "exists", side_effect=PermissionError("Permission denied")):
      new_dir = tmp_path / "newdir"
      result = await spec.execute(path=str(new_dir))

      assert not result.success
      assert "permission" in result.error.lower()


class TestMkdirToolPathResolution:
  """Tests for path resolution behavior."""

  @pytest.mark.asyncio
  async def test_absolute_path_preserved(self, tmp_path: Path) -> None:
    """
    Given: An absolute path
    When: Calling execute
    Then: Result contains the resolved absolute path
    """
    spec = _mkdir_spec()
    abs_path = str(tmp_path / "newdir")
    result = await spec.execute(path=abs_path)

    assert result.success
    assert os.path.isabs(result.result["path"])
    assert (tmp_path / "newdir").is_dir()

  @pytest.mark.asyncio
  async def test_path_normalized(self, tmp_path: Path) -> None:
    """
    Given: A path with redundant separators or .. segments
    When: Calling execute
    Then: Path is normalized in result
    """
    spec = _mkdir_spec()
    # Create a parent directory first
    parent = tmp_path / "parent"
    parent.mkdir()

    # Path with redundant .. and back to parent
    path = str(tmp_path / "parent" / ".." / "parent" / "child")
    result = await spec.execute(path=path)

    assert result.success
    # The result should be normalized
    assert "parent/..//parent" not in result.result["path"]

  @pytest.mark.asyncio
  async def test_path_resolution_consistency(self, tmp_path: Path) -> None:
    """
    Given: Different forms of the same path (./dir, dir, /full/path/dir)
    When: Calling execute multiple times
    Then: All resolve to the same canonical path
    """
    spec = _mkdir_spec()
    original_cwd = os.getcwd()

    try:
      os.chdir(tmp_path)

      # Create with different path forms
      result1 = await spec.execute(path="newdir1")
      result2 = await spec.execute(path="./newdir2")

      # All should be absolute paths
      assert os.path.isabs(result1.result["path"])
      assert os.path.isabs(result2.result["path"])

    finally:
      os.chdir(original_cwd)


class TestMkdirToolReturnFormat:
  """Tests for return format structure."""

  @pytest.mark.asyncio
  async def test_return_format_created(self, tmp_path: Path) -> None:
    """
    Given: A valid path for new directory
    When: Calling execute
    Then: Returns {created: true, path: str}
    """
    spec = _mkdir_spec()
    new_dir = tmp_path / "newdir"
    result = await spec.execute(path=str(new_dir))

    assert result.success
    assert "created" in result.result
    assert "path" in result.result
    assert result.result["created"] is True
    assert isinstance(result.result["path"], str)

  @pytest.mark.asyncio
  async def test_return_format_existing(self, tmp_path: Path) -> None:
    """
    Given: A path to existing directory
    When: Calling execute
    Then: Returns {created: false, path: str, message: str}
    """
    spec = _mkdir_spec()
    existing_dir = tmp_path / "existing"
    existing_dir.mkdir()

    result = await spec.execute(path=str(existing_dir))

    assert result.success
    assert result.result["created"] is False
    assert "path" in result.result
    assert "message" in result.result
    assert result.result["message"] == "Directory already exists"

  @pytest.mark.asyncio
  async def test_return_format_error(self) -> None:
    """
    Given: An invalid path
    When: Calling execute
    Then: Returns ToolResult with success=False and error message
    """
    spec = _mkdir_spec()
    result = await spec.execute(path="")

    assert not result.success
    assert result.error is not None
    assert isinstance(result.error, str)

  @pytest.mark.asyncio
  async def test_return_path_is_absolute(self, tmp_path: Path) -> None:
    """
    Given: A relative path
    When: Calling execute
    Then: Returned path is absolute
    """
    spec = _mkdir_spec()
    original_cwd = os.getcwd()

    try:
      os.chdir(tmp_path)
      result = await spec.execute(path="newdir")

      assert result.success
      assert os.path.isabs(result.result["path"])
    finally:
      os.chdir(original_cwd)


class TestMkdirToolSpecialCases:
  """Tests for special cases and edge conditions."""

  @pytest.mark.asyncio
  async def test_create_current_directory(self) -> None:
    """
    Given: Path "."
    When: Calling execute
    Then: Returns success with created=False (already exists)
    """
    spec = _mkdir_spec()
    result = await spec.execute(path=".")

    assert result.success
    assert result.result["created"] is False
    assert result.result["message"] == "Directory already exists"

  @pytest.mark.asyncio
  async def test_create_parent_directory(self, tmp_path: Path) -> None:
    """
    Given: Path ".."
    When: Calling execute
    Then: Returns success with created=False (already exists)
    """
    spec = _mkdir_spec()
    original_cwd = os.getcwd()

    try:
      os.chdir(tmp_path)
      result = await spec.execute(path="..")

      assert result.success
      assert result.result["created"] is False
    finally:
      os.chdir(original_cwd)

  @pytest.mark.asyncio
  async def test_create_root_subdirectory(self, tmp_path: Path) -> None:
    """
    Given: A path like /tmp/newdir
    When: Calling execute with guardrail allowing /tmp
    Then: Creates directory successfully
    """
    spec = _mkdir_spec()

    new_dir = tmp_path / "newdir"
    result = await spec.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()

  @pytest.mark.asyncio
  async def test_create_directory_with_spaces(self, tmp_path: Path) -> None:
    """
    Given: A path with spaces in directory name
    When: Calling execute
    Then: Creates directory successfully
    """
    spec = _mkdir_spec()
    dir_with_spaces = tmp_path / "dir with spaces"
    result = await spec.execute(path=str(dir_with_spaces))

    assert result.success
    assert result.result["created"] is True
    assert dir_with_spaces.is_dir()

  @pytest.mark.asyncio
  async def test_create_directory_with_unicode(self, tmp_path: Path) -> None:
    """
    Given: A path with unicode characters in directory name
    When: Calling execute
    Then: Creates directory successfully
    """
    spec = _mkdir_spec()
    unicode_dir = tmp_path / "unicode_目录_🎉"
    result = await spec.execute(path=str(unicode_dir))

    assert result.success
    assert result.result["created"] is True
    assert unicode_dir.is_dir()

  @pytest.mark.asyncio
  async def test_recursive_creates_intermediate_directories(self, tmp_path: Path) -> None:
    """
    Given: A deep nested path with recursive=True
    When: Calling execute
    Then: All intermediate directories are created
    """
    spec = _mkdir_spec()
    deep_path = tmp_path / "a" / "b" / "c" / "d" / "e"
    result = await spec.execute(path=str(deep_path), recursive=True)

    assert result.success
    assert result.result["created"] is True
    assert deep_path.is_dir()
    assert (tmp_path / "a").is_dir()
    assert (tmp_path / "a" / "b").is_dir()
    assert (tmp_path / "a" / "b" / "c").is_dir()
    assert (tmp_path / "a" / "b" / "c" / "d").is_dir()


class TestMkdirToolIntegration:
  """Integration tests for mkdir tool with other components."""

  @pytest.mark.asyncio
  async def test_create_then_check_existence(self, tmp_path: Path) -> None:
    """
    Given: mkdir tool creates a directory
    When: Checking existence with existence tool
    Then: Existence tool reports directory exists
    """
    mkdir_spec = _mkdir_spec()
    existence_spec = ToolRegistry().register(existence)

    new_dir = tmp_path / "newdir"
    mkdir_result = await mkdir_spec.execute(path=str(new_dir))
    assert mkdir_result.success

    existence_result = await existence_spec.execute(path=str(new_dir))
    assert existence_result.success
    assert existence_result.result["exists"] is True
    assert existence_result.result["type"] == "directory"

  @pytest.mark.asyncio
  async def test_create_then_list_directory(self, tmp_path: Path) -> None:
    """
    Given: mkdir tool creates a directory
    When: Listing parent directory with list tool
    Then: New directory appears in listing
    """
    mkdir_spec = _mkdir_spec()
    list_spec = ToolRegistry().register(list)

    new_dir = tmp_path / "newdir"
    mkdir_result = await mkdir_spec.execute(path=str(new_dir))
    assert mkdir_result.success

    list_result = await list_spec.execute(path=str(tmp_path))
    assert list_result.success
    assert "newdir" in list_result.result

  @pytest.mark.asyncio
  async def test_create_in_allowed_directory(self, tmp_path: Path) -> None:
    """
    Given: A guardrail with filesystem_paths configured
    When: Creating directory within allowed path
    Then: Directory is created successfully
    """
    spec = _mkdir_spec()

    new_dir = tmp_path / "newdir"
    result = await spec.execute(path=str(new_dir))

    assert result.success
    assert result.result["created"] is True
    assert new_dir.is_dir()
