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


class TestHiddenVisibilityReporting:
  """#61: silent suppression of ignored entries reads as absence.

  "0 entries"/"no matches" output must be distinguishable from "results
  exist but are hidden by ignore rules". The tools report how many entries
  were suppressed and hint at include_ignored=true.
  """

  @pytest.mark.asyncio
  async def test_list_reports_hidden_count_when_entries_hidden(self, tmp_path: Path) -> None:
    """list appends the hidden count when ignore rules suppress entries."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.jsonl").write_text("x")
    (tmp_path / "context" / "other.jsonl").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    assert "hidden by ignore rules" in result.result
    assert "include_ignored=true" in result.result
    # Two gitignored files under context/ (dir + its walk) — at least 1.
    assert result.result.count("entries hidden") >= 1
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["hidden_entries"] >= 1

  @pytest.mark.asyncio
  async def test_list_all_hidden_reports_zero_visible_with_count(self, tmp_path: Path) -> None:
    """When everything is ignored, output shows 0 visible + hidden count."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.jsonl").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    assert "0 entries total" in result.result
    assert "hidden by ignore rules" in result.result

  @pytest.mark.asyncio
  async def test_list_no_hidden_line_when_nothing_suppressed(self, tmp_path: Path) -> None:
    """No hidden-count line when nothing is suppressed."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    spec = _list_spec()
    ctx = _list_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, max_depth=3)
    assert result.success is True
    # The tmp_path may contain 'hidden' (test id); assert on the summary lines.
    assert "entries hidden by ignore rules" not in result.result
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["hidden_entries"] == 0

  @pytest.mark.asyncio
  async def test_search_content_reports_hidden_with_zero_matches(self, tmp_path: Path) -> None:
    """Content search with only-ignored hits reports hidden + hint."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.py").write_text("# TODO: fix this\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# nothing here\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success is True
    assert result.result["total_matches"] == 0
    assert result.result["hidden_by_ignore"] >= 1
    assert "include_ignored=true" in result.result["hint"]

  @pytest.mark.asyncio
  async def test_search_filename_reports_hidden_with_zero_matches(self, tmp_path: Path) -> None:
    """Filename search with only-ignored hits reports hidden + hint."""
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "helper.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="helper.py", type="filename")
    assert result.success is True
    assert result.result["total_matches"] == 0
    assert result.result["hidden_by_ignore"] >= 1
    assert "include_ignored=true" in result.result["hint"]

  @pytest.mark.asyncio
  async def test_search_reports_hidden_alongside_matches(self, tmp_path: Path) -> None:
    """hidden_by_ignore is reported even when matches exist (no hint then)."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "data.jsonl").write_text('{"TODO": "fix"}\n')
    (tmp_path / "main.py").write_text("# TODO: implement\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success is True
    assert result.result["total_matches"] >= 1
    assert result.result["hidden_by_ignore"] >= 1
    assert "hint" not in result.result

  @pytest.mark.asyncio
  async def test_search_no_hidden_field_when_nothing_suppressed(self, tmp_path: Path) -> None:
    """No hidden_by_ignore key when nothing is suppressed."""
    (tmp_path / "main.py").write_text("# TODO: implement\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success is True
    assert result.result["total_matches"] >= 1
    assert "hidden_by_ignore" not in result.result

  @pytest.mark.asyncio
  async def test_search_include_ignored_no_hidden_field(self, tmp_path: Path) -> None:
    """include_ignored=True suppresses nothing, so no hidden field."""
    (tmp_path / ".gitignore").write_text("*.jsonl\n")
    (tmp_path / "data.jsonl").write_text('{"TODO": "fix"}\n')
    (tmp_path / "main.py").write_text("# TODO: implement\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", include_ignored=True)
    assert result.success is True
    assert result.result["total_matches"] >= 2
    assert "hidden_by_ignore" not in result.result
