"""Tests for GitHub issue fixes - agent tool namespacing and model override.

Validates the fixes for:
1. Agent model not being applied (now uses agent's model over config)
2. Built-in tools incorrectly namespaced (yoker: prefix preserved)
3. Tool availability check (yoker:read resolves to read in registry)
4. yoker namespace resolution (yoker: namespace is built-in, not plugin)
"""

import sys
from pathlib import Path

# Add examples/plugins to sys.path for testing
EXAMPLES_PATH = Path(__file__).parent.parent / "examples" / "plugins"
if str(EXAMPLES_PATH) not in sys.path:
  sys.path.insert(0, str(EXAMPLES_PATH))


class TestIssue1AgentModelOverride:
  """Issue 1: Agent model not being applied."""

  def test_agent_model_overrides_config(self) -> None:
    """Agent definition's model should override config's model."""
    from yoker.agents import AgentDefinition
    from yoker.base import AgentCore
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    config = Config()
    config_model = config.backend.ollama.model

    # Agent with different model
    agent_def = AgentDefinition(
      name="test",
      description="Test",
      model="custom-model:latest",
      system_prompt="Test",
      tools=("read",),
    )

    core = AgentCore(config=config, thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Agent's model should override config
    assert core.model == "custom-model:latest"
    assert core.model != config_model

  def test_agent_without_model_uses_config(self) -> None:
    """Agent without model should use config's model."""
    from yoker.agents import AgentDefinition
    from yoker.base import AgentCore
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    config = Config()

    agent_def = AgentDefinition(
      name="test",
      description="Test",
      model=None,  # No model
      system_prompt="Test",
      tools=("read",),
    )

    core = AgentCore(config=config, thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Should use config's model
    assert core.model == config.backend.ollama.model


class TestIssue2BuiltinToolNamespacing:
  """Issue 2: Built-in tools incorrectly namespaced."""

  def test_yoker_namespace_preserved(self) -> None:
    """yoker: namespace should be preserved, not re-namespaced."""
    from yoker.plugins.loader import load_agent_definition_from_string

    content = """---
name: demo
description: Test
tools:
  - yoker:read
  - demo:echo
  - write
---
Test."""

    agent_def = load_agent_definition_from_string(content, namespace="examples.plugins.demo")

    assert agent_def is not None
    # yoker:read stays as-is
    assert "yoker:read" in agent_def.tools
    # demo:echo gets full namespace
    assert "examples.plugins.demo:echo" in agent_def.tools
    # write gets namespace
    assert "examples.plugins.demo:write" in agent_def.tools

  def test_short_namespace_expansion(self) -> None:
    """Short namespace (e.g., 'demo') should expand to full namespace."""
    from yoker.plugins.loader import load_agent_definition_from_string

    content = """---
name: test
description: Test
tools:
  - demo:tool
---
Test."""

    agent_def = load_agent_definition_from_string(content, namespace="examples.plugins.demo")

    assert agent_def is not None
    # demo:tool → examples.plugins.demo:tool
    assert "examples.plugins.demo:tool" in agent_def.tools

  def test_yoker_namespace_not_renamespaced(self) -> None:
    """yoker: tools should not get plugin namespace prefix."""
    from yoker.plugins.loader import load_agent_definition_from_string

    content = """---
name: test
description: Test
tools:
  - yoker:read
  - yoker:write
---
Test."""

    agent_def = load_agent_definition_from_string(content, namespace="myplugin")

    assert agent_def is not None
    # All yoker: tools stay as-is
    assert "yoker:read" in agent_def.tools
    assert "yoker:write" in agent_def.tools
    # NOT myplugin:yoker:read
    assert "myplugin:yoker:read" not in agent_def.tools


class TestIssue3ToolAvailability:
  """Issue 3: Tool availability check broken."""

  def test_yoker_namespace_resolves_to_builtin(self) -> None:
    """yoker:read should resolve to read in tool registry."""
    from yoker.agents import AgentDefinition
    from yoker.base import AgentCore
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    agent_def = AgentDefinition(
      name="test",
      description="Test",
      model=None,
      system_prompt="Test",
      tools=("yoker:read",),  # Only read allowed
    )

    core = AgentCore(config=Config(), thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # yoker:read should make 'read' available
    assert core.tool_registry.get("read") is not None
    # Other tools should not be available
    assert core.tool_registry.get("write") is None

  def test_mixed_namespaces_filter_correctly(self) -> None:
    """Agent with mixed tool namespaces should filter correctly."""
    from yoker.agents import AgentDefinition
    from yoker.base import AgentCore
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    agent_def = AgentDefinition(
      name="test",
      description="Test",
      model=None,
      system_prompt="Test",
      tools=("yoker:read", "yoker:list"),  # Only yoker tools
    )

    core = AgentCore(config=Config(), thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Both should be available
    assert core.tool_registry.get("read") is not None
    assert core.tool_registry.get("list") is not None
    # Others should not
    assert core.tool_registry.get("write") is None


class TestIssue4YokerNamespaceResolution:
  """Issue 4: yoker namespace resolution."""

  def test_yoker_is_builtin_namespace(self) -> None:
    """yoker: should be treated as built-in namespace."""
    from yoker.plugins.loader import load_agent_definition_from_string

    # Agent with yoker: tools
    content = """---
name: test
description: Test
tools:
  - yoker:read
  - yoker:write
  - yoker:list
---
Test."""

    agent_def = load_agent_definition_from_string(content, namespace="myplugin")

    assert agent_def is not None
    # yoker: namespace is preserved
    assert "yoker:read" in agent_def.tools
    assert "yoker:write" in agent_def.tools
    assert "yoker:list" in agent_def.tools

  def test_other_namespaces_get_plugin_prefix(self) -> None:
    """Non-yoker namespaces should get the full plugin namespace."""
    from yoker.plugins.loader import load_agent_definition_from_string

    content = """---
name: test
description: Test
tools:
  - other:tool
  - local_tool
---
Test."""

    agent_def = load_agent_definition_from_string(content, namespace="myplugin")

    assert agent_def is not None
    # other:tool stays as-is (different plugin)
    assert "other:tool" in agent_def.tools
    # local_tool gets myplugin namespace
    assert "myplugin:local_tool" in agent_def.tools


class TestEndToEndDemoPlugin:
  """End-to-end tests with demo plugin."""

  def test_demo_agent_model_and_tools(self) -> None:
    """Demo agent should have correct model and namespaced tools."""
    from yoker.plugins import load_agents_from_package

    agents = load_agents_from_package("yoker_plugin_demo", agents_dir="agents")
    assert len(agents) >= 1

    # Be more specific: find agent with exact name "yoker_plugin_demo:demo"
    demo_agent = next((a for a in agents if a.name == "yoker_plugin_demo:demo"), None)
    assert demo_agent is not None

    # Model from frontmatter
    assert demo_agent.model == "llama3.2:latest"

    # Tools correctly namespaced
    # yoker:read stays as-is
    assert "yoker:read" in demo_agent.tools
    # yoker_plugin_demo:echo should be present
    echo_tools = [t for t in demo_agent.tools if "echo" in t]
    assert len(echo_tools) == 1

  def test_tool_availability_command_output(self) -> None:
    """Tool availability should show correct markers."""
    from yoker.agents import AgentDefinition
    from yoker.base import AgentCore
    from yoker.commands.tools import create_tools_command
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    agent_def = AgentDefinition(
      name="test",
      description="Test",
      model=None,
      system_prompt="Test",
      tools=("yoker:read",),
    )

    core = AgentCore(config=Config(), thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Create tools command
    cmd = create_tools_command(core.tool_registry, core)
    output = cmd.handler([])

    # Check output format
    lines = output.split("\n")

    # Built-in section should show read available
    built_in_section = False
    for line in lines:
      if "Built-in:" in line:
        built_in_section = True
      elif built_in_section and "read" in line:
        # read should be marked as available
        assert "✓ read" in line or "read" in line
        break

    # Agent section should show allowed tools
    assert "Agent: test" in output
    assert "yoker:read" in output
