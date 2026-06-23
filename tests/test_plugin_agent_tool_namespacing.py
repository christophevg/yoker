"""Tests for plugin agent tool namespacing issues.

Validates the fixes for:
1. Agent model not being applied
2. Built-in tools incorrectly namespaced
3. Tool availability check broken
4. yoker namespace resolution
"""

import sys
from pathlib import Path

# Add examples/plugins to sys.path for testing
EXAMPLES_PATH = Path(__file__).parent.parent / "examples" / "plugins"
if str(EXAMPLES_PATH) not in sys.path:
  sys.path.insert(0, str(EXAMPLES_PATH))


class TestAgentModelOverride:
  """Test that agent definition's model overrides config model."""

  def test_agent_model_overrides_config(self, tmp_path: Path) -> None:
    """Agent definition's model should override config's model."""
    from yoker.agent import Agent
    from yoker.agent.thinking import ThinkingMode
    from yoker.agents import AgentDefinition
    from yoker.config import Config

    # Create config with a specific model
    config = Config()
    config_model = config.backend.ollama.model

    # Create agent definition with different model
    agent_def = AgentDefinition(
      simple_name="test-agent",
      description="Test agent",
      model="custom-model:latest",
      system_prompt="You are a test agent.",
      tools=("read", "write"),
    )

    # Create Agent with agent definition
    core = Agent(
      config=config,
      thinking_mode=ThinkingMode.ON,
      agent_definition=agent_def,
    )

    # Agent definition's model should override config
    assert core.model == "custom-model:latest"
    assert core.model != config_model

  def test_agent_without_model_uses_config(self, tmp_path: Path) -> None:
    """Agent without model should use config's model."""
    from yoker.agent import Agent
    from yoker.agent.thinking import ThinkingMode
    from yoker.agents import AgentDefinition
    from yoker.config import Config

    config = Config()
    config_model = config.backend.ollama.model

    # Agent definition without model
    agent_def = AgentDefinition(
      simple_name="test-agent",
      description="Test agent",
      model=None,  # No model specified
      system_prompt="You are a test agent.",
      tools=("read", "write"),
    )

    core = Agent(
      config=config,
      thinking_mode=ThinkingMode.ON,
      agent_definition=agent_def,
    )

    # Should use config's model
    assert core.model == config_model


class TestToolNamespacing:
  """Test that tool namespacing preserves built-in yoker namespace."""

  def test_yoker_namespace_preserved(self) -> None:
    """yoker: namespace should be preserved, not re-namespaced."""
    from yoker.agents.loader import parse_agent_definition
    from yoker.resources import parse_yaml_frontmatter

    content = """---
name: demo
description: Test agent
model: llama3.2:latest
tools:
  - yoker:read
  - demo:echo
  - write
---
System prompt here."""

    frontmatter, body = parse_yaml_frontmatter(content)
    agent_def = parse_agent_definition(
      frontmatter, body, source_path="test.md", namespace="examples.plugins.demo"
    )

    assert agent_def is not None
    assert agent_def.name == "examples.plugins.demo:demo"
    # yoker:read should stay as yoker:read
    assert "yoker:read" in agent_def.tools
    # demo:echo should become examples.plugins.demo:echo
    assert "examples.plugins.demo:echo" in agent_def.tools
    # write should get namespace
    assert "examples.plugins.demo:write" in agent_def.tools

  def test_builtin_yoker_tools_not_renamespaced(self) -> None:
    """Built-in yoker: tools should not be re-namespaced with plugin prefix."""
    from yoker.agents.loader import parse_agent_definition
    from yoker.resources import parse_yaml_frontmatter

    content = """---
name: demo
description: Test agent
tools:
  - yoker:read
  - yoker:write
  - yoker:list
---
System prompt here."""

    frontmatter, body = parse_yaml_frontmatter(content)
    agent_def = parse_agent_definition(frontmatter, body, source_path="test.md", namespace="demo")

    assert agent_def is not None
    # All yoker: tools should stay as yoker:
    assert "yoker:read" in agent_def.tools
    assert "yoker:write" in agent_def.tools
    assert "yoker:list" in agent_def.tools
    # Should NOT have demo: prefix
    assert "demo:yoker:read" not in agent_def.tools

  def test_mixed_namespace_tools(self) -> None:
    """Agent with tools from multiple namespaces should handle each correctly."""
    from yoker.agents.loader import parse_agent_definition
    from yoker.resources import parse_yaml_frontmatter

    content = """---
name: demo
description: Test agent
tools:
  - yoker:read
  - otherplugin:tool
  - local_tool
---
System prompt here."""

    frontmatter, body = parse_yaml_frontmatter(content)
    agent_def = parse_agent_definition(frontmatter, body, source_path="test.md", namespace="demo")

    assert agent_def is not None
    # yoker:read stays as-is
    assert "yoker:read" in agent_def.tools
    # otherplugin:tool stays as-is (already namespaced)
    assert "otherplugin:tool" in agent_def.tools
    # local_tool gets demo: namespace
    assert "demo:local_tool" in agent_def.tools


