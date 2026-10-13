"""Tests for the UI-layer /export command."""

from unittest.mock import MagicMock

import pytest

from yoker.core import Agent
from yoker.ui import BatchUIHandler
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.export import DESCRIPTION, handle


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


def _make_agent(messages):
  """Create a mock agent whose context returns the given messages."""
  agent = MagicMock(spec=Agent)
  agent.context = MagicMock()
  agent.context.get_messages.return_value = messages
  return agent


def _msg(role, content, **extra):
  """Build a context message dict like BaseContextManager.add_message."""
  return {"role": role, "content": content, **extra}


class TestExportCommand:
  """Tests for /export command in the UI layer."""

  @pytest.mark.asyncio
  async def test_export_to_explicit_path(self, tmp_path):
    """/export <path> writes the last assistant response to that file."""
    agent = _make_agent(
      [
        _msg("user", "Question?"),
        _msg("assistant", "The answer is 42."),
      ]
    )
    ui = MockUI()
    target = tmp_path / "out.md"

    result = await handle(str(target), agent, ui)

    assert str(target) in result
    assert target.read_text(encoding="utf-8") == "The answer is 42."

  @pytest.mark.asyncio
  async def test_export_overwrites_existing_file(self, tmp_path):
    """/export to an existing path overwrites it."""
    agent = _make_agent([_msg("assistant", "new content")])
    ui = MockUI()
    target = tmp_path / "out.md"
    target.write_text("old content", encoding="utf-8")

    await handle(str(target), agent, ui)

    assert target.read_text(encoding="utf-8") == "new content"

  @pytest.mark.asyncio
  async def test_export_default_writes_timestamped_file_in_cwd(self, tmp_path, monkeypatch):
    """/export without args writes yoker-response-<HHMMSS>.md to the cwd."""
    monkeypatch.chdir(tmp_path)
    agent = _make_agent([_msg("assistant", "default path content")])
    ui = MockUI()

    result = await handle("", agent, ui)

    files = list(tmp_path.glob("yoker-response-*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "default path content"
    assert files[0].name in result

  @pytest.mark.asyncio
  async def test_export_picks_last_assistant_message(self, tmp_path):
    """/export prefers the most recent assistant message over other roles."""
    agent = _make_agent(
      [
        _msg("assistant", "older response"),
        _msg("user", "follow-up question"),
        _msg("assistant", "newer response"),
        _msg("user", "next turn input"),
      ]
    )
    ui = MockUI()
    target = tmp_path / "out.md"

    await handle(str(target), agent, ui)

    assert target.read_text(encoding="utf-8") == "newer response"

  @pytest.mark.asyncio
  async def test_export_exports_content_without_thinking(self, tmp_path):
    """Thinking is stored as a separate key and must not leak into the file."""
    agent = _make_agent(
      [
        _msg("assistant", "visible answer", thinking="secret reasoning"),
      ]
    )
    ui = MockUI()
    target = tmp_path / "out.md"

    await handle(str(target), agent, ui)

    assert target.read_text(encoding="utf-8") == "visible answer"

  @pytest.mark.asyncio
  async def test_export_without_assistant_message_returns_error(self):
    """/export in a conversation with no assistant response errors."""
    agent = _make_agent([_msg("user", "Question?"), _msg("system", "sys")])
    ui = MockUI()

    result = await handle("out.md", agent, ui)

    assert "nothing to export" in result.lower()

  @pytest.mark.asyncio
  async def test_export_with_empty_context_returns_error(self):
    """/export on an empty conversation errors."""
    agent = _make_agent([])
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "nothing to export" in result.lower()

  @pytest.mark.asyncio
  async def test_export_registered_in_default_registry(self, tmp_path, monkeypatch):
    """/export should be dispatchable from the default registry."""
    monkeypatch.chdir(tmp_path)
    agent = _make_agent([_msg("assistant", "dispatched content")])
    ui = MockUI()

    result = await create_default_registry().dispatch("/export", agent, ui)

    files = list(tmp_path.glob("yoker-response-*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "dispatched content"
    assert "dispatched content" not in result  # result is the confirmation line

  def test_description(self):
    """The /export command should describe itself and mention the path arg."""
    assert "export" in DESCRIPTION.lower()
