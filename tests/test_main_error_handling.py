"""Tests for __main__.py error handling."""

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


class TestMainErrorHandling:
  """Test error handling in main()."""

  def test_value_error_on_invalid_agent_path(self):
    """Test that ValueError from invalid agent path is caught and displayed cleanly."""
    # Simulate running: python -m yoker --agents-definition /nonexistent
    test_args = ["yoker", "--agents-definition", "/nonexistent/agent.md"]

    with patch.object(sys, "argv", test_args):
      with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        # Mock create_prompt_session to avoid Windows console dependency
        mock_session = MagicMock()
        with patch("yoker.__main__.create_prompt_session", return_value=mock_session):
          with pytest.raises(SystemExit) as exc_info:
            from yoker.__main__ import main

            main()

          # Should exit with code 1
          assert exc_info.value.code == 1

          # Check error message in stdout (our catch block prints to stdout)
          output = mock_stdout.getvalue()
          assert "Error:" in output
          assert "Agent definition file not found" in output
