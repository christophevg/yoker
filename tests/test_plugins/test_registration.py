"""Tests for plugin registration."""

import pytest

from yoker.plugins.registration import (
  register_skills,
  register_tools,
)
from yoker.skills import Skill, SkillRegistry
from yoker.tools import ReadTool, ToolRegistry


class TestRegisterTools:
  """Tests for register_tools function."""

  def test_register_tools_with_namespace(self):
    """Test tool registration with namespace."""
    registry = ToolRegistry()
    tools = [ReadTool()]

    registered = register_tools(tools, registry, namespace="pkgq")

    assert len(registered) == 1
    assert "pkgq:read" in registered
    assert registry.get("pkgq:read") is not None

  def test_register_tools_multiple(self):
    """Test registering multiple tools."""
    from yoker.tools import ListTool

    registry = ToolRegistry()
    tools = [ReadTool(), ListTool()]

    registered = register_tools(tools, registry, namespace="pkgq")

    assert len(registered) == 2
    assert "pkgq:read" in registered
    assert "pkgq:list" in registered

  def test_register_tools_collision(self):
    """Test tool name collision detection."""
    registry = ToolRegistry()
    tools = [ReadTool()]

    # Register first tool
    register_tools(tools, registry, namespace="pkgq")

    # Try to register same tool again
    with pytest.raises(ValueError, match="already registered"):
      register_tools(tools, registry, namespace="pkgq")

  def test_register_tools_different_namespaces(self):
    """Test registering same tool under different namespaces."""
    registry = ToolRegistry()
    tools = [ReadTool()]

    # Register under different namespaces
    registered1 = register_tools(tools, registry, namespace="pkg1")
    registered2 = register_tools(tools, registry, namespace="pkg2")

    assert len(registered1) == 1
    assert len(registered2) == 1
    assert registry.get("pkg1:read") is not None
    assert registry.get("pkg2:read") is not None


class TestRegisterSkills:
  """Tests for register_skills function."""

  def test_register_skills_with_namespace(self):
    """Test skill registration with namespace."""
    registry = SkillRegistry()
    skills = [
      Skill(
        name="test-skill",
        description="Test skill",
        content="Test content",
      )
    ]

    registered = register_skills(skills, registry, namespace="pkgq")

    assert len(registered) == 1
    assert "pkgq:test-skill" in registered
    assert registry.get("pkgq:test-skill") is not None

  def test_register_skills_multiple(self):
    """Test registering multiple skills."""
    registry = SkillRegistry()
    skills = [
      Skill(
        name="skill1",
        description="Skill 1",
        content="Content 1",
      ),
      Skill(
        name="skill2",
        description="Skill 2",
        content="Content 2",
      ),
    ]

    registered = register_skills(skills, registry, namespace="pkgq")

    assert len(registered) == 2
    assert "pkgq:skill1" in registered
    assert "pkgq:skill2" in registered

  def test_register_skills_collision(self):
    """Test skill name collision detection."""
    registry = SkillRegistry()
    skills = [
      Skill(
        name="test-skill",
        description="Test skill",
        content="Test content",
      )
    ]

    # Register first skill
    register_skills(skills, registry, namespace="pkgq")

    # Try to register same skill again
    with pytest.raises(ValueError, match="already registered"):
      register_skills(skills, registry, namespace="pkgq")

  def test_register_skills_different_namespaces(self):
    """Test registering same skill under different namespaces."""
    registry = SkillRegistry()
    skills = [
      Skill(
        name="test-skill",
        description="Test skill",
        content="Test content",
      )
    ]

    # Register under different namespaces
    registered1 = register_skills(skills, registry, namespace="pkg1")
    registered2 = register_skills(skills, registry, namespace="pkg2")

    assert len(registered1) == 1
    assert len(registered2) == 1
    assert registry.get("pkg1:test-skill") is not None
    assert registry.get("pkg2:test-skill") is not None


class TestCloneToolWithName:
  """Tests for _clone_tool_with_name helper."""

  def test_clone_tool_preserves_attributes(self):
    """Test that cloning preserves tool attributes."""
    from yoker.plugins.registration import _clone_tool_with_name

    original = ReadTool()
    cloned = _clone_tool_with_name(original, "new:read")

    assert cloned.name == "new:read"
    # Other attributes should be preserved
    assert cloned.description == original.description


class TestCloneAgentWithName:
  """Tests for _clone_agent_with_name helper."""

  def test_clone_agent_preserves_attributes(self):
    """Test that cloning preserves agent attributes."""
    from yoker.agents import AgentDefinition
    from yoker.plugins.registration import _clone_agent_with_name

    original = AgentDefinition(
      name="test-agent",
      description="Test agent",
      model="llama3.2",
      system_prompt="You are a test agent.",
      tools=("read", "write"),
    )

    cloned = _clone_agent_with_name(original, "pkg:test-agent")

    assert cloned.name == "pkg:test-agent"
    assert cloned.description == original.description
    assert cloned.model == original.model
    assert cloned.tools == original.tools
