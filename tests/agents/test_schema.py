"""Tests for agent definition schema."""

from yoker.agents.schema import AgentDefinition


class TestAgentDefinitionSchema:
  """Tests for AgentDefinition dataclass."""

  def test_agent_definition_required_fields(self) -> None:
    """Test AgentDefinition with required fields only."""
    definition = AgentDefinition(
      simple_name="test-agent",
      description="Test agent for unit tests",
      tools=["Read", "Search"],
    )
    assert definition.simple_name == "test-agent"
    assert definition.description == "Test agent for unit tests"
    assert definition.tools == ["Read", "Search"]
    assert definition.color is None
    # system_prompt has a default value
    assert definition.system_prompt == "You are a helpful assistant."
    assert definition.source_path == ""

  def test_agent_definition_all_fields(self) -> None:
    """Test AgentDefinition with all fields."""
    definition = AgentDefinition(
      simple_name="researcher",
      description="Research assistant",
      tools=["List", "Read", "Search"],
      color="blue",
      system_prompt="You are a research assistant.",
      source_path="/agents/researcher.md",
    )
    assert definition.simple_name == "researcher"
    assert definition.description == "Research assistant"
    assert definition.tools == ["List", "Read", "Search"]
    assert definition.color == "blue"
    assert definition.system_prompt == "You are a research assistant."
    assert definition.source_path == "/agents/researcher.md"

  def test_agent_definition_frozen(self) -> None:
    """Test that AgentDefinition is mutable (not frozen)."""
    definition = AgentDefinition(
      simple_name="test",
      description="Test",
      tools=["Read"],
    )
    # AgentDefinition is mutable (not frozen)
    definition.simple_name = "changed"  # type: ignore
    assert definition.simple_name == "changed"

  def test_agent_definition_tuple_normalized_to_list(self) -> None:
    """Test that a tools tuple is normalized to a list."""
    definition = AgentDefinition(
      simple_name="test",
      description="Test",
      tools=("Read", "Search"),
    )
    # Tuples are normalized to lists in __post_init__.
    assert definition.tools == ["Read", "Search"]
    assert isinstance(definition.tools, list)

  def test_agent_definition_empty_tools(self) -> None:
    """Test AgentDefinition can have empty tools list (validation handles this)."""
    definition = AgentDefinition(
      simple_name="test",
      description="Test",
      tools=[],
    )
    assert definition.tools == []

  def test_agent_definition_single_tool(self) -> None:
    """Test AgentDefinition with single tool."""
    definition = AgentDefinition(
      simple_name="test",
      description="Test",
      tools=["Read"],
    )
    assert len(definition.tools) == 1
    assert definition.tools[0] == "Read"
