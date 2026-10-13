"""Unit tests for the make tool's T6 outcome field (agent feedback 2026-09-16).

T4/T6: with post_filter active, the success verdict line ("All checks
passed!") can be filtered away, and stderr make-noise on success read as
failure. The make result now carries an ``outcome`` field (``pass`` /
``fail`` + which leg failed) that survives filtering because it is not a
string value, plus a leading one-line status so exit-0 is never framed
as an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from yoker.builtin.make import _OUTCOME_FAILED, _OUTCOME_PASSED, make
from yoker.config import Config, ToolsConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext

# POSIX-only: the make tool refuses to run on Windows (platform gate — the R4
# process-group kill relies on os.killpg + SIGKILL + start_new_session). Same
# skip as test_make.py; these tests exercise the POSIX subprocess path.
pytestmark = pytest.mark.skipif(
  sys.platform == "win32",
  reason="make tool requires POSIX process-group support",
)


def _write_makefile(tmp_path: Path, content: str) -> None:
  (tmp_path / "Makefile").write_text(content)


def _make_spec():
  registry = ToolRegistry()
  return registry.register(make)


def _make_context() -> ToolContext:
  config = Config(tools=ToolsConfig())
  return ToolContext(
    config=config.tools.make,
    shared=config.tools_shared,
    backends={},
  )


class TestMakeOutcomeField:
  """T6: outcome is pass/fail and never filtered away by post_filter."""

  @pytest.mark.asyncio
  async def test_success_outcome_pass(self, tmp_path: Path) -> None:
    _write_makefile(tmp_path, "check:\n\t@echo hi\n")
    result = await _make_spec().execute(target="check", ctx=_make_context(), cwd=str(tmp_path))
    assert result.success
    assert result.result["outcome"] == _OUTCOME_PASSED
    assert "passed_leg" not in result.result

  @pytest.mark.asyncio
  async def test_failure_outcome_fail(self, tmp_path: Path) -> None:
    _write_makefile(tmp_path, "check:\n\t@exit 2\n")
    result = await _make_spec().execute(target="check", ctx=_make_context(), cwd=str(tmp_path))
    assert not result.success
    assert result.result["outcome"] == _OUTCOME_FAILED
    assert result.result["passed_leg"] == "make"
    assert result.result["failed_leg"] == "target"

  @pytest.mark.asyncio
  async def test_outcome_survives_post_filter(self, tmp_path: Path) -> None:
    """post_filter strips stdout but verdict/outcome survive (exempt fields)."""
    _write_makefile(tmp_path, "check:\n\t@echo 'All checks passed!'\n\t@echo noise\n")
    result = await _make_spec().execute(target="check", ctx=_make_context(), cwd=str(tmp_path))
    assert result.success
    # Simulate what _execute_tool does when the agent filters aggressively.
    from yoker.core._processing import _apply_post_filter

    filtered = _apply_post_filter(result, "ZZZ_no_match")
    assert isinstance(filtered.result, dict)
    # T6: verdict/outcome are exempt from filtering — they carry the
    # pass/fail verdict an aggressive error-oriented filter needs.
    assert filtered.result["outcome"] == _OUTCOME_PASSED
    assert filtered.result["verdict"] == "make 'check' passed (exit 0)"
    assert filtered.result["exit_code"] == 0
    # stdout got the filter treatment (zero matches → summary appended).
    assert "post_filter" in (filtered.result["stdout"] or "")

  @pytest.mark.asyncio
  async def test_verdict_leads_with_target_and_exit(self, tmp_path: Path) -> None:
    _write_makefile(tmp_path, "check:\n\t@echo hi\n")
    result = await _make_spec().execute(target="check", ctx=_make_context(), cwd=str(tmp_path))
    assert result.result["verdict"] == "make 'check' passed (exit 0)"

  @pytest.mark.asyncio
  async def test_failure_verdict_names_exit(self, tmp_path: Path) -> None:
    """make reports its own exit code (2) for a failed recipe."""
    _write_makefile(tmp_path, "check:\n\t@exit 3\n")
    result = await _make_spec().execute(target="check", ctx=_make_context(), cwd=str(tmp_path))
    assert not result.success
    assert result.result["verdict"] == f"make 'check' failed (exit {result.result['exit_code']})"
    assert result.result["outcome"] == _OUTCOME_FAILED
    assert result.result["failed_leg"] == "target"
