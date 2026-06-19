"""Tests for plugin security system."""

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from yoker.config import Config, PluginsConfig
from yoker.plugins import PluginComponents
from yoker.plugins.security import (
  check_plugin_allowed,
  check_plugins_enabled,
  confirm_plugin,
  is_trusted,
  reset_session_trusted,
)


@pytest.fixture(autouse=True)
def reset_session():
  """Reset session-trusted set before each test."""
  reset_session_trusted()
  yield
  reset_session_trusted()


class TestPluginsConfig:
  """Tests for PluginsConfig."""

  def test_plugins_config_defaults(self) -> None:
    """Test PluginsConfig default values."""
    config = PluginsConfig()
    assert config.enabled is False
    assert config.packages == ()
    assert config.trusted == {}

  def test_plugins_config_enabled(self) -> None:
    """Test PluginsConfig with enabled=True."""
    config = PluginsConfig(enabled=True)
    assert config.enabled is True

  def test_plugins_config_with_packages(self) -> None:
    """Test PluginsConfig with packages."""
    config = PluginsConfig(packages=("pkgq", "c3"))
    assert config.packages == ("pkgq", "c3")

  def test_plugins_config_with_trusted(self) -> None:
    """Test PluginsConfig with trusted plugins."""
    config = PluginsConfig(trusted={"pkgq": True, "c3": True})
    assert config.trusted == {"pkgq": True, "c3": True}


class TestIsTrusted:
  """Tests for is_trusted function."""

  def test_is_trusted_in_config(self) -> None:
    """Test plugin trusted in config."""
    config = Config(plugins=PluginsConfig(trusted={"pkgq": True}))
    assert is_trusted("pkgq", config) is True

  def test_is_trusted_not_in_config(self) -> None:
    """Test plugin not trusted in config."""
    config = Config(plugins=PluginsConfig(trusted={"pkgq": True}))
    assert is_trusted("other_plugin", config) is False

  def test_is_trusted_session_confirmed(self) -> None:
    """Test plugin confirmed in session."""
    config = Config(plugins=PluginsConfig(trusted={}))
    # Simulate session confirmation
    from yoker.plugins.security import _session_trusted

    _session_trusted.add("session_plugin")
    assert is_trusted("session_plugin", config) is True

  def test_is_trusted_empty_config(self) -> None:
    """Test with empty trusted config."""
    config = Config(plugins=PluginsConfig())
    assert is_trusted("any_plugin", config) is False


class TestConfirmPlugin:
  """Tests for confirm_plugin function."""

  def test_confirm_plugin_non_interactive(self) -> None:
    """Test confirm_plugin in non-interactive mode."""
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="test_plugin",
    )

    # Mock stdin.isatty() to return False (non-interactive)
    with patch.object(sys.stdin, "isatty", return_value=False):
      result = confirm_plugin("test_plugin", plugin)
      assert result is False

  def test_confirm_plugin_interactive_yes(self) -> None:
    """Test confirm_plugin with user saying yes."""
    from yoker.skills import Skill

    # Create mock plugin with tools/skills/agents
    mock_tool = MagicMock(spec=["name", "description"])
    mock_tool.name = "test_tool"
    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "test_skill"

    plugin = PluginComponents(
      tools=[mock_tool],
      skills=[mock_skill],
      agents=[],
      source="test_plugin",
    )

    # Mock stdin.isatty() to return True (interactive)
    # Mock input() to return "y"
    with (
      patch.object(sys.stdin, "isatty", return_value=True),
      patch("builtins.input", return_value="y"),
    ):
      result = confirm_plugin("test_plugin", plugin)
      assert result is True

      # Check session trusted
      from yoker.plugins.security import _session_trusted

      assert "test_plugin" in _session_trusted

  def test_confirm_plugin_interactive_no(self) -> None:
    """Test confirm_plugin with user saying no."""
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="test_plugin",
    )

    with (
      patch.object(sys.stdin, "isatty", return_value=True),
      patch("builtins.input", return_value="n"),
    ):
      result = confirm_plugin("test_plugin", plugin)
      assert result is False

      # Check session not trusted
      from yoker.plugins.security import _session_trusted

      assert "test_plugin" not in _session_trusted

  def test_confirm_plugin_interactive_eof(self) -> None:
    """Test confirm_plugin with EOF (Ctrl+D)."""
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="test_plugin",
    )

    with (
      patch.object(sys.stdin, "isatty", return_value=True),
      patch("builtins.input", side_effect=EOFError),
    ):
      result = confirm_plugin("test_plugin", plugin)
      assert result is False


