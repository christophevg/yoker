"""Tests for the file tool implementation."""

from pathlib import Path

import pytest

from yoker.builtin import file
from yoker.config import Config, PermissionsConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import WritePathGuardrail


def _file_spec():
  """Create and register the file tool."""
  registry = ToolRegistry()
  return registry.register(file)


def _file_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for file tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.file,
    shared=config.tools_shared,
    backends={},
  )


class TestFileToolSchema:
  """Tests for file tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    spec = _file_spec()
    assert spec.name == "file"

  def test_description(self) -> None:
    """Test tool description."""
    spec = _file_spec()
    assert "filesystem" in spec.description.lower() or "file" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema has required parameters."""
    spec = _file_spec()
    schema = spec.schema
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "file"
    props = schema["function"]["parameters"]["properties"]
    assert "operation" in props
    assert "source" in props
    assert "destination" in props
    assert "recursive" in props
    required = schema["function"]["parameters"]["required"]
    assert "operation" in required
    assert "source" in required


class TestFileCopy:
  """Tests for the copy operation."""

  @pytest.mark.asyncio
  async def test_copy_file(self, tmp_path: Path) -> None:
    """Test copying a file."""
    source = tmp_path / "source.txt"
    source.write_text("hello world")
    dest = tmp_path / "dest.txt"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="copy", source=str(source), destination=str(dest), ctx=ctx
    )

    assert result.success
    assert result.result["operation"] == "copy"
    assert result.result["type"] == "file"
    assert dest.exists()
    assert dest.read_text() == "hello world"

  @pytest.mark.asyncio
  async def test_copy_file_preserves_permissions(self, tmp_path: Path) -> None:
    """Test that copy2 preserves file metadata."""
    source = tmp_path / "source.py"
    source.write_text("print('hello')")
    source.chmod(0o755)
    dest = tmp_path / "dest.py"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="copy", source=str(source), destination=str(dest), ctx=ctx
    )

    assert result.success
    assert dest.exists()
    assert dest.stat().st_mode == source.stat().st_mode

  @pytest.mark.asyncio
  async def test_copy_directory_recursive(self, tmp_path: Path) -> None:
    """Test copying a directory recursively."""
    source = tmp_path / "source_dir"
    source.mkdir()
    (source / "file1.txt").write_text("content1")
    (source / "subdir").mkdir()
    (source / "subdir" / "file2.txt").write_text("content2")
    dest = tmp_path / "dest_dir"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="copy",
      source=str(source),
      destination=str(dest),
      recursive=True,
      ctx=ctx,
    )

    assert result.success
    assert result.result["type"] == "directory"
    assert (dest / "file1.txt").exists()
    assert (dest / "subdir" / "file2.txt").exists()
    assert (dest / "subdir" / "file2.txt").read_text() == "content2"

  @pytest.mark.asyncio
  async def test_copy_directory_without_recursive_fails(self, tmp_path: Path) -> None:
    """Test copying a directory without recursive flag fails."""
    source = tmp_path / "source_dir"
    source.mkdir()
    (source / "file.txt").write_text("content")
    dest = tmp_path / "dest_dir"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="copy", source=str(source), destination=str(dest), ctx=ctx
    )

    assert not result.success
    assert "recursive" in result.error.lower()

  @pytest.mark.asyncio
  async def test_copy_to_existing_destination_fails(self, tmp_path: Path) -> None:
    """Test copying to an existing destination fails."""
    source = tmp_path / "source.txt"
    source.write_text("source content")
    dest = tmp_path / "dest.txt"
    dest.write_text("existing content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="copy", source=str(source), destination=str(dest), ctx=ctx
    )

    assert not result.success
    assert "already exists" in result.error.lower()

  @pytest.mark.asyncio
  async def test_copy_creates_parent_dirs(self, tmp_path: Path) -> None:
    """Test that copy creates parent directories for destination."""
    source = tmp_path / "source.txt"
    source.write_text("content")
    dest = tmp_path / "subdir" / "deeper" / "dest.txt"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="copy", source=str(source), destination=str(dest), ctx=ctx
    )

    assert result.success
    assert dest.exists()
    assert dest.read_text() == "content"


class TestFileMove:
  """Tests for the move operation."""

  @pytest.mark.asyncio
  async def test_move_file(self, tmp_path: Path) -> None:
    """Test moving a file."""
    source = tmp_path / "source.txt"
    source.write_text("hello world")
    dest = tmp_path / "dest.txt"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="move", source=str(source), destination=str(dest), ctx=ctx
    )

    assert result.success
    assert result.result["operation"] == "move"
    assert not source.exists()
    assert dest.exists()
    assert dest.read_text() == "hello world"

  @pytest.mark.asyncio
  async def test_move_directory(self, tmp_path: Path) -> None:
    """Test moving a directory."""
    source = tmp_path / "source_dir"
    source.mkdir()
    (source / "file.txt").write_text("content")
    dest = tmp_path / "dest_dir"

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="move", source=str(source), destination=str(dest), ctx=ctx
    )

    assert result.success
    assert result.result["type"] == "directory"
    assert not source.exists()
    assert (dest / "file.txt").exists()

  @pytest.mark.asyncio
  async def test_move_to_existing_destination_fails(self, tmp_path: Path) -> None:
    """Test moving to an existing destination fails."""
    source = tmp_path / "source.txt"
    source.write_text("source content")
    dest = tmp_path / "dest.txt"
    dest.write_text("existing content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="move", source=str(source), destination=str(dest), ctx=ctx
    )

    assert not result.success
    assert "already exists" in result.error.lower()

  @pytest.mark.asyncio
  async def test_move_same_source_dest_fails(self, tmp_path: Path) -> None:
    """Test moving to the same path fails."""
    source = tmp_path / "file.txt"
    source.write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="move", source=str(source), destination=str(source), ctx=ctx
    )

    assert not result.success
    assert "same path" in result.error.lower()


