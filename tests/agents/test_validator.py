"""Tests for agent definition validator."""

import pytest

from yoker.agents.schema import AgentDefinition
from yoker.agents.validator import (
  validate_agent_definition,
  validate_non_empty_string,
  validate_tools,
)
from yoker.config.schema import (
  AgentToolConfig,
  ListToolConfig,
  ReadToolConfig,
  SearchToolConfig,
  ToolsConfig,
)
from yoker.exceptions import ValidationError


class TestValidateNonEmptyString:
  """Tests for non-empty string validation."""

  def test_valid_non_empty_string(self) -> None:
    """Test valid non-empty string passes."""
    validate_non_empty_string("valid", "test.path")  # Should not raise

  def test_empty_string_fails(self) -> None:
    """Test empty string raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
      validate_non_empty_string("", "test.path")
    assert "test.path" in str(exc_info.value)

  def test_whitespace_only_fails(self) -> None:
    """Test whitespace-only string raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
      validate_non_empty_string("   ", "test.path")
    assert "non-empty string" in str(exc_info.value)


class TestValidateTools:
  """Tests for tools validation."""

  @pytest.fixture
  def tools_config(self) -> ToolsConfig:
    """Create a tools configuration for testing."""
    return ToolsConfig(
      list=ListToolConfig(enabled=True),
      read=ReadToolConfig(enabled=True),
      search=SearchToolConfig(enabled=False),
      agent=AgentToolConfig(enabled=False),
    )

  def test_validate_known_enabled_tools(self, tools_config: ToolsConfig) -> None:
    """Test validation passes for known enabled tools."""
    warnings = validate_tools(("List", "Read"), tools_config, "agent.tools")
    assert warnings == []

  def test_validate_unknown_tool(self, tools_config: ToolsConfig) -> None:
    """Test validation fails for unknown tool."""
    with pytest.raises(ValidationError) as exc_info:
      validate_tools(("UnknownTool",), tools_config, "agent.tools")
    assert "unknown tool" in str(exc_info.value)

  def test_validate_disabled_tool_warning(self, tools_config: ToolsConfig) -> None:
    """Test validation warns for disabled tools."""
    warnings = validate_tools(("Search",), tools_config, "agent.tools")
    assert len(warnings) == 1
    assert "not enabled" in warnings[0]

  def test_validate_tool_case_insensitive(self, tools_config: ToolsConfig) -> None:
    """Test tool names are case-insensitive."""
    warnings = validate_tools(("list", "READ"), tools_config, "agent.tools")
    assert warnings == []

  def test_validate_empty_tools_tuple(self, tools_config: ToolsConfig) -> None:
    """Test empty tools tuple passes (handled by validate_agent_definition)."""
    warnings = validate_tools((), tools_config, "agent.tools")
    assert warnings == []


class TestValidateAgentDefinition:
  """Tests for full agent definition validation."""

  @pytest.fixture
  def tools_config(self) -> ToolsConfig:
    """Create a tools configuration for testing."""
    return ToolsConfig(
      list=ListToolConfig(enabled=True),
      read=ReadToolConfig(enabled=True),
      search=SearchToolConfig(enabled=True),
      agent=AgentToolConfig(enabled=True),
    )

  def test_validate_valid_definition(self, tools_config: ToolsConfig) -> None:
    """Test valid agent definition passes."""
    definition = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("Read", "Search"),
      system_prompt="You are a test agent.",
    )
    warnings = validate_agent_definition(definition, tools_config)
    assert warnings == []

  def test_validate_empty_name(self, tools_config: ToolsConfig) -> None:
    """Test empty name raises ValidationError."""
    definition = AgentDefinition(
      name="",
      description="Test",
      tools=("Read",),
    )
    with pytest.raises(ValidationError) as exc_info:
      validate_agent_definition(definition, tools_config)
    assert "agent.name" in str(exc_info.value)

  def test_validate_empty_description(self, tools_config: ToolsConfig) -> None:
    """Test empty description raises ValidationError."""
    definition = AgentDefinition(
      name="test",
      description="",
      tools=("Read",),
    )
    with pytest.raises(ValidationError) as exc_info:
      validate_agent_definition(definition, tools_config)
    assert "agent.description" in str(exc_info.value)

  def test_validate_empty_tools(self, tools_config: ToolsConfig) -> None:
    """Test empty tools raises ValidationError."""
    definition = AgentDefinition(
      name="test",
      description="Test",
      tools=(),
    )
    with pytest.raises(ValidationError) as exc_info:
      validate_agent_definition(definition, tools_config)
    assert "agent.tools" in str(exc_info.value)

  def test_validate_unknown_tool(self, tools_config: ToolsConfig) -> None:
    """Test unknown tool raises ValidationError."""
    definition = AgentDefinition(
      name="test",
      description="Test",
      tools=("UnknownTool",),
    )
    with pytest.raises(ValidationError) as exc_info:
      validate_agent_definition(definition, tools_config)
    assert "unknown tool" in str(exc_info.value)

  def test_validate_duplicate_name(self, tools_config: ToolsConfig) -> None:
    """Test duplicate name raises ValidationError."""
    definition = AgentDefinition(
      name="existing",
      description="Test",
      tools=("Read",),
    )
    existing = {"existing"}
    with pytest.raises(ValidationError) as exc_info:
      validate_agent_definition(definition, tools_config, existing_names=existing)
    assert "already defined" in str(exc_info.value)

  def test_validate_unique_name(self, tools_config: ToolsConfig) -> None:
    """Test unique name passes."""
    definition = AgentDefinition(
      name="unique",
      description="Test",
      tools=("Read",),
      system_prompt="You are a unique agent.",
    )
    existing = {"other", "another"}
    warnings = validate_agent_definition(definition, tools_config, existing_names=existing)
    assert warnings == []

  def test_validate_empty_system_prompt_warning(self, tools_config: ToolsConfig) -> None:
    """Test empty system prompt generates warning."""
    definition = AgentDefinition(
      name="test",
      description="Test",
      tools=("Read",),
      system_prompt="",
    )
    warnings = validate_agent_definition(definition, tools_config)
    assert len(warnings) == 1
    assert "no system prompt" in warnings[0].lower()

  def test_validate_disabled_tool_warning(self, tools_config: ToolsConfig) -> None:
    """Test disabled tool generates warning."""
    # Create config with Search disabled
    config = ToolsConfig(
      read=ReadToolConfig(enabled=True),
      search=SearchToolConfig(enabled=False),
    )
    definition = AgentDefinition(
      name="test",
      description="Test",
      tools=("Read", "Search"),
      system_prompt="Prompt",
    )
    warnings = validate_agent_definition(definition, config)
    assert len(warnings) == 1
    assert "not enabled" in warnings[0]

  def test_validate_multiple_warnings(self, tools_config: ToolsConfig) -> None:
    """Test multiple warnings are collected."""
    config = ToolsConfig(
      read=ReadToolConfig(enabled=True),
      search=SearchToolConfig(enabled=False),
      agent=AgentToolConfig(enabled=False),
    )
    definition = AgentDefinition(
      name="test",
      description="Test",
      tools=("Search", "Agent"),  # Both disabled
      system_prompt="",  # Empty prompt
    )
    warnings = validate_agent_definition(definition, config)
    assert len(warnings) == 3  # Two disabled tools + empty prompt