class TestCheckPluginsEnabled:
  """Tests for check_plugins_enabled function."""

  def test_plugins_enabled_true(self) -> None:
    """Test with plugins enabled."""
    config = Config(plugins=PluginsConfig(enabled=True))
    result = check_plugins_enabled(config)
    assert result is True

  def test_plugins_enabled_false(self) -> None:
    """Test with plugins disabled."""
    config = Config(plugins=PluginsConfig(enabled=False))
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
      result = check_plugins_enabled(config)
      assert result is False
      assert "Error: Plugins are disabled" in mock_stdout.getvalue()

  def test_plugins_disabled_default(self) -> None:
    """Test with default config (plugins disabled)."""
    config = Config()
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
      result = check_plugins_enabled(config)
      assert result is False
      assert "Error: Plugins are disabled" in mock_stdout.getvalue()


class TestCheckPluginAllowed:
  """Tests for check_plugin_allowed function."""

  def test_check_plugin_allowed_trusted(self) -> None:
    """Test plugin allowed when trusted."""
    config = Config(
      plugins=PluginsConfig(
        enabled=True,
        trusted={"trusted_plugin": True},
      )
    )
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="trusted_plugin",
    )

    result = check_plugin_allowed("trusted_plugin", config, plugin)
    assert result is True

  def test_check_plugin_allowed_not_trusted(self) -> None:
    """Test plugin not allowed when not trusted."""
    config = Config(
      plugins=PluginsConfig(
        enabled=True,
        trusted={},
      )
    )
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="untrusted_plugin",
    )

    # Mock non-interactive mode
    with patch.object(sys.stdin, "isatty", return_value=False):
      result = check_plugin_allowed("untrusted_plugin", config, plugin)
      assert result is False

  def test_check_plugin_allowed_session_confirmed(self) -> None:
    """Test plugin allowed after session confirmation."""
    config = Config(
      plugins=PluginsConfig(
        enabled=True,
        trusted={},
      )
    )
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="session_plugin",
    )

    # Mock interactive mode and user saying yes
    with (
      patch.object(sys.stdin, "isatty", return_value=True),
      patch("builtins.input", return_value="y"),
    ):
      # First call asks for confirmation
      result1 = check_plugin_allowed("session_plugin", config, plugin)
      assert result1 is True

      # Second call uses session trust
      result2 = check_plugin_allowed("session_plugin", config, plugin)
      assert result2 is True


class TestIntegration:
  """Integration tests for plugin security."""

  def test_full_workflow_enabled_trusted(self) -> None:
    """Test full workflow with enabled and trusted plugin."""
    config = Config(
      plugins=PluginsConfig(
        enabled=True,
        trusted={"test_plugin": True},
      )
    )

    # Level 1: Check plugins enabled
    assert check_plugins_enabled(config) is True

    # Level 2: Check plugin allowed
    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="test_plugin",
    )
    assert check_plugin_allowed("test_plugin", config, plugin) is True

  def test_full_workflow_disabled(self) -> None:
    """Test full workflow with plugins disabled."""
    config = Config(plugins=PluginsConfig(enabled=False))

    # Level 1: Check plugins enabled (should fail)
    with patch("sys.stdout", new_callable=StringIO):
      assert check_plugins_enabled(config) is False

  def test_full_workflow_not_trusted(self) -> None:
    """Test full workflow with untrusted plugin."""
    config = Config(
      plugins=PluginsConfig(
        enabled=True,
        trusted={},
      )
    )

    plugin = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="untrusted_plugin",
    )

    # Level 1: Check plugins enabled (should pass)
    assert check_plugins_enabled(config) is True

    # Level 2: Check plugin allowed (should fail in non-interactive mode)
    with patch.object(sys.stdin, "isatty", return_value=False):
      assert check_plugin_allowed("untrusted_plugin", config, plugin) is False

  def test_config_integration(self) -> None:
    """Test Config with PluginsConfig."""
    config = Config(plugins=PluginsConfig(enabled=True, trusted={"pkgq": True}))

    assert config.plugins.enabled is True
    assert "pkgq" in config.plugins.trusted
    assert config.plugins.trusted["pkgq"] is True
