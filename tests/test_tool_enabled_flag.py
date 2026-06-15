"""Tests for tool enabled flag enforcement."""

import pytest

from yoker.agent.core import AgentCore
from yoker.config import (
  Config,
  ExistenceToolConfig,
  GitToolConfig,
  ListToolConfig,
  MkdirToolConfig,
  ReadToolConfig,
  SearchToolConfig,
  ToolsConfig,
  UpdateToolConfig,
  WebFetchToolConfig,
  WebSearchToolConfig,
  WriteToolConfig,
)


class TestToolEnabledFlag:
  """Tests for tool enabled flag enforcement."""

  def test_read_tool_disabled(self) -> None:
    """Test that read tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(read=ReadToolConfig(enabled=False)))
    core = AgentCore(config=config)

    # read tool should not be in registry
    assert core.tool_registry.get("read") is None
    # Other tools should still be available
    assert core.tool_registry.get("list") is not None

  def test_list_tool_disabled(self) -> None:
    """Test that list tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(list=ListToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("list") is None
    assert core.tool_registry.get("read") is not None

  def test_write_tool_disabled(self) -> None:
    """Test that write tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(write=WriteToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("write") is None
    assert core.tool_registry.get("read") is not None

  def test_update_tool_disabled(self) -> None:
    """Test that update tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("update") is None
    assert core.tool_registry.get("read") is not None

  def test_search_tool_disabled(self) -> None:
    """Test that search tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(search=SearchToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("search") is None
    assert core.tool_registry.get("read") is not None

  def test_mkdir_tool_disabled(self) -> None:
    """Test that mkdir tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(mkdir=MkdirToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("mkdir") is None
    assert core.tool_registry.get("read") is not None

  def test_existence_tool_disabled(self) -> None:
    """Test that existence tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(existence=ExistenceToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("existence") is None
    assert core.tool_registry.get("read") is not None

  def test_git_tool_disabled(self) -> None:
    """Test that git tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(git=GitToolConfig(enabled=False)))
    core = AgentCore(config=config)

    assert core.tool_registry.get("git") is None
    assert core.tool_registry.get("read") is not None

  def test_multiple_tools_disabled(self) -> None:
    """Test that multiple tools can be disabled at once."""
    config = Config(
      tools=ToolsConfig(
        read=ReadToolConfig(enabled=False),
        write=WriteToolConfig(enabled=False),
        update=UpdateToolConfig(enabled=False),
      )
    )
    core = AgentCore(config=config)

    assert core.tool_registry.get("read") is None
    assert core.tool_registry.get("write") is None
    assert core.tool_registry.get("update") is None
    # Other tools should still be available
    assert core.tool_registry.get("list") is not None
    assert core.tool_registry.get("search") is not None

  def test_all_tools_enabled_by_default(self) -> None:
    """Test that all tools are enabled by default."""
    config = Config()
    core = AgentCore(config=config)

    # All default tools should be present
    assert core.tool_registry.get("read") is not None
    assert core.tool_registry.get("list") is not None
    assert core.tool_registry.get("write") is not None
    assert core.tool_registry.get("update") is not None
    assert core.tool_registry.get("search") is not None
    assert core.tool_registry.get("existence") is not None
    assert core.tool_registry.get("mkdir") is not None


class TestGetKnownToolsEnabledFlag:
  """Tests for get_known_tools() respecting enabled flag."""

  def test_get_known_tools_excludes_disabled_tools(self) -> None:
    """Test that get_known_tools() excludes disabled tools."""
    config = Config(
      tools=ToolsConfig(
        read=ReadToolConfig(enabled=False),
        write=WriteToolConfig(enabled=False),
      )
    )
    core = AgentCore(config=config)

    known_tools = core.get_known_tools()
    tool_names = {t.name for t in known_tools}

    # read and write should not be in known tools
    assert "read" not in tool_names
    assert "write" not in tool_names
    # Other tools should be present
    assert "list" in tool_names
    assert "search" in tool_names

  def test_get_known_tools_includes_enabled_tools(self) -> None:
    """Test that get_known_tools() includes enabled tools."""
    config = Config()
    core = AgentCore(config=config)

    known_tools = core.get_known_tools()
    tool_names = {t.name for t in known_tools}

    # All default tools should be present
    assert "read" in tool_names
    assert "list" in tool_names
    assert "write" in tool_names
    assert "update" in tool_names
    assert "search" in tool_names
    assert "existence" in tool_names
    assert "mkdir" in tool_names


class TestAgentDefinitionAndEnabledFlag:
  """Tests for agent definition tool list AND enabled flag working together."""

  def test_agent_definition_respects_enabled_flag(self) -> None:
    """Test that agent definition filtering still respects enabled flag."""
    from yoker.agents import AgentDefinition

    # Agent requests read and write tools
    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read", "write"),
      system_prompt="Test prompt",
    )

    # But write tool is disabled in config
    config = Config(tools=ToolsConfig(write=WriteToolConfig(enabled=False)))
    core = AgentCore(agent_definition=agent_def, config=config)

    # read should be available (in agent def AND enabled)
    assert core.tool_registry.get("read") is not None
    # write should NOT be available (in agent def but disabled)
    assert core.tool_registry.get("write") is None

  def test_agent_definition_with_all_tools_disabled(self) -> None:
    """Test agent definition when all requested tools are disabled."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read", "write"),
      system_prompt="Test prompt",
    )

    config = Config(
      tools=ToolsConfig(
        read=ReadToolConfig(enabled=False),
        write=WriteToolConfig(enabled=False),
      )
    )
    core = AgentCore(agent_definition=agent_def, config=config)

    # No tools should be available (all disabled)
    assert core.tool_registry.get("read") is None
    assert core.tool_registry.get("write") is None
    assert core.tool_registry.get("list") is None  # Not in agent def


class TestWebToolsEnabledFlag:
  """Tests for web search and web fetch tools enabled flag."""

  def test_websearch_disabled_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that websearch is not available when disabled or API key missing."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    config = Config()
    core = AgentCore(config=config)

    # websearch should not be in default tools (no API key)
    assert core.tool_registry.get("websearch") is None

  def test_webfetch_disabled_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that webfetch is not available when API key is missing."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    config = Config()
    core = AgentCore(config=config)

    # webfetch should not be in default tools (no API key)
    assert core.tool_registry.get("webfetch") is None

  def test_websearch_disabled_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that websearch respects enabled flag even with API key."""
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

    from ollama import Client

    client = Client(host="http://localhost:11434")

    config = Config(tools=ToolsConfig(websearch=WebSearchToolConfig(enabled=False)))
    core = AgentCore(config=config, client=client)

    # websearch should not be in tools (disabled)
    assert core.tool_registry.get("websearch") is None

  def test_webfetch_disabled_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that webfetch respects enabled flag even with API key."""
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

    from ollama import Client

    client = Client(host="http://localhost:11434")

    config = Config(tools=ToolsConfig(webfetch=WebFetchToolConfig(enabled=False)))
    core = AgentCore(config=config, client=client)

    # webfetch should not be in tools (disabled)
    assert core.tool_registry.get("webfetch") is None
