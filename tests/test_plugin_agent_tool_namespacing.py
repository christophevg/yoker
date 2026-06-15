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
    from yoker.agent.core import AgentCore
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    # Create config with a specific model
    config = Config()
    config_model = config.backend.ollama.model

    # Create agent definition with different model
    agent_def = AgentDefinition(
      name="test-agent",
      description="Test agent",
      model="custom-model:latest",
      system_prompt="You are a test agent.",
      tools=("read", "write"),
    )

    # Create AgentCore with agent definition
    core = AgentCore(
      config=config,
      thinking_mode=ThinkingMode.ON,
      agent_definition=agent_def,
    )

    # Agent definition's model should override config
    assert core.model == "custom-model:latest"
    assert core.model != config_model

  def test_agent_without_model_uses_config(self, tmp_path: Path) -> None:
    """Agent without model should use config's model."""
    from yoker.agent.core import AgentCore
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    config = Config()
    config_model = config.backend.ollama.model

    # Agent definition without model
    agent_def = AgentDefinition(
      name="test-agent",
      description="Test agent",
      model=None,  # No model specified
      system_prompt="You are a test agent.",
      tools=("read", "write"),
    )

    core = AgentCore(
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
    from yoker.plugins.loader import load_agent_definition_from_string

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

    agent_def = load_agent_definition_from_string(content, namespace="examples.plugins.demo")

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
    from yoker.plugins.loader import load_agent_definition_from_string

    content = """---
name: demo
description: Test agent
tools:
  - yoker:read
  - yoker:write
  - yoker:list
---
System prompt here."""

    agent_def = load_agent_definition_from_string(content, namespace="demo")

    assert agent_def is not None
    # All yoker: tools should stay as yoker:
    assert "yoker:read" in agent_def.tools
    assert "yoker:write" in agent_def.tools
    assert "yoker:list" in agent_def.tools
    # Should NOT have demo: prefix
    assert "demo:yoker:read" not in agent_def.tools

  def test_mixed_namespace_tools(self) -> None:
    """Agent with tools from multiple namespaces should handle each correctly."""
    from yoker.plugins.loader import load_agent_definition_from_string

    content = """---
name: demo
description: Test agent
tools:
  - yoker:read
  - otherplugin:tool
  - local_tool
---
System prompt here."""

    agent_def = load_agent_definition_from_string(content, namespace="demo")

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
    from yoker.agent.core import AgentCore
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    agent_def = AgentDefinition(
      name="test-agent",
      description="Test agent",
      model=None,
      system_prompt="You are a test agent.",
      tools=("yoker:read",),  # Only read tool allowed
    )

    core = AgentCore(
      config=Config(),
      thinking_mode=ThinkingMode.ON,
      agent_definition=agent_def,
    )

    # Check which tools are registered
    registry = core.tool_registry

    # Only 'read' should be available (yoker:read resolves to read)
    # The registry filters based on allowed tools
    assert registry.get("read") is not None
    # Other tools should not be registered
    assert registry.get("write") is None
    assert registry.get("list") is None

  def test_tool_availability_without_agent(self) -> None:
    """All tools should be available when no agent definition is loaded."""
    from yoker.agent.core import AgentCore
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    core = AgentCore(
      config=Config(),
      thinking_mode=ThinkingMode.ON,
      agent_definition=None,  # No agent
    )

    # All tools should be available
    registry = core.tool_registry
    assert registry.get("read") is not None
    assert registry.get("write") is not None
    assert registry.get("list") is not None


class TestDemoAgentIntegration:
  """Integration tests with demo plugin agent."""

  def test_demo_agent_loads_with_correct_model(self) -> None:
    """Demo agent should have model from agent definition."""
    from yoker.plugins import load_agents_from_package

    agents = load_agents_from_package("yoker_plugin_demo", agents_dir="agents")

    assert len(agents) >= 1
    # Be more specific: find agent with exact name "yoker_plugin_demo:demo"
    demo_agent = next((a for a in agents if a.name == "yoker_plugin_demo:demo"), None)
    assert demo_agent is not None

    # Agent definition should have the model from frontmatter
    assert demo_agent.model == "llama3.2:latest"

  def test_demo_agent_tool_namespacing(self) -> None:
    """Demo agent tools should be namespaced correctly."""
    from yoker.plugins import load_agents_from_package

    agents = load_agents_from_package("yoker_plugin_demo", agents_dir="agents")

    # Be more specific: find agent with exact name "yoker_plugin_demo:demo"
    demo_agent = next((a for a in agents if a.name == "yoker_plugin_demo:demo"), None)
    assert demo_agent is not None

    # yoker:read should stay as yoker:read
    assert "yoker:read" in demo_agent.tools
    # yoker_plugin_demo:echo should be present
    echo_tools = [t for t in demo_agent.tools if "echo" in t]
    assert len(echo_tools) == 1
    # Should NOT have double namespacing like "yoker_plugin_demo:yoker_plugin_demo:echo"
    assert "yoker_plugin_demo:yoker_plugin_demo:echo" not in demo_agent.tools
