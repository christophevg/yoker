"""Tests for built-in plugin."""

from yoker.plugins import load_plugin


class TestLoadBuiltinPlugin:
  """Tests for the built-in yoker plugin."""

  def test_load_builtin_plugin_is_empty(self):
    """Test that load_plugin("yoker") returns an empty manifest.

    Built-in filesystem tools are registered directly by the Agent, so the
    built-in plugin manifest no longer duplicates them.
    """
    plugin = load_plugin("yoker")

    assert plugin is not None
    assert plugin.tools == []
    assert plugin.skills == []
    assert plugin.agents == []

  def test_load_builtin_plugin_source_is_yoker(self):
    """Test that the built-in plugin source is reported as yoker."""
    plugin = load_plugin("yoker")
    assert plugin is not None
    assert plugin.source == "yoker"
