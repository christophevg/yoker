"""Tilde expansion for path-guarded tool arguments.

Bug: none of the filesystem tools expand ``~`` — ``Path("~/x")`` is a
literal relative path, so ``search(path="~/...")`` failed with
"Path not found" and ``existence`` silently returned ``exists: False``
for a real file. The fix expands a leading ``~`` in PATH_READ/PATH_WRITE
arguments in ``_run_tool``, BEFORE the guardrails, so the
filesystem_paths allowlist validates the real post-expansion path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import pytest

from yoker.config import Config, PermissionsConfig
from yoker.core._processing import _expand_tilde_args, _run_tool
from yoker.tools.annotations import ReadPath, Text, WritePath
from yoker.tools.guardrails.path import ReadPathGuardrail, WritePathGuardrail
from yoker.tools.registry import ToolRegistry
from yoker.tools.schema import build_tool_spec

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
  """Isolate and pin ``HOME`` for every test.

  ``os.path.expanduser`` is a no-op when HOME is unset (e.g. under some
  CI/sandbox environments), and a real-HOME-dependent test would be
  non-deterministic. Mirrors the pattern in test_usage.py / test_context.py.
  """
  home = tmp_path / "home"
  home.mkdir()
  monkeypatch.setenv("HOME", str(home))
  monkeypatch.setenv("USERPROFILE", str(home))  # Windows expanduser source.
  return home


async def _dummy_search(
  path: Annotated[str, ReadPath("Directory or file to search in")],
  pattern: Annotated[str, Text("Search pattern")] = "",
) -> Any:
  """Stand-in read tool — records the path argument it received."""
  return {"received_path": path, "received_pattern": pattern}


async def _dummy_write(
  path: Annotated[str, WritePath("Path to the file to write")],
  content: Annotated[str, Text("Content to write")],
) -> Any:
  """Stand-in write tool — records the path argument it received."""
  return {"received_path": path}


async def _dummy_capture_all(**kwargs: Any) -> Any:
  """Tool without path annotations — receives arguments verbatim."""
  return {"received": dict(kwargs)}


class _FakeAgent:
  """Minimal agent for _run_tool: registry, guardrails, config."""

  def __init__(self, config: Config) -> None:
    self.tools = ToolRegistry()
    self.tools.register(_dummy_search)
    self.tools.register(_dummy_write)
    self.tools.register(_dummy_capture_all)
    self._guardrails: dict[str, Any] = {
      "path_read": ReadPathGuardrail(config),
      "path_write": WritePathGuardrail(config),
    }
    self.config = config


# ---------------------------------------------------------------------------
# Unit: _expand_tilde_args
# ---------------------------------------------------------------------------


class TestExpandTildeArgs:
  """The helper expands ~ only in path-guarded string parameters."""

  def test_expands_read_path_arg(self) -> None:
    spec = build_tool_spec(_dummy_search)
    result = _expand_tilde_args(spec, {"path": "~/notes/file.md"})

    assert result["path"] == os.path.expanduser("~/notes/file.md")

  def test_expands_write_path_arg(self) -> None:
    spec = build_tool_spec(_dummy_write)
    result = _expand_tilde_args(spec, {"path": "~/Makefile", "content": "x"})

    assert result["path"] == os.path.expanduser("~/Makefile")
    assert result["content"] == "x"

  def test_bare_tilde_expands_to_home(self) -> None:
    spec = build_tool_spec(_dummy_search)
    result = _expand_tilde_args(spec, {"path": "~"})

    assert result["path"] == os.path.expanduser("~")

  def test_non_path_params_untouched(self) -> None:
    """A '~'-prefixed pattern is legitimate regex/glob data — verbatim."""
    spec = build_tool_spec(_dummy_search)
    result = _expand_tilde_args(spec, {"path": str(Path.cwd()), "pattern": "~[abc]"})

    assert result["pattern"] == "~[abc]"

  def test_no_tilde_returns_input_unchanged(self) -> None:
    spec = build_tool_spec(_dummy_search)
    args = {"path": "/tmp/somewhere"}

    assert _expand_tilde_args(spec, args) is args

  def test_no_guards_returns_input_unchanged(self) -> None:
    spec = build_tool_spec(_dummy_capture_all)
    args = {"path": "~/x"}

    assert _expand_tilde_args(spec, args) is args

  def test_non_string_path_value_passes_through(self) -> None:
    spec = build_tool_spec(_dummy_search)
    args = {"path": None}

    assert _expand_tilde_args(spec, args) is args


# ---------------------------------------------------------------------------
# Integration: _run_tool expands before guardrails; tool sees the real path
# ---------------------------------------------------------------------------


class TestRunToolTildeIntegration:
  """End-to-end through the tool funnel: expansion, allowlist, denylist."""

  def _agent(self, fake_home: Path, tmp_path: Path) -> _FakeAgent:
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path), "~")))
    return _FakeAgent(config)

  @pytest.mark.asyncio
  async def test_tool_receives_expanded_path(self, fake_home: Path, tmp_path: Path) -> None:
    """The search bug scenario: '~'-relative path must reach the tool expanded."""
    (fake_home / "notes").mkdir()
    agent = self._agent(fake_home, tmp_path)

    result, success, _ = await _run_tool(agent, "_dummy_search", {"path": "~/notes"})

    assert success is True, f"Expected success, got: {result}"
    assert "Path not found" not in result
    assert result == str({"received_path": os.path.expanduser("~/notes"), "received_pattern": ""})

  @pytest.mark.asyncio
  async def test_tilde_outside_allowed_root_blocked(self, fake_home: Path, tmp_path: Path) -> None:
    """Expanded path must be validated against the allowlist — no escape."""
    # Disjoint allowed root: fake_home lives under tmp_path's PARENT, so the
    # expanded '~/notes' cannot fall inside tmp_path by coincidence.
    other_root = tmp_path / "other-root"
    other_root.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(other_root),)))
    agent = _FakeAgent(config)

    result, success, _ = await _run_tool(agent, "_dummy_search", {"path": "~/notes"})

    assert success is False
    assert "outside allowed" in result

  @pytest.mark.asyncio
  async def test_tilde_traversal_outside_home_blocked(self, fake_home: Path) -> None:
    """'~/..' expands above the allowed '~' root — must be blocked."""
    # Allowlist only '~' (→ fake_home); '~/..' escapes one level above it.
    config = Config(permissions=PermissionsConfig(filesystem_paths=("~",)))
    agent = _FakeAgent(config)

    result, success, _ = await _run_tool(agent, "_dummy_search", {"path": "~/.."})

    assert success is False
    assert "outside allowed" in result

  @pytest.mark.asyncio
  async def test_tilde_write_to_protected_makefile_blocked(
    self, fake_home: Path, tmp_path: Path
  ) -> None:
    """The Makefile denylist must still apply to expanded '~' paths."""
    agent = self._agent(fake_home, tmp_path)

    result, success, _ = await _run_tool(
      agent, "_dummy_write", {"path": "~/Makefile", "content": "pwned"}
    )

    assert success is False
    assert "write-protected" in result.lower()

  @pytest.mark.asyncio
  async def test_non_path_arg_verbatim_through_funnel(
    self, fake_home: Path, tmp_path: Path
  ) -> None:
    """Non-path-guarded parameters pass through the funnel unexpanded."""
    agent = self._agent(fake_home, tmp_path)

    result, success, _ = await _run_tool(
      agent, "_dummy_capture_all", {"pattern": "~", "other": "~/literal"}
    )

    assert success is True
    assert "'pattern': '~'" in result
    assert "'other': '~/literal'" in result
