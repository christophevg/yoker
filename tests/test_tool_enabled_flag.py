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
    assert core.tools.get("yoker:read") is None
    # Other tools should still be available
    assert core.tools.get("yoker:list") is not None

  def test_list_tool_disabled(self) -> None:
    """Test that list tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(list=ListToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:list") is None
    assert core.tools.get("yoker:read") is not None

  def test_write_tool_disabled(self) -> None:
    """Test that write tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(write=WriteToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:write") is None
    assert core.tools.get("yoker:read") is not None

  def test_update_tool_disabled(self) -> None:
    """Test that update tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:update") is None
    assert core.tools.get("yoker:read") is not None

  def test_search_tool_disabled(self) -> None:
    """Test that search tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(search=SearchToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:search") is None
    assert core.tools.get("yoker:read") is not None

  def test_mkdir_tool_disabled(self) -> None:
    """Test that mkdir tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(mkdir=MkdirToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:mkdir") is None
    assert core.tools.get("yoker:read") is not None

  def test_existence_tool_disabled(self) -> None:
    """Test that existence tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(existence=ExistenceToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:existence") is None
    assert core.tools.get("yoker:read") is not None

  def test_git_tool_disabled(self) -> None:
    """Test that git tool is not registered when enabled=False."""
    config = Config(tools=ToolsConfig(git=GitToolConfig(enabled=False)))
    core = Agent(config=config)

    assert core.tools.get("yoker:git") is None
    assert core.tools.get("yoker:read") is not None

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

    assert core.tools.get("yoker:read") is None
    assert core.tools.get("yoker:write") is None
    assert core.tools.get("yoker:update") is None
    # Other tools should still be available
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:search") is not None

  def test_all_tools_enabled_by_default(self) -> None:
    """Test that all tools are enabled by default."""
    config = Config()
    core = Agent(config=config)

    # All default tools should be present
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:write") is not None
    assert core.tools.get("yoker:update") is not None
    assert core.tools.get("yoker:search") is not None
    assert core.tools.get("yoker:existence") is not None
    assert core.tools.get("yoker:mkdir") is not None


class TestGetKnownToolsEnabledFlag:
  """Tests for tool registry respecting enabled flag."""

  def test_tool_registry_excludes_disabled_tools(self) -> None:
    """Test that tool registry excludes disabled tools."""
    config = Config(
      tools=ToolsConfig(
        read=ReadToolConfig(enabled=False),
        write=WriteToolConfig(enabled=False),
      )
    )
    core = Agent(config=config)

    # read and write should not be in registry
    assert core.tools.get("yoker:read") is None
    assert core.tools.get("yoker:write") is None
    # Other tools should be present
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:search") is not None

  def test_tool_registry_includes_enabled_tools(self) -> None:
    """Test that tool registry includes enabled tools."""
    config = Config()
    core = Agent(config=config)

    # All default tools should be present
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:write") is not None
    assert core.tools.get("yoker:update") is not None
    assert core.tools.get("yoker:search") is not None
    assert core.tools.get("yoker:existence") is not None
    assert core.tools.get("yoker:mkdir") is not None
    assert core.tools.get("yoker:git") is not None


class TestAgentDefinitionAndEnabledFlag:
  """Tests for agent definition tool list AND enabled flag working together."""

  def test_agent_definition_respects_enabled_flag(self) -> None:
    """Test that agent definition filtering still respects enabled flag."""
    from yoker.agents import AgentDefinition

    # Agent requests read and write tools
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read", "write"),
      system_prompt="Test prompt",
    )

    # But write tool is disabled in config
    config = Config(tools=ToolsConfig(write=WriteToolConfig(enabled=False)))
    core = Agent(agent_definition=agent_def, config=config)

    # read should be available (in agent def AND enabled)
    assert core.tools.get("yoker:read") is not None
    # write should NOT be available (in agent def but disabled)
    assert core.tools.get("yoker:write") is None

  def test_agent_definition_with_all_tools_disabled(self) -> None:
    """Test agent definition when all requested tools are disabled."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
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

    # Requested tools that are disabled should not be available
    assert core.tools.get("yoker:read") is None
    assert core.tools.get("yoker:write") is None
    # Tools not in agent definition should not be available (agent def restricts tools)
    # Note: When agent definition specifies tools, only those tools are available (if enabled)
    # Since read/write are disabled and list is not requested, agent has no tools


class TestWebToolsEnabledFlag:
  """Tests for web search and web fetch tools enabled flag."""

  def test_websearch_disabled_without_api_key(self) -> None:
    """Test that websearch is not available when disabled or API key missing."""
    config = Config()
    core = Agent(config=config)

    # websearch should not be in default tools (no API key)
    assert core.tools.get("yoker:websearch") is None

  def test_webfetch_disabled_without_api_key(self) -> None:
    """Test that webfetch is not available when API key is missing."""
    config = Config()
    core = Agent(config=config)

    # webfetch should not be in default tools (no API key)
    assert core.tools.get("yoker:webfetch") is None

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
    assert core.tools.get("yoker:websearch") is None

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
    assert core.tools.get("yoker:webfetch") is None
