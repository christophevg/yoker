"""Windows-only tests for the make tool platform gate.

The main ``test_make.py`` module is skipped on Windows because the make tool
uses POSIX-only APIs (``os.killpg``, ``signal.SIGKILL``, ``start_new_session``).
This module verifies the Windows platform gate returns a clear ``ToolResult``
error instead of crashing with ``AttributeError``.

Skipped on POSIX (the POSIX path is covered by ``test_make.py``).
"""

import asyncio
import sys
from pathlib import Path

import pytest

from yoker.builtin import make
from yoker.config import MakeToolConfig, ToolsSharedConfig
from yoker.tools.context import ToolContext


def _make_context() -> ToolContext:
  return ToolContext(
    config=MakeToolConfig(),
    shared=ToolsSharedConfig(),
    backends={},
  )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only platform gate test")
class TestWindowsPlatformGate:
  """The make tool refuses to run on Windows with a clear error."""

  def test_make_rejected_on_windows(self, tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("check:\n\t@echo ok\n")
    result = asyncio.run(make(target="check", ctx=_make_context(), cwd=str(tmp_path)))
    assert not result.success
    assert "not available on Windows" in result.error
