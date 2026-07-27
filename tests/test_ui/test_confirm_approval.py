"""Tests for ``UIHandler.confirm_approval`` implementations (MBI-009 T12)."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rich.console import Console

from yoker.ui.batch import BatchUIHandler
from yoker.ui.interactive import InteractiveUIHandler

# ---------------------------------------------------------------------------
# BatchUIHandler.confirm_approval — always False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_confirm_approval_always_false() -> None:
  handler = BatchUIHandler()
  result = await handler.confirm_approval("/some/path/Makefile", "--- before\n+++ after\n")
  assert result is False


@pytest.mark.asyncio
async def test_batch_confirm_approval_false_for_empty_diff() -> None:
  handler = BatchUIHandler()
  result = await handler.confirm_approval("/some/path/Makefile", "")
  assert result is False


# ---------------------------------------------------------------------------
# InteractiveUIHandler.confirm_approval — y/N prompt
# ---------------------------------------------------------------------------
#
# On CI runners without a real TTY, constructing prompt_toolkit's
# ``PromptSession`` raises ``NoConsoleScreenBufferError`` on Windows and hangs
# on macOS. We patch ``PromptSession`` at the module level so the handler is
# built against a stub session whose ``prompt_async`` returns canned answers
# (or raises canned exceptions), exercising only the ``confirm_approval``
# logic on every platform.


def _make_interactive_handler(
  answers: list[str] | None = None,
  raises: type[BaseException] | None = None,
  console: Console | None = None,
) -> InteractiveUIHandler:
  """Build an ``InteractiveUIHandler`` backed by a stub ``PromptSession``.

  Args:
    answers: Canned answers returned sequentially by ``prompt_async``. An
      exhausted iterator yields ``""`` (the empty-Enter default).
    raises: Exception type raised by ``prompt_async`` instead of returning.
    console: Optional Rich console (default: a fresh one).
  """
  answers_iter = iter(answers or [])

  async def _prompt_async(_prompt: str, is_password: bool = False) -> str:
    if raises is not None:
      raise raises()
    try:
      return next(answers_iter)
    except StopIteration:
      return ""

  # ``PromptSession`` is called inside ``_create_session`` during
  # ``__init__``; replace it with a stub that records the canned behavior.
  stub_session = SimpleNamespace(prompt_async=_prompt_async)

  with patch("yoker.ui.interactive.PromptSession", return_value=stub_session):
    handler = InteractiveUIHandler(history_file="none", console=console)

  return handler


@pytest.mark.asyncio
async def test_interactive_confirm_approval_yes_returns_true() -> None:
  handler = _make_interactive_handler(["y"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is True


@pytest.mark.asyncio
async def test_interactive_confirm_approval_full_yes_returns_true() -> None:
  handler = _make_interactive_handler(["yes"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is True


@pytest.mark.asyncio
async def test_interactive_confirm_approval_uppercase_yes_returns_true() -> None:
  handler = _make_interactive_handler(["Y"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is True


@pytest.mark.asyncio
async def test_interactive_confirm_approval_no_returns_false() -> None:
  handler = _make_interactive_handler(["n"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_empty_returns_false() -> None:
  """Empty response (Enter) defaults to denial (fail-safe)."""
  handler = _make_interactive_handler([""])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_eof_returns_false() -> None:
  """EOFError (Ctrl+D) is treated as denial — fail-safe."""
  handler = _make_interactive_handler(raises=EOFError)
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_ctrl_c_returns_false() -> None:
  """KeyboardInterrupt is caught and treated as denial."""
  handler = _make_interactive_handler(raises=KeyboardInterrupt)
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_renders_diff(
  capsys: pytest.CaptureFixture[str],
) -> None:
  """The diff content is rendered to the console before prompting."""
  console = Console(file=StringIO(), force_terminal=False, width=80)
  handler = _make_interactive_handler(["n"], console=console)
  diff = "--- Makefile (before)\n+++ Makefile (after)\n@@ -1,1 +1,1 @@\n-old\n+new\n"
  result = await handler.confirm_approval("/x/Makefile", diff)
  assert result is False
  output = console.file.getvalue()
  # The diff lines are rendered (with formatting, so check for substrings).
  assert "old" in output
  assert "new" in output
  # The prompt header is shown.
  assert "Protected file" in output or "Makefile" in output
