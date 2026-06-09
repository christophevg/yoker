"""Tests for the demo plugin.

Validates that the demo plugin can be discovered, loaded, and its components
registered correctly.
"""

import sys
from pathlib import Path

import pytest

# Add examples/plugins to sys.path for testing
EXAMPLES_PATH = Path(__file__).parent.parent / "examples" / "plugins"
if str(EXAMPLES_PATH) not in sys.path:
  sys.path.insert(0, str(EXAMPLES_PATH))


class TestDemoPluginDiscovery:
  """Test plugin discovery."""

  def test_demo_plugin_can_be_imported(self) -> None:
    """Demo plugin package should be importable."""
    import demo

    assert hasattr(demo, "__YOKER_MANIFEST__")

  def test_demo_plugin_yoker_submodule_can_be_imported(self) -> None:
    """Demo plugin yoker submodule should be importable."""
    import demo.yoker

    assert hasattr(demo.yoker, "__YOKER_MANIFEST__")
    assert hasattr(demo.yoker, "EchoTool")


class TestDemoPluginManifest:
  """Test plugin manifest declaration."""

  def test_manifest_has_echo_tool(self) -> None:
    """Manifest should declare EchoTool."""
    from demo.yoker import __YOKER_MANIFEST__

    assert len(__YOKER_MANIFEST__.tools) == 1
    tool = __YOKER_MANIFEST__.tools[0]
    assert tool.name == "echo"

  def test_manifest_declares_skills_dir(self) -> None:
    """Manifest should declare skills directory."""
    from demo.yoker import __YOKER_MANIFEST__

    assert __YOKER_MANIFEST__.skills_dir == "skills"

  def test_manifest_declares_agents_dir(self) -> None:
    """Manifest should declare agents directory."""
    from demo.yoker import __YOKER_MANIFEST__

    assert __YOKER_MANIFEST__.agents_dir == "agents"


class TestEchoTool:
  """Test EchoTool implementation."""

  @pytest.mark.asyncio
  async def test_echo_tool_returns_input_with_prefix(self) -> None:
    """EchoTool should return input message with 'Echo: ' prefix."""
    from demo.yoker import EchoTool

    tool = EchoTool()
    result = await tool.execute(message="Hello, World!")

    assert result.success
    assert result.result == "Echo: Hello, World!"

  @pytest.mark.asyncio
  async def test_echo_tool_handles_empty_string(self) -> None:
    """EchoTool should handle empty string input."""
    from demo.yoker import EchoTool

    tool = EchoTool()
    result = await tool.execute(message="")

    assert result.success
    assert result.result == "Echo: "

  @pytest.mark.asyncio
  async def test_echo_tool_rejects_non_string(self) -> None:
    """EchoTool should reject non-string input."""
    from demo.yoker import EchoTool

    tool = EchoTool()
    result = await tool.execute(message=123)

    assert not result.success
    assert result.error is not None
    assert "must be a string" in result.error

  def test_echo_tool_has_correct_name(self) -> None:
    """EchoTool should have 'echo' as its name."""
    from demo.yoker import EchoTool

    tool = EchoTool()
    assert tool.name == "echo"

  def test_echo_tool_has_description(self) -> None:
    """EchoTool should have a description."""
    from demo.yoker import EchoTool

    tool = EchoTool()
    assert tool.description != ""

  def test_echo_tool_has_valid_schema(self) -> None:
    """EchoTool should have a valid OpenAI function schema."""
    from demo.yoker import EchoTool

    tool = EchoTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert "message" in schema["function"]["parameters"]["properties"]
    assert "message" in schema["function"]["parameters"]["required"]


class TestDemoPluginLoading:
  """Test plugin loading through the plugin system."""

  def test_load_demo_plugin(self) -> None:
    """Demo plugin should be loadable via load_plugin()."""
    from yoker.plugins import load_plugin

    plugin = load_plugin("demo")

    assert plugin is not None
    assert plugin.source == "demo"
    assert len(plugin.tools) == 1
    assert plugin.tools[0].name == "echo"

  def test_load_demo_plugin_skills(self) -> None:
    """Demo plugin should provide skills from skills directory."""
    from yoker.plugins import load_skills_from_package

    skills = load_skills_from_package("demo", skills_dir="skills")

    # Should load at least the greeting skill
    assert len(skills) >= 1
    greeting_skill = next((s for s in skills if s.name == "greeting"), None)
    assert greeting_skill is not None
    assert greeting_skill.namespace == "demo"
    assert greeting_skill.full_name == "demo:greeting"

  def test_load_demo_plugin_agents(self) -> None:
    """Demo plugin should provide agents from agents directory."""
    from yoker.plugins import load_agents_from_package

    agents = load_agents_from_package("demo", agents_dir="agents")

    # Should load at least the demo agent
    assert len(agents) >= 1
    demo_agent = next((a for a in agents if "demo" in a.name), None)
    assert demo_agent is not None
    # Agent name should be namespaced
    assert ":" in demo_agent.name


class TestDemoPluginRegistration:
  """Test plugin registration with registries."""

  def test_register_demo_tool_with_namespace(self) -> None:
    """Demo tool should be registerable with namespace prefix."""
    from yoker.plugins import load_plugin, register_tools
    from yoker.tools import ToolRegistry

    plugin = load_plugin("demo")
    assert plugin is not None

    registry = ToolRegistry()
    registered = register_tools(plugin.tools, registry, namespace="demo")

    assert len(registered) == 1
    assert "demo:echo" in registered
    assert registry.get("demo:echo") is not None

  def test_register_demo_skill_with_namespace(self) -> None:
    """Demo skill should be registerable with namespace prefix."""
    from yoker.plugins import load_skills_from_package, register_skills
    from yoker.skills import SkillRegistry

    skills = load_skills_from_package("demo", skills_dir="skills")

    registry = SkillRegistry()
    registered = register_skills(skills, registry, namespace="demo")

    assert len(registered) >= 1
    assert "demo:greeting" in registered
    assert registry.get("demo:greeting") is not None


class TestDemoPluginIntegration:
  """Test end-to-end plugin loading with skill discovery."""

  def test_load_plugin_discovers_skills_from_directory(self) -> None:
    """load_plugin should discover skills from skills_dir declared in manifest."""
    from yoker.plugins import load_plugin

    plugin = load_plugin("demo")

    assert plugin is not None
    # Plugin should have loaded skills from skills/ directory
    # (not just the empty SKILLS list in __init__.py)
    assert len(plugin.skills) >= 1, (
      f"Plugin should have loaded skills from skills/ directory, "
      f"but got {len(plugin.skills)} skills. "
      f"load_plugin should check __YOKER_MANIFEST__ and call load_skills_from_package"
    )

    greeting_skill = next((s for s in plugin.skills if s.name == "greeting"), None)
    assert greeting_skill is not None, (
      "greeting skill should be loaded from skills/greeting/SKILL.md"
    )
    assert greeting_skill.namespace == "demo"

  def test_load_plugin_discovers_agents_from_directory(self) -> None:
    """load_plugin should discover agents from agents_dir declared in manifest."""
    from yoker.plugins import load_plugin

    plugin = load_plugin("demo")

    assert plugin is not None
    # Plugin should have loaded agents from agents/ directory
    assert len(plugin.agents) >= 1, (
      f"Plugin should have loaded agents from agents/ directory, "
      f"but got {len(plugin.agents)} agents. "
      f"load_plugin should check __YOKER_MANIFEST__ and call load_agents_from_package"
    )
