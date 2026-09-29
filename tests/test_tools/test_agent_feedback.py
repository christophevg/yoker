"""Regression tests for agent-feedback triage (2026-09-16, feedback.md).

Covers the changes accepted from the agent-friction report:

- T2: ``update``/``write`` distinguish a true no-op (``old_string ==
  new_string``) from "applied but content identical" — the old single
  "(no content change)" suffix read as "done" and cost blind patch
  cycles.
- T5: content search skips binary junk (cache dirs, binary extensions)
  even with ``include_ignored=True``, with an explicit
  ``include_binaries=True`` opt-in.
"""

from pathlib import Path

import pytest

from yoker.builtin import search, update, write
from yoker.config import Config, ToolsConfig, UpdateToolConfig, WriteToolConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext


def _update_context() -> ToolContext:
  config = Config(
    tools=ToolsConfig(
      update=UpdateToolConfig(),
      write=WriteToolConfig(allow_overwrite=True),
    )
  )
  return ToolContext(
    config=config.tools.update,
    shared=config.tools_shared,
    backends={},
  )


def _write_context() -> ToolContext:
  config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
  return ToolContext(
    config=config.tools.write,
    shared=config.tools_shared,
    backends={},
  )


def _search_spec():
  registry = ToolRegistry()
  return registry.register(search)


def _search_context() -> ToolContext:
  config = Config()
  return ToolContext(
    config=config.tools.search,
    shared=config.tools_shared,
    backends={},
  )


class TestUpdateNoOpDistinction:
  """T2: update distinguishes no-op from applied-but-identical."""

  @pytest.mark.asyncio
  async def test_replace_old_equals_new_is_no_op(self, tmp_path: Path) -> None:
    """old_string == new_string reports the no-op message, not 'updated'."""
    file = tmp_path / "f.txt"
    file.write_text("alpha\nbeta\n")
    result = await update(
      str(file),
      _update_context(),
      operation="replace",
      old_string="beta",
      new_string="beta",
    )
    assert result.success
    assert result.result.startswith("No-op: old_string equals new_string")
    assert "your diagnosis may be wrong" in result.result

  @pytest.mark.asyncio
  async def test_append_empty_new_string_is_applied_identical(self, tmp_path: Path) -> None:
    """append('') normalizes EOF but content may stay identical."""
    file = tmp_path / "f.txt"
    file.write_text("x\n")
    result = await update(str(file), _update_context(), operation="append", new_string="")
    assert result.success
    assert result.result.startswith("Applied, but file content is identical")

  @pytest.mark.asyncio
  async def test_apply_identical_message_via_line_range(self, tmp_path: Path) -> None:
    """A line_range replace with the same text is 'applied but identical'."""
    file = tmp_path / "f.txt"
    file.write_text("a\nb\nc\n")
    result = await update(
      str(file),
      _update_context(),
      operation="replace",
      line_range=[2, 2],
      new_string="b",
    )
    assert result.success
    assert result.result.startswith("Applied, but file content is identical")

  @pytest.mark.asyncio
  async def test_inference_note_appended_to_noop(self, tmp_path: Path) -> None:
    """The operation-inferred advice is preserved on the no-op path."""
    file = tmp_path / "f.txt"
    file.write_text("alpha\nbeta\n")
    result = await update(
      str(file),
      _update_context(),
      old_string="beta",
      new_string="beta",
    )
    assert result.success
    assert result.result.startswith("No-op: old_string equals new_string")
    assert "(operation inferred: 'replace')" in result.result

  @pytest.mark.asyncio
  async def test_real_change_still_reports_updated(self, tmp_path: Path) -> None:
    """A genuine change keeps the existing success message."""
    file = tmp_path / "f.txt"
    file.write_text("alpha\nbeta\n")
    result = await update(
      str(file),
      _update_context(),
      operation="replace",
      old_string="beta",
      new_string="BETA",
    )
    assert result.success
    assert result.result.startswith("File updated successfully (+1 −1)")

  @pytest.mark.asyncio
  async def test_eof_newline_addition_is_not_identical(self, tmp_path: Path) -> None:
    """A file that gains a trailing newline takes the normal diff path."""
    file = tmp_path / "f.txt"
    file.write_text("a\nno-final-newline")
    result = await update(
      str(file),
      _update_context(),
      operation="replace",
      old_string="no-final-newline",
      new_string="no-final-newline",
    )
    assert result.success
    # The EOF-touching replace adds a terminal newline: content changed.
    assert not result.result.startswith("No-op:")
    assert "File updated successfully" in result.result

  @pytest.mark.asyncio
  async def test_delete_to_same_content_says_applied_identical(self, tmp_path: Path) -> None:
    """Deleting text that only differs by trailing whitespace-normalization."""
    file = tmp_path / "f.txt"
    file.write_text("keep\n")
    result = await update(
      str(file),
      _update_context(),
      operation="delete",
      line_number=1,
    )
    # Deleting the only line empties the file — content DID change.
    assert result.success
    assert not result.result.startswith("Applied")


class TestWriteIdenticalMessage:
  """T2: write reports applied-but-identical instead of 'no content change'."""

  @pytest.mark.asyncio
  async def test_overwrite_identical_content_message(self, tmp_path: Path) -> None:
    file = tmp_path / "same.txt"
    file.write_text("same\n")
    result = await write(str(file), "same\n", _write_context())
    assert result.success
    assert "applied, but file content is identical" in result.result

  @pytest.mark.asyncio
  async def test_overwrite_real_change_keeps_diff(self, tmp_path: Path) -> None:
    file = tmp_path / "over.txt"
    file.write_text("old1\nold2\n")
    result = await write(str(file), "old1\nnew2\n", _write_context())
    assert result.success
    assert "(+1 −1)" in result.result


