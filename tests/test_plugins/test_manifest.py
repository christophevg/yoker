"""Tests for plugin manifest."""

from yoker.builtin import read
from yoker.plugins.manifest import PluginManifest
from yoker.tools.schema import build_tool_spec


class TestPluginManifest:
  """Tests for PluginManifest dataclass."""

  def test_manifest_creation_with_defaults(self):
    """Test creating a manifest with default values."""
    manifest = PluginManifest()

    assert manifest.tools == []
    assert manifest.skills == []
    assert manifest.agents == []
    assert manifest.config_class is None
    assert manifest.skills_dir == "skills"
    assert manifest.agents_dir == "agents"

  def test_manifest_creation_with_tools(self):
    """Test creating a manifest with tools."""
    tools = [read]
    manifest = PluginManifest(tools=tools)

    assert len(manifest.tools) == 1
    spec = build_tool_spec(manifest.tools[0])
    assert spec.name == "read"

  def test_manifest_creation_with_skills(self):
    """Test creating a manifest with skills."""
    from yoker.skills import Skill

    skills = [
      Skill(
        name="test-skill",
        description="Test skill",
        content="Test content",
      )
    ]
    manifest = PluginManifest(skills=skills)

    assert len(manifest.skills) == 1
    assert manifest.skills[0].name == "test-skill"

  def test_manifest_with_config_class(self):
    """Test creating a manifest with config class."""

    class MyConfig:
      option1: str = "value1"
      option2: int = 42

    manifest = PluginManifest(config_class=MyConfig)

    assert manifest.config_class is MyConfig
    assert manifest.config_class.option1 == "value1"
    assert manifest.config_class.option2 == 42

  def test_manifest_with_custom_dirs(self):
    """Test creating a manifest with custom skill/agent directories."""
    manifest = PluginManifest(
      skills_dir="custom_skills",
      agents_dir="custom_agents",
    )

    assert manifest.skills_dir == "custom_skills"
    assert manifest.agents_dir == "custom_agents"

  def test_manifest_frozen(self):
    """Test that manifest is not frozen (can modify lists)."""
    manifest = PluginManifest()
    manifest.tools.append(read)

    assert len(manifest.tools) == 1
