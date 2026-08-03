"""Tests for ``UIHandler.confirm_approval`` implementations (MBI-009 T12)."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

from yoker.ui.batch import BatchUIHandler
from yoker.ui.interactive import InteractiveUIHandler

# ---------------------------------------------------------------------------
# BatchUIHandler — does not provide confirm_approval (optional pattern)
# ---------------------------------------------------------------------------


def test_batch_handler_does_not_provide_confirm_approval() -> None:
  """BatchUIHandler should not provide confirm_approval (optional pattern)."""
  handler = BatchUIHandler()
  assert not hasattr(handler, "confirm_approval")


# ---------------------------------------------------------------------------
# InteractiveUIHandler.confirm_approval — y/N prompt
# ---------------------------------------------------------------------------
#
# On CI runners without a real TTY, constructing prompt_toolkit's
# ``PromptSession`` raises ``NoConsoleScreenBufferError`` on Windows and hangs
# on macOS. Because the merged handler creates the ``PromptSession`` lazily
# (on first ``get_input`` / ``get_secret_input`` / ``confirm_approval``),
# the patch must stay active for the duration of each test — including the
# ``confirm_approval`` call, not just ``__init__``. We use a fixture that
# patches ``PromptSession`` at the module level for the whole test, and tests
# configure the stub session's ``prompt_async`` behavior.


@pytest.fixture
def stub_session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
  """Patch ``PromptSession`` at module level with a stub for the test's duration.

  The stub's ``prompt_async`` is a coroutine that returns ``""`` by default.
  Tests reassign ``prompt_async`` (or set ``answers`` / ``raises``) to drive
  the desired behavior.
  """
  state: dict[str, Any] = {"answers": [], "raises": None}

  async def _prompt_async(_prompt: str, is_password: bool = False, **_kw: Any) -> str:
    if state["raises"] is not None:
      raise state["raises"]()
    answers = state["answers"]
    if answers:
      return answers.pop(0)
    return ""

  stub = SimpleNamespace(prompt_async=_prompt_async, is_password=False)
  monkeypatch.setattr("yoker.ui.interactive.PromptSession", lambda *a, **kw: stub)
  stub._state = state  # type: ignore[attr-defined]
  return stub


def _make_handler(
  stub: SimpleNamespace,
  answers: list[str] | None = None,
  raises: type[BaseException] | None = None,
  console: Console | None = None,
) -> InteractiveUIHandler:
  """Build an ``InteractiveUIHandler`` against the patched ``PromptSession``."""
  stub._state["answers"] = list(answers or [])  # type: ignore[attr-defined]
  stub._state["raises"] = raises  # type: ignore[attr-defined]
  return InteractiveUIHandler(history_file="none", console=console)


@pytest.mark.asyncio
async def test_interactive_confirm_approval_yes_returns_true(
  stub_session: SimpleNamespace,
) -> None:
  handler = _make_handler(stub_session, answers=["y"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is True


@pytest.mark.asyncio
async def test_interactive_confirm_approval_full_yes_returns_true(
  stub_session: SimpleNamespace,
) -> None:
  handler = _make_handler(stub_session, answers=["yes"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is True


@pytest.mark.asyncio
async def test_interactive_confirm_approval_uppercase_yes_returns_true(
  stub_session: SimpleNamespace,
) -> None:
  handler = _make_handler(stub_session, answers=["Y"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is True


@pytest.mark.asyncio
async def test_interactive_confirm_approval_no_returns_false(
  stub_session: SimpleNamespace,
) -> None:
  handler = _make_handler(stub_session, answers=["n"])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_empty_returns_false(
  stub_session: SimpleNamespace,
) -> None:
  """Empty response (Enter) defaults to denial (fail-safe)."""
  handler = _make_handler(stub_session, answers=[""])
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_eof_returns_false(
  stub_session: SimpleNamespace,
) -> None:
  """EOFError (Ctrl+D) is treated as denial — fail-safe."""
  handler = _make_handler(stub_session, raises=EOFError)
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_ctrl_c_returns_false(
  stub_session: SimpleNamespace,
) -> None:
  """KeyboardInterrupt is caught and treated as denial."""
  handler = _make_handler(stub_session, raises=KeyboardInterrupt)
  result = await handler.confirm_approval("/x/Makefile", "+all:\n")
  assert result is False


@pytest.mark.asyncio
async def test_interactive_confirm_approval_renders_diff(
  stub_session: SimpleNamespace,
) -> None:
  """The diff content is rendered to the console before prompting."""
  console = Console(file=StringIO(), force_terminal=False, width=80)
  handler = _make_handler(stub_session, answers=["n"], console=console)
  diff = "--- Makefile (before)\n+++ Makefile (after)\n@@ -1,1 +1,1 @@\n-old\n+new\n"
  result = await handler.confirm_approval("/x/Makefile", diff)
  assert result is False
  output = console.file.getvalue()
  assert "old" in output
  assert "new" in output
  assert "Protected file" in output or "Makefile" in output


# ---------------------------------------------------------------------------
# InteractiveUIHandler.confirm_approval — git operation approval (kind="git")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interactive_confirm_approval_git_shows_git_title(
  stub_session: SimpleNamespace,
) -> None:
  """Git approval shows 'Git operation' title, not 'Protected file'."""
  console = Console(file=StringIO(), force_terminal=False, width=80)
  handler = _make_handler(stub_session, answers=["y"], console=console)
  result = await handler.confirm_approval("git commit", "staged diff", kind="git")
  assert result is True
  output = console.file.getvalue()
  assert "Git operation" in output
  assert "Protected file" not in output
  assert "git commit" in output


@pytest.mark.asyncio
async def test_interactive_confirm_approval_git_prompt_says_approve_not_write(
  stub_session: SimpleNamespace,
) -> None:
  """Git approval panel says 'run' not 'modify', and no 'write to' language."""
  console = Console(file=StringIO(), force_terminal=False, width=80)
  handler = _make_handler(stub_session, answers=["n"], console=console)
  await handler.confirm_approval("git push", "commits to push", kind="git")
  output = console.file.getvalue()
  assert "Agent wants to run" in output
  assert "modify" not in output
  assert "write to" not in output.lower()


@pytest.mark.asyncio
async def test_interactive_confirm_approval_file_default_kind(
  stub_session: SimpleNamespace,
) -> None:
  """Default kind='file' preserves backward-compatible behavior."""
  console = Console(file=StringIO(), force_terminal=False, width=80)
  handler = _make_handler(stub_session, answers=["n"], console=console)
  await handler.confirm_approval("/x/Makefile", "+all:\n")
  output = console.file.getvalue()
  assert "Protected file" in output
  assert "Agent wants to modify" in output
