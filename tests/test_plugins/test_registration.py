"""Tests for plugin registration via the registry methods.

The standalone ``yoker.plugins.registration`` module was removed in
Batch 2 of the plugin-API cleanup; registration now lives on the
registries themselves. These tests exercise the new entry points:
  - ``ToolRegistry.register_all(specs, namespace)``
  - ``ToolRegistry.register_plugin_tools(plugins, config)``
  - ``SkillRegistry.register_all(skills, namespace)``
  - ``SkillRegistry.register_plugin_skills(plugins)``
  - ``AgentRegistry.register(definition, namespace=...)``

The intent preserved from the previous test suite is: registering
plugin tools/skills/agents via the registry works and namespaces
them correctly, collisions raise ``ValueError``, and the same simple
name can coexist under different namespaces.
"""

import pytest

from yoker.builtin import list, read
from yoker.config import Config
from yoker.plugins import PluginComponents
from yoker.skills import Skill, SkillRegistry
from yoker.tools import ToolRegistry
from yoker.tools.schema import build_tool_spec


def _tool_plugin(source: str, tools: list) -> PluginComponents:
  """Build a PluginComponents carrying pre-built tool specs."""
  return PluginComponents(tools=tools, skills=[], agents=[], source=source)


def _skill_plugin(source: str, skills: list) -> PluginComponents:
  """Build a PluginComponents carrying pre-built skill objects."""
  return PluginComponents(tools=[], skills=skills, agents=[], source=source)


class TestRegisterTools:
  """Tests for tool registration via ToolRegistry."""

  def test_register_tools_with_namespace(self):
    """Tools registered under a namespace are namespaced in the registry."""
    registry = ToolRegistry()
    tools = [build_tool_spec(read, namespace="pkgq")]

    registry.register_all(tools, namespace="pkgq")

    assert len(registry) == 1
    assert "pkgq:read" in registry
    assert registry.get("pkgq:read") is not None

  def test_register_tools_multiple(self):
    """Multiple tools register under the same namespace."""
    registry = ToolRegistry()
    tools = [
      build_tool_spec(read, namespace="pkgq"),
      build_tool_spec(list, namespace="pkgq"),
    ]

    registry.register_all(tools, namespace="pkgq")

    assert len(registry) == 2
    assert "pkgq:read" in registry
    assert "pkgq:list" in registry

  def test_register_tools_collision(self):
    """Registering a duplicate tool name raises ValueError."""
    registry = ToolRegistry()
    tools = [build_tool_spec(read, namespace="pkgq")]

    registry.register_all(tools, namespace="pkgq")

    with pytest.raises(ValueError, match="already registered"):
      registry.register_all(tools, namespace="pkgq")

  def test_register_tools_different_namespaces(self):
    """Same simple name coexists under different namespaces."""
    registry = ToolRegistry()
    tools1 = [build_tool_spec(read, namespace="pkg1")]
    tools2 = [build_tool_spec(read, namespace="pkg2")]

    registry.register_all(tools1, namespace="pkg1")
    registry.register_all(tools2, namespace="pkg2")

    assert len(registry) == 2
    assert registry.get("pkg1:read") is not None
    assert registry.get("pkg2:read") is not None

  def test_register_plugin_tools_consumes_components(self):
    """register_plugin_tools registers namespaced tools from PluginComponents."""
    registry = ToolRegistry()
    config = Config()
    plugin = _tool_plugin(
      "pkgq",
      [build_tool_spec(read, namespace="pkgq")],
    )

    registry.register_plugin_tools([plugin], config)

    assert "pkgq:read" in registry
    assert registry.get("pkgq:read") is not None


class TestRegisterSkills:
  """Tests for skill registration via SkillRegistry."""

  def test_register_skills_with_namespace(self):
    """Skills registered under a namespace are namespaced in the registry."""
    registry = SkillRegistry()
    skills = [
      Skill(
        simple_name="test-skill",
        description="Test skill",
        content="Test content",
        namespace="pkgq",
      )
    ]

    registry.register_all(skills, namespace="pkgq")

    assert len(registry) == 1
    assert "pkgq:test-skill" in registry
    assert registry.get("pkgq:test-skill") is not None

  def test_register_skills_multiple(self):
    """Multiple skills register under the same namespace."""
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

    registry.register_all(skills, namespace="pkgq")

    assert len(registry) == 2
    assert "pkgq:skill1" in registry
    assert "pkgq:skill2" in registry

  def test_register_skills_collision(self):
    """Registering a duplicate skill name raises ValueError."""
    registry = SkillRegistry()
    skills = [
      Skill(
        simple_name="test-skill",
        description="Test skill",
        content="Test content",
        namespace="pkgq",
      )
    ]

    registry.register_all(skills, namespace="pkgq")

    with pytest.raises(ValueError, match="already registered"):
      registry.register_all(skills, namespace="pkgq")

  def test_register_skills_different_namespaces(self):
    """Same simple name coexists under different namespaces."""
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

    registry.register_all([skill1], namespace="pkg1")
    registry.register_all([skill2], namespace="pkg2")

    assert len(registry) == 2
    assert registry.get("pkg1:test-skill") is not None
    assert registry.get("pkg2:test-skill") is not None

  def test_register_plugin_skills_consumes_components(self):
    """register_plugin_skills registers namespaced skills from PluginComponents."""
    registry = SkillRegistry()
    skill = Skill(
      simple_name="test-skill",
      description="Test skill",
      content="Test content",
      namespace="pkgq",
    )
    plugin = _skill_plugin("pkgq", [skill])

    registry.register_plugin_skills([plugin])

    assert "pkgq:test-skill" in registry
    assert registry.get("pkgq:test-skill") is not None


class TestAgentRegistryNamespacing:
  """Tests for AgentRegistry.register namespace assignment.

  Replaces the deleted ``_clone_agent_with_name`` helper test: the
  registry now assigns the namespace in-place on the definition, after
  which ``definition.name`` yields the namespaced name while the other
  attributes (description, model, tools) are preserved.
  """

  def test_register_with_namespace_preserves_attributes(self):
    """Registering under a namespace names the agent and preserves attrs."""
    from yoker.agents import AgentDefinition, AgentRegistry

    original = AgentDefinition(
      simple_name="test-agent",
      description="Test agent",
      model="llama3.2",
      system_prompt="You are a test agent.",
      tools=["read", "write"],
    )
    registry = AgentRegistry()

    registry.register(original, namespace="pkg")

    assert original.name == "pkg:test-agent"
    assert original.description == "Test agent"
    assert original.model == "llama3.2"
    assert original.tools == ["read", "write"]
    assert registry.get("pkg:test-agent") is original
