"""Tests for yoker logging configuration."""

from unittest.mock import patch

import pytest

from yoker.config import Config, LoggingConfig
from yoker.core import Agent


class TestLoggingConfiguredFlag:
  """Tests for the _logging_configured flag and is_logging_configured helper."""

  @pytest.fixture(autouse=True)
  def reset_logging_configured(self, monkeypatch):
    """Reset the module-level flag so each test starts unconfigured."""
    monkeypatch.setattr("yoker.logging._logging_configured", False)

  def test_is_logging_configured_false_initially(self):
    """is_logging_configured should return False before configure_logging runs."""
    from yoker.logging import is_logging_configured

    assert is_logging_configured() is False

  def test_configure_logging_sets_configured_flag(self):
    """configure_logging should set the configured flag."""
    from yoker.logging import configure_logging, is_logging_configured

    with patch("yoker.logging.structlog.configure"):
      with patch("yoker.logging.logging.basicConfig"):
        config = LoggingConfig(level="WARNING")
        configure_logging(config, console=False)

        assert is_logging_configured() is True


class TestAgentAppliesLoggingConfig:
  """Tests that Agent applies logging configuration from the loaded config."""

  def test_agent_configures_logging_from_config(self):
    """Agent should call configure_logging using the loaded config's settings."""
    config = Config(logging=LoggingConfig(level="ERROR", format="json"))

    with patch("yoker.core.configure_logging") as mock_configure:
      Agent(config=config)

      mock_configure.assert_called_once_with(
        config.logging,
        console=True,
      )

  def test_agent_configures_logging_with_file(self):
    """Agent should pass the configured log file path to configure_logging."""
    config = Config(logging=LoggingConfig(level="DEBUG", file="/tmp/yoker.log"))

    with patch("yoker.core.configure_logging") as mock_configure:
      Agent(config=config)

      mock_configure.assert_called_once_with(
        config.logging,
        console=True,
      )


class TestMainLoggingSetup:
  """Tests for __main__._setup_logging."""

  def test_agent_disables_console_logging_from_cli(self):
    """CLI-launched Agent should configure logging with console disabled."""
    from yoker.core import Agent

    config = Config(logging=LoggingConfig(level="DEBUG", format="json", file="/tmp/yoker.log"))

    with patch("yoker.core.configure_logging") as mock_configure:
      Agent(config=config, console_logging=False)

      mock_configure.assert_called_once_with(
        config.logging,
        console=False,
      )

  def test_agent_disables_console_logging_without_file(self):
    """CLI-launched Agent should pass None for log_file when not configured."""
    from yoker.core import Agent

    config = Config(logging=LoggingConfig(level="WARNING"))

    with patch("yoker.core.configure_logging") as mock_configure:
      Agent(config=config, console_logging=False)

      mock_configure.assert_called_once_with(
        config.logging,
        console=False,
      )
