"""Tests for built-in plugin."""

from yoker.plugins import load_plugin


class TestLoadBuiltinPlugin:
  """Tests for the built-in yoker plugin."""

  def test_load_builtin_plugin_has_tools(self):
    """Test that load_plugin("yoker") returns builtin tools.

    Built-in tools (read, write, etc.) are registered via the builtin plugin
    manifest and loaded by the plugin system.
    """
    plugin = load_plugin("yoker")

    assert plugin is not None
    # Builtin tools are included in the manifest
    assert len(plugin.tools) > 0
    assert plugin.skills == []
    assert plugin.agents == []

  def test_load_builtin_plugin_source_is_yoker(self):
    """Test that the built-in plugin source is reported as yoker."""
    plugin = load_plugin("yoker")
    assert plugin is not None
    assert plugin.source == "yoker"
