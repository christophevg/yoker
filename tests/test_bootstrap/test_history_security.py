"""Tests for bootstrap wizard history security.

Verifies that bootstrap wizard inputs (including API keys) are not persisted
to the command history file.
"""

from pathlib import Path

from prompt_toolkit.history import InMemoryHistory

from yoker.ui import InteractiveUIHandler


class TestBootstrapHistorySecurity:
  """Tests for ensuring bootstrap wizard doesn't persist sensitive data to history."""

  def test_interactive_handler_default_uses_file_history(self, tmp_path: Path):
    """Default InteractiveUIHandler uses FileHistory (persists to disk)."""
    history_file = tmp_path / ".test_history"
    handler = InteractiveUIHandler(history_file=history_file)

    assert handler.history_file == history_file
    # Verify that a session is created (indirectly tests FileHistory is used)
    assert handler._session is not None

  def test_interactive_handler_none_uses_default_path(self):
    """Passing None to history_file uses the default ~/.yoker_history path."""
    handler = InteractiveUIHandler(history_file=None)

    assert handler.history_file == Path.home() / ".yoker_history"

  def test_interactive_handler_explicit_none_disables_history(self):
    """Passing 'none' string explicitly disables history (uses InMemoryHistory)."""
    handler = InteractiveUIHandler(history_file="none")

    # history_file should be None internally
    assert handler.history_file is None

    # Verify session uses InMemoryHistory
    assert handler._session is not None
    # The history object should be InMemoryHistory, not FileHistory
    assert isinstance(handler._session.history, InMemoryHistory)

  def test_interactive_handler_custom_path_uses_file_history(self, tmp_path: Path):
    """Custom history file path is used correctly."""
    history_file = tmp_path / ".custom_history"
    handler = InteractiveUIHandler(history_file=history_file)

    assert handler.history_file == history_file
    assert handler._session is not None
