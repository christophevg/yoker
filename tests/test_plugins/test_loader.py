"""Tests for plugin loader."""

import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from yoker.builtin import read
from yoker.exceptions import PluginError
from yoker.plugins import PluginManifest
from yoker.plugins.loader import (
  PluginComponents,
  load_plugin,
)
from yoker.tools.schema import build_tool_spec


class TestLoadPlugin:
  """Tests for load_plugin function."""

  def test_load_plugin_with_tools(self):
    """Test loading plugin with tools."""
    manifest = PluginManifest(tools=[read])
    module = ModuleType("test_pkg")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"test_pkg": module}):
      plugin = load_plugin("test_pkg")

      assert plugin is not None
      assert len(plugin.tools) == 1
      spec = build_tool_spec(plugin.tools[0])
      assert spec.name == "read"
      assert plugin.source == "test_pkg"

  def test_load_plugin_with_skills(self):
    """Test loading plugin with skills."""
    from yoker.skills import Skill

    skill = Skill(
      simple_name="test-skill",
      description="Test skill",
      content="Test content",
    )

    manifest = PluginManifest(skills=[skill])
    module = ModuleType("test_pkg")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"test_pkg": module}):
      plugin = load_plugin("test_pkg")

      assert plugin is not None
      assert len(plugin.skills) == 1
      assert plugin.skills[0].name == "test-skill"

  def test_load_plugin_without_manifest(self):
    """Test package without manifest raises PluginError."""
    module = ModuleType("test_pkg")

    with patch.dict(sys.modules, {"test_pkg": module}):
      with pytest.raises(PluginError) as exc_info:
        load_plugin("test_pkg")

      assert exc_info.value.package == "test_pkg"
      assert "doesn't provide a manifest" in str(exc_info.value)

  def test_load_plugin_without_yoker_module(self):
    """Test loading missing package raises PluginError."""
    with pytest.raises(PluginError) as exc_info:
      load_plugin("nonexistent_package_xyz")

    assert exc_info.value.package == "nonexistent_package_xyz"
    assert "not found" in str(exc_info.value)

  def test_load_plugin_with_import_error(self):
    """Test missing plugin package raises PluginError."""

    def raise_import_error(name):
      raise ImportError(f"No module named '{name}'")

    with patch("importlib.import_module", side_effect=raise_import_error):
      with pytest.raises(PluginError) as exc_info:
        load_plugin("missing_module")

      assert exc_info.value.package == "missing_module"
      assert "not found" in str(exc_info.value)

  def test_load_plugin_with_critical_error(self):
    """Test plugin import that raises a non-ImportError."""

    def raise_runtime_error(name):
      raise RuntimeError("Critical plugin error")

    with patch("importlib.import_module", side_effect=raise_runtime_error):
      with pytest.raises(PluginError) as exc_info:
        load_plugin("broken_plugin")

      assert exc_info.value.package == "broken_plugin"
      assert "Critical plugin error" in str(exc_info.value)


class TestPluginComponents:
  """Tests for PluginComponents dataclass."""

  def test_components_creation(self):
    """Test creating PluginComponents."""
    tools = [read]

    components = PluginComponents(
      tools=tools,
      skills=[],
      agents=[],
      source="test_pkg",
    )

    assert len(components.tools) == 1
    assert components.source == "test_pkg"

  def test_components_empty(self):
    """Test creating empty PluginComponents."""
    components = PluginComponents(
      tools=[],
      skills=[],
      agents=[],
      source="empty_pkg",
    )

    assert components.tools == []
    assert components.skills == []
    assert components.agents == []
    assert components.source == "empty_pkg"
