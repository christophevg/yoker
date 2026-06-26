"""Tests for ToolSpec integration with plugin system.

This test file demonstrates the architectural fix where tools are parsed into
ToolSpec objects during plugin load, making them consistent with skills/agents.
"""

import sys
from types import ModuleType
from unittest.mock import patch

from yoker.builtin import read
from yoker.plugins import PluginManifest
from yoker.plugins.loader import load_plugin
from yoker.tools.schema import ToolSpec


class TestToolSpecIntegration:
  """Tests that tools are parsed into ToolSpec during load."""

  def test_plugin_components_tools_are_toolspec(self):
    """Test that PluginComponents.tools contains ToolSpec objects."""
    # Arrange: Create a plugin manifest with tools
    manifest = PluginManifest(tools=[read])
    module = ModuleType("test_pkg")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"test_pkg": module}):
      # Act: Load the plugin
      plugin = load_plugin("test_pkg")

      # Assert: Tools should be ToolSpec objects
      assert len(plugin.tools) == 1
      assert isinstance(plugin.tools[0], ToolSpec)
      assert plugin.tools[0].name == "test_pkg:read"
      assert plugin.tools[0].simple_name == "read"
      assert plugin.tools[0].namespace == "test_pkg"

  def test_plugin_components_empty_tools(self):
    """Test that PluginComponents with empty tools works."""
    # Arrange: Create a plugin manifest without tools
    manifest = PluginManifest(tools=[])
    module = ModuleType("test_pkg_empty")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"test_pkg_empty": module}):
      # Act: Load the plugin
      plugin = load_plugin("test_pkg_empty")

      # Assert: Tools should be empty list
      assert plugin.tools == []
      assert isinstance(plugin.tools, list)

  def test_plugin_tools_have_name_attribute(self):
    """Test that tools have .name attribute accessible."""
    # Arrange: Create a plugin with tools
    manifest = PluginManifest(tools=[read])
    module = ModuleType("test_pkg_name")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"test_pkg_name": module}):
      # Act: Load the plugin
      plugin = load_plugin("test_pkg_name")

      # Assert: Can access .name attribute directly (like skills/agents)
      assert len(plugin.tools) == 1
      assert plugin.tools[0].name == "test_pkg_name:read"

  def test_multiple_tools_in_plugin(self):
    """Test loading multiple tools in a plugin."""
    from yoker.builtin import list

    # Arrange: Create a plugin with multiple tools
    manifest = PluginManifest(tools=[read, list])
    module = ModuleType("test_pkg_multi")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"test_pkg_multi": module}):
      # Act: Load the plugin
      plugin = load_plugin("test_pkg_multi")

      # Assert: All tools are ToolSpec objects
      assert len(plugin.tools) == 2
      assert all(isinstance(t, ToolSpec) for t in plugin.tools)
      tool_names = {t.name for t in plugin.tools}
      assert "test_pkg_multi:read" in tool_names
      assert "test_pkg_multi:list" in tool_names
