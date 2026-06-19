"""Tests for tool enabled flag enforcement."""

from yoker.agent import Agent
from yoker.config import (
  BackendConfig,
  Config,
  ExistenceToolConfig,
  GitToolConfig,
  ListToolConfig,
  MkdirToolConfig,
  OllamaConfig,
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
    core = Agent(config=config)

    # read tool should not be in registry
    assert core.tools.get("read") is None
    # Other tools should still be available
    assert core.tools.get("list") is not None

  def test_list_tool_disabled(self) -> None:
    """Test that list tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(list=ListToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("list") is None
    assert core.tools.get("read") is not None

  def test_write_tool_disabled(self) -> None:
    """Test that write tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(write=WriteToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("write") is None
    assert core.tools.get("read") is not None

  def test_update_tool_disabled(self) -> None:
    """Test that update tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("update") is None
    assert core.tools.get("read") is not None

  def test_search_tool_disabled(self) -> None:
    """Test that search tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(search=SearchToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("search") is None
    assert core.tools.get("read") is not None

  def test_mkdir_tool_disabled(self) -> None:
    """Test that mkdir tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(mkdir=MkdirToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("mkdir") is None
    assert core.tools.get("read") is not None

  def test_existence_tool_disabled(self) -> None:
    """Test that existence tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(existence=ExistenceToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("existence") is None
    assert core.tools.get("read") is not None

  def test_git_tool_disabled(self) -> None:
    """Test that git tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(git=GitToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("git") is None
    assert core.tools.get("read") is not None

  def test_multiple_tools_disabled(self) -> None:
    """Test that multiple tools can be disabled at once."""
    config = Config(
      tools=ToolsConfig(
        read=ReadToolConfig(enabled=False),
        write=WriteToolConfig(enabled=False),
        update=UpdateToolConfig(enabled=False),
      )
    )
    core = Agent(config=config)

    assert core.tools.get("read") is None
    assert core.tools.get("write") is None
    assert core.tools.get("update") is None
    # Other tools should still be available
    assert core.tools.get("list") is not None
    assert core.tools.get("search") is not None

  def test_all_tools_enabled_by_default(self) -> None:
    """Test that all tools are enabled by default."""
    config = Config()
    core = Agent(config=config)

    # All default tools should be present
    assert core.tools.get("read") is not None
    assert core.tools.get("list") is not None
    assert core.tools.get("write") is not None
    assert core.tools.get("update") is not None
    assert core.tools.get("search") is not None
    assert core.tools.get("existence") is not None
    assert core.tools.get("mkdir") is not None


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
    core = Agent(config=config)

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
    core = Agent(config=config)

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
    assert "git" in tool_names
    assert "websearch" in tool_names
    assert "webfetch" in tool_names
    assert "agent" in tool_names


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
    core = Agent(agent_definition=agent_def, config=config)

    # read should be available (in agent def AND enabled)
    assert core.tools.get("read") is not None
    # write should NOT be available (in agent def but disabled)
    assert core.tools.get("write") is None

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
    core = Agent(agent_definition=agent_def, config=config)

    # No tools should be available (all disabled)
    assert core.tools.get("read") is None
    assert core.tools.get("write") is None
    assert core.tools.get("list") is None  # Not in agent def


class TestWebToolsEnabledFlag:
  """Tests for web search and web fetch tools enabled flag."""

  def test_websearch_disabled_without_api_key(self) -> None:
    """Test that websearch is not available when disabled or API key missing."""
    config = Config()
    core = Agent(config=config)

    # websearch should not be in default tools (no API key)
    assert core.tools.get("websearch") is None

  def test_webfetch_disabled_without_api_key(self) -> None:
    """Test that webfetch is not available when API key is missing."""
    config = Config()
    core = Agent(config=config)

    # webfetch should not be in default tools (no API key)
    assert core.tools.get("webfetch") is None

  def test_websearch_disabled_flag(self) -> None:
    """Test that websearch respects enabled flag even with API key."""
    from ollama import Client

    client = Client(host="http://localhost:11434")

    config = Config(
      backend=BackendConfig(ollama=OllamaConfig(api_key="test-key")),
      tools=ToolsConfig(websearch=WebSearchToolConfig(enabled=False)),
    )
    core = Agent(config=config, client=client)

    # websearch should not be in tools (disabled)
    assert core.tools.get("websearch") is None

  def test_webfetch_disabled_flag(self) -> None:
    """Test that webfetch respects enabled flag even with API key."""
    from ollama import Client

    client = Client(host="http://localhost:11434")

    config = Config(
      backend=BackendConfig(ollama=OllamaConfig(api_key="test-key")),
      tools=ToolsConfig(webfetch=WebFetchToolConfig(enabled=False)),
    )
    core = Agent(config=config, client=client)

    # webfetch should not be in tools (disabled)
    assert core.tools.get("webfetch") is None
