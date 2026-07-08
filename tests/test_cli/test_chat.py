"""Tests for the ``yoker chat`` subcommand handler (MBI-004 task 4.2).

The bulk of the REPL/UI tests remain in ``tests/test_main.py`` (they test the
extracted functions via ``yoker.cli.chat`` imports). This file verifies the
module is importable and exports the expected public API.
"""

from yoker.cli.chat import create_ui, run_chat


class TestChatModule:
  """Verify cli.chat module structure."""

  def test_run_chat_callable(self):
    """run_chat is a callable function."""
    assert callable(run_chat)

  def test_create_ui_callable(self):
    """create_ui is a callable function."""
    assert callable(create_ui)
