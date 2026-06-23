"""Tests for plugin registration."""

import pytest

from yoker.builtin import list, read
from yoker.plugins.registration import (
  register_skills,
  register_tools,
)
from yoker.skills import Skill, SkillRegistry
from yoker.tools import ToolRegistry


class TestRegisterTools:
  """Tests for register_tools function."""

  def test_register_tools_with_namespace(self):
    """Test tool registration with namespace."""
    registry = ToolRegistry()
    tools = [read]

    registered = register_tools(tools, registry, namespace="pkgq")

    assert len(registered) == 1
    assert "pkgq:read" in registered
    assert registry.get("pkgq:read") is not None

  def test_register_tools_multiple(self):
    """Test registering multiple tools."""
    registry = ToolRegistry()
    tools = [read, list]

    registered = register_tools(tools, registry, namespace="pkgq")

    assert len(registered) == 2
    assert "pkgq:read" in registered
    assert "pkgq:list" in registered

  def test_register_tools_collision(self):
    """Test tool name collision detection."""
    registry = ToolRegistry()
    tools = [read]

    # Register first tool
    register_tools(tools, registry, namespace="pkgq")

    # Try to register same tool again
    with pytest.raises(ValueError, match="already registered"):
      register_tools(tools, registry, namespace="pkgq")

  def test_register_tools_different_namespaces(self):
    """Test registering same tool under different namespaces."""
    registry = ToolRegistry()
    tools = [read]

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
        simple_name="test-skill",
        description="Test skill",
        content="Test content",
        namespace="pkgq",
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
        simple_name="skill1",
        description="Skill 1",
        content="Content 1",
        namespace="pkgq",
      ),
      Skill(
        simple_name="skill2",
        description="Skill 2",
        content="Content 2",
        namespace="pkgq",
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
        simple_name="test-skill",
        description="Test skill",
        content="Test content",
        namespace="pkgq",
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
    skill1 = Skill(
      simple_name="test-skill",
      description="Test skill",
      content="Test content",
      namespace="pkg1",
    )
    skill2 = Skill(
      simple_name="test-skill",
      description="Test skill",
      content="Test content",
      namespace="pkg2",
    )

    # Register under different namespaces
    registered1 = register_skills([skill1], registry, namespace="pkg1")
    registered2 = register_skills([skill2], registry, namespace="pkg2")

    assert len(registered1) == 1
    assert len(registered2) == 1
    assert registry.get("pkg1:test-skill") is not None
    assert registry.get("pkg2:test-skill") is not None


class TestCloneAgentWithName:
  """Tests for _clone_agent_with_name helper."""

  def test_clone_agent_preserves_attributes(self):
    """Test that cloning preserves agent attributes."""
    from yoker.agents import AgentDefinition
    from yoker.plugins.registration import _clone_agent_with_name

    original = AgentDefinition(
      simple_name="test-agent",
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
