"""Tests for plugin loader."""

import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from yoker.exceptions import PluginError
from yoker.plugins import PluginManifest
from yoker.plugins.agents import load_agent_definition_from_string
from yoker.plugins.loader import (
  PluginComponents,
  load_plugin,
  load_plugins,
)
from yoker.tools import make_list_tool, make_read_tool
from yoker.tools.schema import build_tool_spec


class TestLoadPlugin:
  """Tests for load_plugin function."""

  def test_load_plugin_with_tools(self):
    """Test loading plugin with tools."""
    echo_tool = make_read_tool()
    manifest = PluginManifest(tools=[echo_tool])
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
      name="test-skill",
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
    """Test package without manifest returns None."""
    module = ModuleType("test_pkg")

    with patch.dict(sys.modules, {"test_pkg": module}):
      plugin = load_plugin("test_pkg")

      assert plugin is None

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


class TestLoadPlugins:
  """Tests for load_plugins function."""

  def test_load_multiple_plugins(self):
    """Test loading multiple plugins."""
    manifest1 = PluginManifest(tools=[make_read_tool()])
    module1 = ModuleType("pkg1")
    module1.__YOKER_MANIFEST__ = manifest1

    manifest2 = PluginManifest(tools=[make_list_tool()])
    module2 = ModuleType("pkg2")
    module2.__YOKER_MANIFEST__ = manifest2

    with patch.dict(sys.modules, {"pkg1": module1, "pkg2": module2}):
      plugins = load_plugins(["pkg1", "pkg2"])

      assert len(plugins) == 2
      assert plugins[0].source == "pkg1"
      assert plugins[1].source == "pkg2"

  def test_load_plugins_with_missing(self):
    """Test loading plugins raises PluginError when package is missing."""
    manifest = PluginManifest(tools=[make_read_tool()])
    module = ModuleType("exists")
    module.__YOKER_MANIFEST__ = manifest

    with patch.dict(sys.modules, {"exists": module}):
      with pytest.raises(PluginError) as exc_info:
        load_plugins(["exists", "nonexistent"])

      assert exc_info.value.package == "nonexistent"
      assert "not found" in str(exc_info.value)

  def test_load_plugins_with_error(self):
    """Test loading plugins with critical error."""

    def raise_error(name):
      raise RuntimeError("Plugin error")

    with patch("importlib.import_module", side_effect=raise_error):
      with pytest.raises(PluginError):
        load_plugins(["broken"])


class TestLoadAgentDefinitionFromString:
  """Tests for load_agent_definition_from_string function."""

  def test_load_agent_definition_valid(self):
    """Test loading valid agent definition."""
    content = """---
name: test-agent
description: Test agent
model: llama3.2
tools:
  - read
  - write
---

You are a test agent.
"""

    agent_def = load_agent_definition_from_string(content, namespace="pkg")

    assert agent_def is not None
    assert agent_def.name == "pkg:test-agent"
    assert agent_def.description == "Test agent"
    assert agent_def.model == "llama3.2"
    # Tools should be namespaced
    assert "pkg:read" in agent_def.tools
    assert "pkg:write" in agent_def.tools

  def test_load_agent_definition_without_namespace(self):
    """Test loading agent definition without namespace."""
    content = """---
name: test-agent
description: Test agent
---

You are a test agent.
"""

    agent_def = load_agent_definition_from_string(content)

    assert agent_def is not None
    assert agent_def.name == "test-agent"

  def test_load_agent_definition_missing_name(self):
    """Test loading agent definition without name."""
    content = """---
description: Test agent
---

You are a test agent.
"""

    agent_def = load_agent_definition_from_string(content)

    assert agent_def is None

  def test_load_agent_definition_invalid_yaml(self):
    """Test loading agent definition with invalid YAML."""
    content = """---
name: test-agent
description: Test agent
invalid yaml here
---

Content
"""

    agent_def = load_agent_definition_from_string(content)

    # Should handle gracefully
    assert agent_def is None


class TestPluginComponents:
  """Tests for PluginComponents dataclass."""

  def test_components_creation(self):
    """Test creating PluginComponents."""
    tools = [make_read_tool()]

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