class TestToolAvailability:
  """Test that tool availability checks work correctly."""

  def test_tool_availability_with_agent_definition(self) -> None:
    """Tools should only show as available if in agent's allowed tools."""
    from yoker.agent import Agent
    from yoker.agent.thinking import ThinkingMode
    from yoker.agents import AgentDefinition
    from yoker.config import Config

    agent_def = AgentDefinition(
      simple_name="test-agent",
      description="Test agent",
      model=None,
      system_prompt="You are a test agent.",
      tools=("yoker:read",),  # Only read tool allowed
    )

    core = Agent(
      config=Config(),
      thinking_mode=ThinkingMode.ON,
      agent_definition=agent_def,
    )

    # Check which tools are registered
    # When an agent definition specifies tools, only those tools are registered.
    # The definition.tools filters the available tools.
    registry = core.tools

    # yoker:read should be registered (it's in the agent's tools list)
    assert registry.get("yoker:read") is not None
    # Other yoker tools should NOT be registered (not in agent's tools list)
    assert registry.get("yoker:write") is None
    assert registry.get("yoker:list") is None

  def test_tool_availability_without_agent(self) -> None:
    """All tools should be available when no agent definition is loaded."""
    from yoker.agent import Agent
    from yoker.agent.thinking import ThinkingMode
    from yoker.config import Config

    core = Agent(
      config=Config(),
      thinking_mode=ThinkingMode.ON,
      agent_definition=None,  # No agent
    )

    # All builtin yoker tools should be available
    registry = core.tools
    assert registry.get("yoker:read") is not None
    assert registry.get("yoker:write") is not None
    assert registry.get("yoker:list") is not None


class TestDemoAgentIntegration:
  """Integration tests with demo plugin agent."""

  def test_demo_agent_loads_with_correct_model(self) -> None:
    """Demo agent should have model from agent definition."""
    from yoker.plugins import load_plugin

    plugin = load_plugin("yoker_plugin_demo")

    agents = plugin.agents
    assert len(agents) >= 1
    # Be more specific: find agent with exact name "yoker_plugin_demo:demo"
    demo_agent = next((a for a in agents if a.name == "yoker_plugin_demo:demo"), None)
    assert demo_agent is not None

    # Agent definition should have the model from frontmatter
    assert demo_agent.model == "llama3.2:latest"

  def test_demo_agent_tool_namespacing(self) -> None:
    """Demo agent tools should be namespaced correctly."""
    from yoker.plugins import load_plugin

    plugin = load_plugin("yoker_plugin_demo")

    agents = plugin.agents

    # Be more specific: find agent with exact name "yoker_plugin_demo:demo"
    demo_agent = next((a for a in agents if a.name == "yoker_plugin_demo:demo"), None)
    assert demo_agent is not None

    # Tools without namespace prefix in the agent.md get the plugin namespace
    assert "yoker_plugin_demo:read" in demo_agent.tools
    # yoker_plugin_demo:echo should be present
    echo_tools = [t for t in demo_agent.tools if "echo" in t]
    assert len(echo_tools) == 1
    # Should NOT have double namespacing like "yoker_plugin_demo:yoker_plugin_demo:echo"
    assert "yoker_plugin_demo:yoker_plugin_demo:echo" not in demo_agent.tools
