"""Tests for built-in plugin."""

from yoker.plugins.builtin import (
  AGENTS,
  SKILLS,
  TOOLS,
  get_builtin_skills,
  get_builtin_tools,
  load_builtin_plugin,
)


class TestLoadBuiltinPlugin:
  """Tests for load_builtin_plugin function."""

  def test_load_builtin_plugin_returns_tools(self):
    """Test that load_builtin_plugin returns tools."""
    tools, skills = load_builtin_plugin()

    assert len(tools) > 0
    assert len(skills) == 0  # Built-in skills loaded from config

  def test_load_builtin_plugin_tools_are_instances(self):
    """Test that tools are Tool instances."""
    tools, skills = load_builtin_plugin()

    from yoker.tools import Tool

    for tool in tools:
      assert isinstance(tool, Tool)

  def test_load_builtin_plugin_includes_filesystem_tools(self):
    """Test that built-in includes filesystem tools."""
    tools, skills = load_builtin_plugin()

    tool_names = [t.name for t in tools]

    # Core filesystem tools
    assert "read" in tool_names
    assert "list" in tool_names
    assert "write" in tool_names
    assert "update" in tool_names
    assert "search" in tool_names

  def test_load_builtin_plugin_with_config(self):
    """Test load_builtin_plugin with config parameter."""
    from yoker.config import Config

    config = Config()
    tools, skills = load_builtin_plugin(config)

    assert len(tools) > 0
    assert isinstance(tools, list)

  def test_load_builtin_plugin_empty_skills(self):
    """Test that built-in plugin has no hardcoded skills."""
    tools, skills = load_builtin_plugin()

    assert skills == []
    assert len(skills) == 0


class TestGetBuiltinTools:
  """Tests for get_builtin_tools function."""

  def test_get_builtin_tools_returns_list(self):
    """Test that get_builtin_tools returns a list."""
    tools = get_builtin_tools()

    assert isinstance(tools, list)
    assert len(tools) > 0

  def test_get_builtin_tools_without_config(self):
    """Test get_builtin_tools without config parameter."""
    tools = get_builtin_tools()

    assert len(tools) > 0


class TestGetBuiltinSkills:
  """Tests for get_builtin_skills function."""

  def test_get_builtin_skills_returns_empty_list(self):
    """Test that get_builtin_skills returns empty list."""
    skills = get_builtin_skills()

    assert skills == []


class TestBuiltinExports:
  """Tests for module-level exports."""

  def test_tools_export(self):
    """Test TOOLS export."""
    # TOOLS is initialized as empty list
    assert TOOLS == []

  def test_skills_export(self):
    """Test SKILLS export."""
    # SKILLS is initialized as empty list
    assert SKILLS == []

  def test_agents_export(self):
    """Test AGENTS export."""
    # AGENTS is initialized as empty list
    assert AGENTS == []
