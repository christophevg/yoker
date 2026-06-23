"""Tests for write tool."""

import platform
from pathlib import Path

import pytest

from yoker.builtin import write as write_tool
from yoker.config import Config, PermissionsConfig, ToolsConfig, WriteToolConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import PathGuardrail
from yoker.tools.schema import ToolResult


def _write_spec():
  """Create and register the write tool."""
  registry = ToolRegistry()
  return registry.register(write_tool)


def _write_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for write tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.write,
    shared=config.tools_shared,
    backends={},
  )


class TestWriteTool:
  """Tests for the write tool."""

  def test_name(self) -> None:
    """write tool has correct name."""
    spec = _write_spec()
    assert spec.name == "write"

  def test_description(self) -> None:
    """write tool has description."""
    spec = _write_spec()
    assert "Write" in spec.description

  def test_schema(self) -> None:
    """write tool schema has required fields."""
    spec = _write_spec()
    schema = spec.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "write"
    assert "parameters" in func
    props = func["parameters"]["properties"]
    assert "path" in props
    assert "content" in props
    assert "create_parents" in props
    assert "path" in func["parameters"]["required"]
    assert "content" in func["parameters"]["required"]

  @pytest.mark.asyncio
  async def test_write_new_file(self, tmp_path: Path) -> None:
    """write tool writes content to a new file."""
    file_path = tmp_path / "test.txt"
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=str(file_path), content="hello world", ctx=ctx)
    assert result.success is True
    assert result.result == "File written successfully"
    assert result.error is None
    assert file_path.read_text(encoding="utf-8") == "hello world"

  @pytest.mark.asyncio
  async def test_write_overwrite_blocked(self, tmp_path: Path) -> None:
    """write tool blocks overwrite when allow_overwrite=False."""
    file_path = tmp_path / "existing.txt"
    file_path.write_text("old content")
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=False)))
    spec = _write_spec()
    ctx = _write_context(config)
    result = await spec.execute(path=str(file_path), content="new content", ctx=ctx)
    assert result.success is False
    assert "overwrite" in result.error.lower()
    assert file_path.read_text(encoding="utf-8") == "old content"

  @pytest.mark.asyncio
  async def test_write_overwrite_allowed(self, tmp_path: Path) -> None:
    """write tool allows overwrite when allow_overwrite=True."""
    file_path = tmp_path / "existing.txt"
    file_path.write_text("old content")
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    spec = _write_spec()
    ctx = _write_context(config)
    result = await spec.execute(path=str(file_path), content="new content", ctx=ctx)
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "new content"

  @pytest.mark.asyncio
  async def test_write_with_guardrail_blocks(self, tmp_path: Path) -> None:
    """Path guardrail blocks paths outside allowed directories for write."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _write_spec()
    validation = guardrail.validate(spec.name, {"path": "/etc/passwd", "content": "data"})
    assert not validation.valid
    assert "outside allowed" in (validation.reason or "").lower()

  @pytest.mark.asyncio
  async def test_write_with_guardrail_allows(self, tmp_path: Path) -> None:
    """Path guardrail allows paths inside allowed directories for write."""
    file_path = tmp_path / "test.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _write_spec()
    ctx = _write_context()
    validation = guardrail.validate(
      spec.name, {"path": str(file_path), "content": "allowed content"}
    )
    assert validation.valid
    result = await spec.execute(path=str(file_path), content="allowed content", ctx=ctx)
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "allowed content"

  @pytest.mark.asyncio
  async def test_write_rejects_symlink(self, tmp_path: Path) -> None:
    """write tool rejects writing to symlinks."""
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=str(link), content="new data", ctx=ctx)
    assert result.success is False
    assert "symlink" in result.error.lower()

  @pytest.mark.asyncio
  async def test_write_create_parents_false(self, tmp_path: Path) -> None:
    """write tool returns error when parent missing and create_parents=False."""
    file_path = tmp_path / "missing" / "test.txt"
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=str(file_path), content="data", create_parents=False, ctx=ctx)
    assert result.success is False
    assert "parent directory" in result.error.lower()

  @pytest.mark.asyncio
  async def test_write_create_parents_true(self, tmp_path: Path) -> None:
    """write tool creates parents when create_parents=True."""
    file_path = tmp_path / "missing" / "test.txt"
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=str(file_path), content="data", create_parents=True, ctx=ctx)
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "data"

  @pytest.mark.asyncio
  async def test_write_missing_path(self) -> None:
    """write tool handles missing path parameter."""
    spec = _write_spec()
    ctx = _write_context()
    # Missing path parameter is caught at the schema binding level
    result = await spec.execute(path="", content="data", ctx=ctx)
    assert result.success is False
    assert "invalid path" in result.error.lower() or "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_write_empty_content(self, tmp_path: Path) -> None:
    """write tool writes empty file when content is empty string."""
    file_path = tmp_path / "empty_file.txt"
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=str(file_path), content="", ctx=ctx)
    assert result.success is True
    assert result.result == "File written successfully"
    assert file_path.read_text(encoding="utf-8") == ""

  @pytest.mark.asyncio
  async def test_write_non_string_path(self) -> None:
    """write tool handles non-string path parameter."""
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=123, content="data", ctx=ctx)  # type: ignore
    assert result.success is False
    assert result.error == "Invalid path parameter"

  @pytest.mark.asyncio
  async def test_write_non_string_content(self) -> None:
    """write tool handles non-string content parameter."""
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path="/tmp/test.txt", content=123, ctx=ctx)  # type: ignore
    assert result.success is False
    assert result.error == "Invalid content parameter"

  @pytest.mark.asyncio
  async def test_write_permission_denied(self, tmp_path: Path, monkeypatch) -> None:
    """write tool returns sanitized error on permission denied."""
    file_path = tmp_path / "readonly.txt"
    file_path.write_text("existing")

    def mock_write_text(*args, **kwargs):
      raise PermissionError("Access denied")

    monkeypatch.setattr(Path, "write_text", mock_write_text)
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    spec = _write_spec()
    ctx = _write_context(config)
    result = await spec.execute(path=str(file_path), content="new data", ctx=ctx)
    assert result.success is False
    assert "permission denied" in result.error.lower()
    assert str(file_path) not in result.error

  @pytest.mark.asyncio
  async def test_write_sanitizes_error_messages(self, tmp_path: Path) -> None:
    """write tool does not leak full paths in error messages."""
    spec = _write_spec()
    ctx = _write_context()
    sensitive_path = str(tmp_path / ".ssh" / "id_rsa")
    result = await spec.execute(path=sensitive_path, content="secret", ctx=ctx)
    assert result.success is False
    assert sensitive_path not in result.error

  @pytest.mark.asyncio
  async def test_write_resolves_path(self, tmp_path: Path) -> None:
    """write tool resolves relative paths before writing."""
    file_path = tmp_path / "real.txt"
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(
      path=str(tmp_path / ".." / tmp_path.name / "real.txt"),
      content="resolved",
      ctx=ctx,
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "resolved"

  @pytest.mark.asyncio
  async def test_write_oserror_during_write(self, tmp_path: Path, monkeypatch) -> None:
    """write tool handles OSError during write_text gracefully."""
    file_path = tmp_path / "device.txt"
    file_path.write_text("data")

    def mock_write_text(*args, **kwargs):
      raise OSError("device error")

    monkeypatch.setattr(Path, "write_text", mock_write_text)
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    spec = _write_spec()
    ctx = _write_context(config)
    result = await spec.execute(path=str(file_path), content="new data", ctx=ctx)
    assert result.success is False
    assert "error writing file" in result.error.lower()
    assert str(file_path) not in result.error

  @pytest.mark.asyncio
  async def test_write_empty_path(self) -> None:
    """write tool handles empty path string."""
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path="", content="data", ctx=ctx)
    assert result.success is False
    assert "invalid path" in result.error.lower()

  @pytest.mark.asyncio
  async def test_write_result_is_toolresult(self) -> None:
    """write tool execute returns ToolResult."""
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path="/dev/null", content="test", ctx=ctx)
    assert isinstance(result, ToolResult)

  @pytest.mark.asyncio
  async def test_write_guardrail_passes_create_parents(self, tmp_path: Path) -> None:
    """Path guardrail validates write parameters including create_parents."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _write_spec()
    ctx = _write_context()
    validation = guardrail.validate(
      spec.name,
      {
        "path": str(tmp_path / "test.txt"),
        "content": "data",
        "create_parents": True,
      },
    )
    assert validation.valid
    result = await spec.execute(
      path=str(tmp_path / "test.txt"),
      content="data",
      create_parents=True,
      ctx=ctx,
    )
    assert result.success is True

  @pytest.mark.asyncio
  async def test_write_symlink_inside_allowed_with_guardrail(self, tmp_path: Path) -> None:
    """write tool rejects symlinks regardless of guardrail."""
    target = tmp_path / "target.txt"
    target.write_text("allowed target")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    spec = _write_spec()
    ctx = _write_context()
    result = await spec.execute(path=str(link), content="new data", ctx=ctx)
    # Tool layer rejects symlinks before writing
    assert result.success is False
    assert "symlink" in result.error.lower()

  @pytest.mark.skipif(
    platform.system() == "Windows", reason="Unix permission model differs on Windows"
  )
  @pytest.mark.asyncio
  async def test_write_over_existing_directory(self, tmp_path: Path) -> None:
    """write tool returns error when path is an existing directory."""
    subdir = tmp_path / "existing_dir"
    subdir.mkdir()
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    spec = _write_spec()
    ctx = _write_context(config)
    result = await spec.execute(path=str(subdir), content="data", ctx=ctx)
    assert result.success is False
    assert "error writing file" in result.error.lower()
