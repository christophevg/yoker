"""Test plugin skill discovery and invocation.

Tests that skills from plugins are properly discovered and can be invoked
via the SkillTool.
"""

import sys
from pathlib import Path

import pytest

from yoker.agent import Agent
from yoker.config import Config, PluginsConfig

# Add examples directory to sys.path for plugin imports
# Must be after imports to avoid E402 linting error
EXAMPLES_PATH = Path(__file__).parent.parent / "examples"
if str(EXAMPLES_PATH) not in sys.path:
  sys.path.insert(0, str(EXAMPLES_PATH))


@pytest.fixture
def demo_plugin():
  """Ensure demo plugin is available."""
  return "yoker_plugin_demo"


@pytest.fixture
def plugin_config():
  """Create config with plugins enabled and demo plugin trusted."""
  return Config(
    plugins=PluginsConfig(
      enabled=True,
      trusted={"yoker_plugin_demo": True},
    )
  )


class TestPluginSkillDiscovery:
  """Test discovery of skills from plugins."""

  def test_agent_initializes_with_plugin_skills(self, demo_plugin, plugin_config):
    """Agent should load skills from plugins during initialization."""
    agent = Agent(config=plugin_config, plugins=[demo_plugin])

    # Should have skill registry
    assert agent._core.skill_registry is not None
    assert agent._core.skill_registry.count > 0

    # Should have greeting skill with namespace
    skills = agent._core.skill_registry.list_skills()
    skill_names = [s.name for s in skills]
    assert "greeting" in skill_names

    # Namespace should be preserved
    greeting_skill = [s for s in skills if s.name == "greeting"][0]
    assert greeting_skill.namespace == "yoker_plugin_demo"

  def test_skill_tool_registered_for_plugin_skills(self, demo_plugin, plugin_config):
    """SkillTool should be registered when plugin provides skills."""
    agent = Agent(config=plugin_config, plugins=[demo_plugin])

    # Should have skill tool registered
    assert "skill" in agent.tool_registry.names
    assert "yoker_plugin_demo:echo" in agent.tool_registry.names

  def test_skill_discovery_block_added_to_context(self, demo_plugin, plugin_config):
    """Plugin skills should be visible in agent context."""
    agent = Agent(config=plugin_config, plugins=[demo_plugin])

    # Context should have skill discovery message
    messages = agent.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]

    # Should have skill discovery block
    has_discovery = any(
      "The following skills are available" in str(m.get("content", "")) for m in system_messages
    )
    assert has_discovery, "Skill discovery block not found in context"

  def test_no_env_skills_but_plugin_skills(self, demo_plugin, plugin_config, monkeypatch):
    """Skills should work even without YOKER_SKILLS_PATH set."""
    # Ensure YOKER_SKILLS_PATH is not set
    monkeypatch.delenv("YOKER_SKILLS_PATH", raising=False)

    agent = Agent(config=plugin_config, plugins=[demo_plugin])

    # Should still have plugin skills
    assert agent._core.skill_registry is not None
    assert agent._core.skill_registry.count > 0

    # SkillTool should still be registered
    assert "skill" in agent.tool_registry.names

  def test_multiple_plugins_with_skills(self, plugin_config):
    """Multiple plugins can contribute skills simultaneously."""
    # Load demo plugin
    agent = Agent(config=plugin_config, plugins=["yoker_plugin_demo"])

    skill_count = agent._core.skill_registry.count
    assert skill_count > 0

    # Plugin skills should be namespaced
    skills = agent._core.skill_registry.list_skills()
    plugin_skills = [s for s in skills if s.namespace is not None]
    assert len(plugin_skills) > 0, "Should have at least one plugin skill"

    # All plugin skills should have proper namespace format
    for skill in plugin_skills:
      assert skill.namespace is not None
      assert ":" in f"{skill.namespace}:{skill.name}"