class TestSearchBinaryFloor:
  """T5: content search skips binary junk even with include_ignored=True."""

  @pytest.mark.asyncio
  async def test_mypy_cache_db_skipped_by_default(self, tmp_path: Path) -> None:
    """.mypy_cache .db files are excluded by default (no include_ignored)."""
    cache = tmp_path / ".mypy_cache" / "7"
    cache.mkdir(parents=True)
    (cache / "some.db").write_bytes(b"TODO\xff\x00junk\x01")
    (tmp_path / "main.py").write_text("# TODO: real\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any("some.db" in f for f in files)

  @pytest.mark.asyncio
  async def test_mypy_cache_db_skipped_even_with_include_ignored(self, tmp_path: Path) -> None:
    """The reported defect: include_ignored=True dragged in .db junk."""
    cache = tmp_path / ".mypy_cache" / "7"
    cache.mkdir(parents=True)
    (cache / "some.db").write_bytes(b"TODO\xff\x00junk\x01")
    (tmp_path / "main.py").write_text("# TODO: real\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", include_ignored=True)
    assert result.success
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any("some.db" in f for f in files)

  @pytest.mark.asyncio
  async def test_venv_skipped_even_with_include_ignored(self, tmp_path: Path) -> None:
    """.venv binaries stay excluded under include_ignored=True."""
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "libsqlite.so").write_bytes(b"TODO\x7fELFjunk")
    (tmp_path / "main.py").write_text("# TODO: real\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", include_ignored=True)
    assert result.success
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any("libsqlite" in f for f in files)

  @pytest.mark.asyncio
  async def test_include_binaries_opt_in(self, tmp_path: Path) -> None:
    """include_binaries=True searches the binary junk paths again."""
    cache = tmp_path / ".mypy_cache" / "7"
    cache.mkdir(parents=True)
    (cache / "some.db").write_text("TODO marker in cache\n")
    (tmp_path / "main.py").write_text("# TODO: real\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="TODO",
      include_ignored=True,
      include_binaries=True,
    )
    assert result.success
    files = [m["file"] for m in result.result["matches"]]
    assert any("some.db" in f for f in files)

  @pytest.mark.asyncio
  async def test_binary_extension_in_project_dir(self, tmp_path: Path) -> None:
    """Binary extensions are skipped even in a normal project directory."""
    (tmp_path / "module.pyc").write_bytes(b"TODO\x00\x01binary")
    (tmp_path / "image.png").write_bytes(b"TODO\x89PNGjunk")
    (tmp_path / "main.py").write_text("# TODO: real\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", include_ignored=True)
    assert result.success
    files = [m["file"] for m in result.result["matches"]]
    assert any("main.py" in f for f in files)
    assert not any(".pyc" in f for f in files)
    assert not any(".png" in f for f in files)

  @pytest.mark.asyncio
  async def test_filename_search_unaffected(self, tmp_path: Path) -> None:
    """Filename search is not touched by the binary floor."""
    cache = tmp_path / ".mypy_cache"
    cache.mkdir()
    (cache / "some.db").write_bytes(b"\x00\x01")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="*.db",
      type="filename",
      include_ignored=True,
    )
    assert result.success
    names = [m["file"] for m in result.result["matches"]]
    assert any("some.db" in n for n in names)

  @pytest.mark.asyncio
  async def test_single_file_target_not_filtered(self, tmp_path: Path) -> None:
    """Explicitly targeting a binary file still searches it."""
    db = tmp_path / "explicit.db"
    db.write_bytes(b"TODO marker")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(db), ctx=ctx, pattern="TODO")
    assert result.success
    assert result.result["total_matches"] == 1

  @pytest.mark.asyncio
  async def test_binary_skips_counted_for_visibility(self, tmp_path: Path) -> None:
    """Suppressed binaries are counted so a zero-result is explainable."""
    cache = tmp_path / ".mypy_cache"
    cache.mkdir()
    (cache / "some.db").write_bytes(b"TODO")
    (tmp_path / "main.py").write_text("# no match here\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success
    assert result.result["total_matches"] == 0
    assert result.result.get("hidden_by_ignore", 0) >= 1

  @pytest.mark.asyncio
  async def test_floor_only_suppression_names_include_binaries_hint(self, tmp_path: Path) -> None:
    """Floor-only suppression: hint names include_binaries, not include_ignored."""
    cache = tmp_path / ".mypy_cache"
    cache.mkdir()
    (cache / "some.db").write_text("TODO marker\n")
    (tmp_path / "main.py").write_text("# no match here\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", include_ignored=True)
    assert result.success
    assert result.result["total_matches"] == 0
    assert result.result.get("hidden_by_ignore", 0) >= 1
    assert "include_binaries=true" in result.result["hint"]
    assert "include_ignored=true" not in result.result["hint"]

  @pytest.mark.asyncio
  async def test_mixed_suppression_hint_names_both_remedies(self, tmp_path: Path) -> None:
    """Both counters active: hint names both remedies.

    Note: floor DIRS (dotfile caches) are also matcher-suppressed under
    default config, so they count as ignore suppressions — the floor
    counter is exercised by binary extensions in normal dirs.
    """
    (tmp_path / ".gitignore").write_text("context/\n")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "session.py").write_text("# TODO: fix this\n")
    (tmp_path / "module.pyc").write_bytes(b"TODO\x00binary")
    (tmp_path / "main.py").write_text("# no match here\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO")
    assert result.success
    assert result.result["total_matches"] == 0
    assert result.result.get("hidden_by_ignore", 0) >= 2
    assert "include_ignored=true" in result.result["hint"]
    assert "include_binaries=true" in result.result["hint"]
