"""Tests for plugin loader."""

import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from yoker.exceptions import PluginError
from yoker.plugins.loader import (
  PluginComponents,
  _extract_list,
  load_agent_definition_from_string,
  load_plugin,
  load_plugins,
)


class TestLoadPlugin:
  """Tests for load_plugin function."""

  def test_load_plugin_with_tools(self):
    """Test loading plugin with tools."""
    from yoker.tools import ReadTool

    # Create mock module
    module = ModuleType("test_pkg.yoker")
    module.TOOLS = [ReadTool()]
    module.SKILLS = []
    module.AGENTS = []

    with patch.dict(sys.modules, {"test_pkg.yoker": module}):
      plugin = load_plugin("test_pkg")

      assert plugin is not None
      assert len(plugin.tools) == 1
      assert isinstance(plugin.tools[0], ReadTool)
      assert plugin.source == "test_pkg"

  def test_load_plugin_with_skills(self):
    """Test loading plugin with skills."""
    from yoker.skills import Skill

    skill = Skill(
      name="test-skill",
      description="Test skill",
      content="Test content",
    )

    module = ModuleType("test_pkg.yoker")
    module.TOOLS = []
    module.SKILLS = [skill]
    module.AGENTS = []

    with patch.dict(sys.modules, {"test_pkg.yoker": module}):
      plugin = load_plugin("test_pkg")

      assert plugin is not None
      assert len(plugin.skills) == 1
      assert plugin.skills[0].name == "test-skill"

  def test_load_plugin_without_yoker_module(self):
    """Test loading package without yoker submodule."""
    plugin = load_plugin("nonexistent_package_xyz")

    assert plugin is None

  def test_load_plugin_with_import_error(self):
    """Test plugin that fails to import."""

    # Create a module that will fail when imported
    def raise_import_error(name):
      if name == "broken_plugin.yoker":
        raise ImportError("Broken plugin")
      raise ImportError(f"No module named '{name}'")

    with patch("importlib.import_module", side_effect=raise_import_error):
      # ImportError from missing module returns None
      plugin = load_plugin("missing_module")
      assert plugin is None

  def test_load_plugin_with_critical_error(self):
    """Test plugin that has a critical import error."""

    def raise_runtime_error(name):
      if name == "broken_plugin.yoker":
        raise RuntimeError("Critical plugin error")
      raise ImportError(f"No module named '{name}'")

    with patch("importlib.import_module", side_effect=raise_runtime_error):
      # Non-ImportError raises PluginError
      with pytest.raises(PluginError) as exc_info:
        load_plugin("broken_plugin")

      assert exc_info.value.package == "broken_plugin"
      assert "Critical plugin error" in str(exc_info.value)


class TestExtractList:
  """Tests for _extract_list helper function."""

  def test_extract_list_with_list(self):
    """Test extracting a list from module."""
    module = ModuleType("test")
    module.TOOLS = ["tool1", "tool2"]

    result = _extract_list(module, "TOOLS")

    assert result == ["tool1", "tool2"]

  def test_extract_list_missing_attribute(self):
    """Test extracting list when attribute doesn't exist."""
    module = ModuleType("test")

    result = _extract_list(module, "MISSING")

    assert result == []

  def test_extract_list_not_a_list(self):
    """Test extracting list when attribute is not a list."""
    module = ModuleType("test")
    module.TOOLS = "not a list"

    result = _extract_list(module, "TOOLS")

    assert result == []

  def test_extract_list_none_value(self):
    """Test extracting list when attribute is None."""
    module = ModuleType("test")
    module.TOOLS = None

    result = _extract_list(module, "TOOLS")

    assert result == []


class TestLoadPlugins:
  """Tests for load_plugins function."""

  def test_load_multiple_plugins(self):
    """Test loading multiple plugins."""
    from yoker.tools import ListTool, ReadTool

    module1 = ModuleType("pkg1.yoker")
    module1.TOOLS = [ReadTool()]
    module1.SKILLS = []
    module1.AGENTS = []

    module2 = ModuleType("pkg2.yoker")
    module2.TOOLS = [ListTool()]
    module2.SKILLS = []
    module2.AGENTS = []

    with patch.dict(sys.modules, {"pkg1.yoker": module1, "pkg2.yoker": module2}):
      plugins = load_plugins(["pkg1", "pkg2"])

      assert len(plugins) == 2
      assert plugins[0].source == "pkg1"
      assert plugins[1].source == "pkg2"

  def test_load_plugins_with_missing(self):
    """Test loading plugins when some don't exist."""
    from yoker.tools import ReadTool

    module = ModuleType("exists.yoker")
    module.TOOLS = [ReadTool()]
    module.SKILLS = []
    module.AGENTS = []

    with patch.dict(sys.modules, {"exists.yoker": module}):
      plugins = load_plugins(["exists", "nonexistent"])

      # Only existing plugins loaded
      assert len(plugins) == 1
      assert plugins[0].source == "exists"

  def test_load_plugins_with_error(self):
    """Test loading plugins with critical error."""

    def raise_error(name):
      if name == "broken.yoker":
        raise RuntimeError("Plugin error")
      raise ImportError(f"No module named '{name}'")

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
    assert "read" in agent_def.tools

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
    from yoker.tools import ReadTool

    tools = [ReadTool()]

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
