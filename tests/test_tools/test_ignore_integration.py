"""Integration tests for gitignore-aware search and list tools."""

from pathlib import Path

import pytest

from yoker.builtin import list as list_tool
from yoker.builtin import search
from yoker.config import Config
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext


def _search_spec():
  registry = ToolRegistry()
  return registry.register(search)


def _search_context(config: Config | None = None) -> ToolContext:
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.search,
    shared=config.tools_shared,
    backends={},
  )


def _list_spec():
  registry = ToolRegistry()
  return registry.register(list_tool)


def _list_context(config: Config | None = None) -> ToolContext:
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.list,
    shared=config.tools_shared,
    backends={},
  )


async def _execute_search(spec, **kwargs):
  import inspect

  sig = inspect.signature(spec.func)
  kwargs["ctx"] = _search_context()
  if "path" not in kwargs:
    kwargs["path"] = "."
  bound = sig.bind(**kwargs)
  bound.apply_defaults()
  return await spec.func(*bound.args, **bound.kwargs)


class TestSearchGitignoreIntegration:
  """Tests that search respects .gitignore patterns."""

  @pytest.mark.asyncio
  async def test_search_excludes_gitignored_directory(self, tmp_path: Path) -> None:
    """Search does not return results from gitignored directories."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.py").write_text("# TODO: fix this\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# TODO: implement\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success is True
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any("session.py" in f for f in files)

  @pytest.mark.asyncio
  async def test_search_excludes_gitignored_file_pattern(self, tmp_path: Path) -> None:
    """Search does not return results from gitignored file patterns."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "data.jsonl").write_text('{"TODO": "fix"}\n')
    (tmp_path / "main.py").write_text("# TODO: implement\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success is True
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any("data.jsonl" in f for f in files)

  @pytest.mark.asyncio
  async def test_search_include_ignored_overrides_gitignore(self, tmp_path: Path) -> None:
    """include_ignored=True returns results from gitignored files."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "data.jsonl").write_text('{"TODO": "fix"}\n')
    (tmp_path / "main.py").write_text("# TODO: implement\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", include_ignored=True)
    assert result.success is True
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert any("data.jsonl" in f for f in files)

  @pytest.mark.asyncio
  async def test_search_still_skips_dotfiles(self, tmp_path: Path) -> None:
    """Search still skips dotfiles by default."""
    (tmp_path / ".hidden").write_text("# TODO: secret\n")
    (tmp_path / "main.py").write_text("# TODO: visible\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success is True
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any(".hidden" in f for f in files)

  @pytest.mark.asyncio
  async def test_search_filename_excludes_gitignored(self, tmp_path: Path) -> None:
    """Filename search also respects .gitignore."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "helper.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "helper.py").write_text("x")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="*.py", type="filename")
    assert result.success is True
    files = [m["file"] for m in result.result["matches"]]
    assert any("src/helper.py" in f for f in files)
    assert not any("context/helper.py" in f for f in files)


class TestListGitignoreIntegration:
  """Tests that list respects .gitignore patterns."""

  @pytest.mark.asyncio
  async def test_list_excludes_gitignored_directory(self, tmp_path: Path) -> None:
    """List does not show gitignored directories."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.jsonl").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    assert "src/" in result.result
    assert "context/" not in result.result

  @pytest.mark.asyncio
  async def test_list_excludes_dotfiles(self, tmp_path: Path) -> None:
    """List skips dotfiles and dot-directories."""
    (tmp_path / ".hidden").write_text("x")
    (tmp_path / ".secret_dir").mkdir()
    (tmp_path / "visible.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    assert "visible.py" in result.result
    assert ".hidden" not in result.result
    assert ".secret_dir" not in result.result

  @pytest.mark.asyncio
  async def test_list_excludes_skip_dirs(self, tmp_path: Path) -> None:
    """List skips hardcoded skip_dirs like __pycache__."""
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "module.pyc").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    assert "src/" in result.result
    assert "__pycache__/" not in result.result

  @pytest.mark.asyncio
  async def test_list_include_ignored_shows_gitignored(self, tmp_path: Path) -> None:
    """include_ignored=True shows gitignored entries."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.jsonl").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3, include_ignored=True)
    assert result.success is True
    assert "src/" in result.result
    assert "context/" in result.result

  @pytest.mark.asyncio
  async def test_list_excludes_gitignored_files(self, tmp_path: Path) -> None:
    """List also excludes gitignored files (not just directories)."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "session.jsonl").write_text("x")
    (tmp_path / "main.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    assert "main.py" in result.result
    assert "session.jsonl" not in result.result
