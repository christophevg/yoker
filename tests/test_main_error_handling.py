"""Tests for __main__.py error handling."""

import sys
from io import StringIO
from unittest.mock import patch

import pytest
from clevis import SecurityError


class TestMainErrorHandling:
  """Test error handling in main()."""

  def test_value_error_on_invalid_agent_path(self):
    """Test that ValueError from invalid agent path is caught and displayed cleanly."""
    # Simulate running: python -m yoker --agents-definition /nonexistent
    test_args = ["yoker", "--agents-definition", "/nonexistent/agent.md"]

    with patch.object(sys, "argv", test_args):
      with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        # The ValueError is raised by Session._resolve_definition (before
        # Agent construction), so the Agent mock is not exercised; patch
        # yoker.session.Agent for consistency with the Session-based path.
        with patch("yoker.session.Agent") as mock_agent_cls:
          mock_agent_cls.side_effect = ValueError("Agent definition file not found")
          with pytest.raises(SystemExit) as exc_info:
            from yoker.__main__ import main

            main()

        # Should exit with code 1
        assert exc_info.value.code == 1

        # Check error message in stderr — _resolve_definition now raises a
        # "could not be resolved" message (file path missing + not in registry).
        output = mock_stderr.getvalue()
        assert "Error:" in output
        assert "could not be resolved" in output

  def test_security_error_on_insecure_config_permissions(self):
    """Test that SecurityError from clevis is caught and displayed cleanly."""
    # Simulate running: python -m yoker when config file has wrong permissions.
    # The bootstrap gate (config_provided) is a separate concern from the
    # security-permissions check exercised here, so it is bypassed by mocking
    # config_provided to return True. This test targets the SecurityError
    # handling path in main(), not the first-run no-config gate.
    test_args = ["yoker"]

    with patch.object(sys, "argv", test_args):
      with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        with patch("yoker.cli.chat.config_provided", return_value=True):
          with patch("yoker.session.Agent") as mock_agent_cls:
            error_msg = (
              "Configuration file /path/to/yoker.toml is readable by group/other "
              "(mode 0o644). Use 'chmod 600 /path/to/yoker.toml' to fix."
            )
            mock_agent_cls.side_effect = SecurityError(
              error_msg, path="/path/to/yoker.toml", check="file_permissions"
            )
            with pytest.raises(SystemExit) as exc_info:
              from yoker.__main__ import main

              main()

        # Should exit with code 1
        assert exc_info.value.code == 1

        # Check error message in stderr (no stack trace)
        output = mock_stderr.getvalue()
        assert "Error:" in output
        assert "Configuration file" in output
        assert "readable by group/other" in output
        assert "chmod 600" in output
        # Should NOT contain stack trace indicators
        assert "Traceback" not in output
        assert "SecurityError" not in output