class TestFileDelete:
  """Tests for the delete operation."""

  @pytest.mark.asyncio
  async def test_delete_file(self, tmp_path: Path) -> None:
    """Test deleting a file."""
    target = tmp_path / "file.txt"
    target.write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="delete", source=str(target), ctx=ctx)

    assert result.success
    assert result.result["operation"] == "delete"
    assert result.result["type"] == "file"
    assert not target.exists()

  @pytest.mark.asyncio
  async def test_delete_directory_without_recursive_fails(self, tmp_path: Path) -> None:
    """Test deleting a directory without recursive flag fails."""
    target = tmp_path / "dir"
    target.mkdir()
    (target / "file.txt").write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="delete", source=str(target), ctx=ctx)

    assert not result.success
    assert "recursive" in result.error.lower()
    assert target.exists()  # not deleted

  @pytest.mark.asyncio
  async def test_delete_directory_recursive(self, tmp_path: Path) -> None:
    """Test deleting a directory recursively."""
    target = tmp_path / "dir"
    target.mkdir()
    (target / "file.txt").write_text("content")
    (target / "subdir").mkdir()
    (target / "subdir" / "nested.txt").write_text("nested")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="delete", source=str(target), recursive=True, ctx=ctx)

    assert result.success
    assert result.result["type"] == "directory"
    assert not target.exists()

  @pytest.mark.asyncio
  async def test_delete_git_directory_refused(self, tmp_path: Path) -> None:
    """Test that deleting .git directory is refused."""
    target = tmp_path / ".git"
    target.mkdir()
    (target / "config").write_text("[core]")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="delete", source=str(target), recursive=True, ctx=ctx)

    assert not result.success
    assert "refusing" in result.error.lower() or "vcs" in result.error.lower()
    assert target.exists()  # not deleted


class TestFileValidation:
  """Tests for input validation and error handling."""

  @pytest.mark.asyncio
  async def test_invalid_operation(self, tmp_path: Path) -> None:
    """Test invalid operation is rejected."""
    source = tmp_path / "file.txt"
    source.write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="chmod", source=str(source), ctx=ctx)

    assert not result.success
    assert "unknown operation" in result.error.lower()

  @pytest.mark.asyncio
  async def test_missing_operation(self, tmp_path: Path) -> None:
    """Test missing operation is rejected."""
    source = tmp_path / "file.txt"
    source.write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="", source=str(source), ctx=ctx)

    assert not result.success
    assert "operation" in result.error.lower()

  @pytest.mark.asyncio
  async def test_nonexistent_source(self, tmp_path: Path) -> None:
    """Test non-existent source fails."""
    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(
      operation="delete", source=str(tmp_path / "nonexistent.txt"), ctx=ctx
    )

    assert not result.success
    assert "does not exist" in result.error.lower()

  @pytest.mark.asyncio
  async def test_copy_missing_destination(self, tmp_path: Path) -> None:
    """Test copy without destination fails."""
    source = tmp_path / "source.txt"
    source.write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="copy", source=str(source), ctx=ctx)

    assert not result.success
    assert "destination" in result.error.lower()

  @pytest.mark.asyncio
  async def test_move_missing_destination(self, tmp_path: Path) -> None:
    """Test move without destination fails."""
    source = tmp_path / "source.txt"
    source.write_text("content")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="move", source=str(source), ctx=ctx)

    assert not result.success
    assert "destination" in result.error.lower()

  @pytest.mark.asyncio
  async def test_empty_source(self) -> None:
    """Test empty source fails."""
    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="delete", source="", ctx=ctx)

    assert not result.success
    assert "empty" in result.error.lower()

  @pytest.mark.asyncio
  async def test_symlink_source_rejected(self, tmp_path: Path) -> None:
    """Test symlink source is rejected."""
    target = tmp_path / "real.txt"
    target.write_text("content")
    link = tmp_path / "link.txt"
    try:
      link.symlink_to(target)
    except OSError:
      pytest.skip("Symlinks not supported")

    spec = _file_spec()
    ctx = _file_context()
    result = await spec.execute(operation="delete", source=str(link), ctx=ctx)

    assert not result.success
    assert "symlink" in result.error.lower()


class TestFileGuardrailIntegration:
  """Tests for guardrail integration."""

  @pytest.mark.asyncio
  async def test_guardrail_blocks_outside_paths(self, tmp_path: Path) -> None:
    """Test that paths outside allowed roots are blocked."""
    source = tmp_path / "file.txt"
    source.write_text("content")
    outside = tmp_path / "outside"
    outside.mkdir()

    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(outside),)))
    guardrail = WritePathGuardrail(config)

    spec = _file_spec()
    validation = guardrail.validate(spec.name, {"path": str(source)})
    assert not validation.valid

  @pytest.mark.asyncio
  async def test_guardrail_protects_makefile(self, tmp_path: Path) -> None:
    """Test that write-blocked files are guarded."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")

    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)

    spec = _file_spec()
    validation = guardrail.validate(spec.name, str(makefile))
    assert not validation.valid
    assert "write-protected" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_guardrail_allows_normal_files(self, tmp_path: Path) -> None:
    """Test that normal files pass guardrail."""
    source = tmp_path / "file.txt"
    source.write_text("content")

    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)

    spec = _file_spec()
    validation = guardrail.validate(spec.name, str(source))
    assert validation.valid
