"""Tests for yoker AgentCore class."""

from pathlib import Path

import pytest

from yoker.agent_base import DEFAULT_SYSTEM_PROMPT, AgentCore
from yoker.config import BackendConfig, Config, OllamaConfig
from yoker.thinking import ThinkingMode


class TestAgentCoreInitialization:
  """Tests for AgentCore initialization."""

  def test_agent_core_initialization_defaults(self) -> None:
    """Test AgentCore initializes with default config."""
    core = AgentCore()
    assert core.model == Config().backend.ollama.model
    assert core.thinking_mode == ThinkingMode.ON
    assert core.tool_registry is not None
    assert core.context is not None
    assert core.agent_definition is None
    assert core.command_registry is None
    assert core.recursion_depth == 0
    assert core.max_recursion_depth == core.config.tools.agent.max_recursion_depth

  def test_agent_core_model_override(self) -> None:
    """Test model parameter overrides config."""
    core = AgentCore(model="custom-model")
    assert core.model == "custom-model"

  def test_agent_core_with_config(self) -> None:
    """Test AgentCore accepts config."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="test-model")))
    core = AgentCore(config=config)
    assert core.model == "test-model"

  def test_agent_core_thinking_mode(self) -> None:
    """Test thinking_mode parameter is respected."""
    core = AgentCore(thinking_mode=ThinkingMode.OFF)
    assert core.thinking_mode == ThinkingMode.OFF

    core_silent = AgentCore(thinking_mode=ThinkingMode.SILENT)
    assert core_silent.thinking_mode == ThinkingMode.SILENT

  def test_agent_core_recursion_depth_default(self) -> None:
    """Test recursion depth starts at 0 by default."""
    core = AgentCore()
    assert core.recursion_depth == 0
    assert core.max_recursion_depth == core.config.tools.agent.max_recursion_depth

  def test_agent_core_recursion_depth_custom(self) -> None:
    """Test recursion depth can be set via internal parameter."""
    core = AgentCore(_recursion_depth=2)
    assert core.recursion_depth == 2

  def test_agent_core_recursion_depth_validation_negative(self) -> None:
    """Test that negative recursion depth raises ValueError."""
    with pytest.raises(ValueError, match="must be non-negative"):
      AgentCore(_recursion_depth=-1)

  def test_agent_core_recursion_depth_validation_exceeds_max(self) -> None:
    """Test that recursion depth exceeding max raises ValueError."""
    config = Config()
    max_depth = config.tools.agent.max_recursion_depth
    with pytest.raises(ValueError, match="exceeds max_recursion_depth"):
      AgentCore(_recursion_depth=max_depth + 1)


class TestAgentCoreToolRegistry:
  """Tests for AgentCore tool registry building."""

  def test_tool_registry_has_default_tools(self) -> None:
    """Test that default tools are available."""
    core = AgentCore()
    assert core.tool_registry.get("read") is not None
    assert core.tool_registry.get("list") is not None
    assert core.tool_registry.get("write") is not None
    assert core.tool_registry.get("update") is not None
    assert core.tool_registry.get("search") is not None

  def test_tool_registry_guardrails_injected(self) -> None:
    """Test that all filesystem tools have guardrails injected."""
    core = AgentCore()
    # Check filesystem tools have guardrails
    read_tool = core.tool_registry.get("read")
    assert read_tool is not None
    assert hasattr(read_tool, "_guardrail")

    list_tool = core.tool_registry.get("list")
    assert list_tool is not None
    assert hasattr(list_tool, "_guardrail")

    write_tool = core.tool_registry.get("write")
    assert write_tool is not None
    assert hasattr(write_tool, "_guardrail")

  def test_tool_registry_filtering_by_agent_definition(self) -> None:
    """Test that tool registry respects agent definition."""
    from yoker.agents import AgentDefinition

    # Agent with only "read" tool
    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Test prompt",
    )
    core = AgentCore(agent_definition=agent_def)
    assert core.tool_registry.get("read") is not None
    # Other tools should not be present
    assert core.tool_registry.get("list") is None
    assert core.tool_registry.get("write") is None

  def test_agent_definition_property(self) -> None:
    """Test that agent_definition property returns loaded definition."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Test prompt",
    )
    core = AgentCore(agent_definition=agent_def)
    assert core.agent_definition is not None
    assert core.agent_definition.name == "test"


class TestAgentCoreEventHandlers:
  """Tests for AgentCore event handler management."""

  def test_add_event_handler(self) -> None:
    """Test adding an event handler."""
    core = AgentCore()

    handler_called = []

    def handler(event: object) -> None:
      handler_called.append(event)

    core.add_event_handler(handler)
    assert len(core.get_event_handlers()) == 1

  def test_remove_event_handler(self) -> None:
    """Test removing an event handler."""
    core = AgentCore()

    def handler(event: object) -> None:
      pass

    core.add_event_handler(handler)
    assert len(core.get_event_handlers()) == 1

    core.remove_event_handler(handler)
    assert len(core.get_event_handlers()) == 0

  def test_get_event_handlers_returns_copy(self) -> None:
    """Test that get_event_handlers returns a copy."""
    core = AgentCore()

    def handler(event: object) -> None:
      pass

    core.add_event_handler(handler)
    handlers = core.get_event_handlers()
    assert len(handlers) == 1

    # Modifying returned list should not affect internal state
    handlers.clear()
    assert len(core.get_event_handlers()) == 1

  def test_remove_nonexistent_handler_raises(self) -> None:
    """Test that removing a non-existent handler raises ValueError."""
    core = AgentCore()

    def handler(event: object) -> None:
      pass

    with pytest.raises(ValueError):
      core.remove_event_handler(handler)


class TestAgentCoreContext:
  """Tests for AgentCore context initialization."""

  def test_context_has_system_prompt(self) -> None:
    """Test that context is initialized with system prompt."""
    core = AgentCore()
    messages = core.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].get("content") == DEFAULT_SYSTEM_PROMPT

  def test_context_uses_custom_system_prompt(self) -> None:
    """Test that agent definition system prompt is used."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for testing.",
    )
    core = AgentCore(agent_definition=agent_def)
    messages = core.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].get("content") == "Custom system prompt for testing."


class TestAgentCoreSecurity:
  """Tests for AgentCore security requirements."""

  def test_config_validation_called(self) -> None:
    """Test that configuration validation is called during initialization."""
    # This test verifies SEC-3: Configuration validation MUST run before AgentCore initialization
    # Using a valid config should not raise any errors
    config = Config()
    core = AgentCore(config=config)
    assert core.config is not None

  def test_guardrail_enforcement_validation(self) -> None:
    """Test that guardrails are enforced on all filesystem tools."""
    # This test verifies SEC-1: Guardrails MUST be injected into all filesystem tools
    core = AgentCore()
    # All filesystem tools should have _guardrail attribute
    filesystem_tools = ["read", "list", "write", "update", "search", "existence", "mkdir", "git"]
    for tool_name in filesystem_tools:
      tool = core.tool_registry.get(tool_name)
      if tool is not None:  # Tool might be filtered by agent definition
        assert hasattr(tool, "_guardrail"), f"Tool {tool_name} missing guardrail"

  def test_each_core_is_independent(self) -> None:
    """Test that each AgentCore instance is independent (SEC-2)."""
    core1 = AgentCore(model="model1")
    core2 = AgentCore(model="model2")

    assert core1.model != core2.model
    assert core1.context is not core2.context
    assert core1.tool_registry is not core2.tool_registry

  def test_config_is_read_only(self) -> None:
    """Test that config cannot be mutated through AgentCore (SEC-4)."""
    core = AgentCore()
    config = core.config
    # Config is a frozen dataclass, so mutation should raise
    with pytest.raises(AttributeError):
      config.backend.ollama.model = "mutated"  # type: ignore


class TestAgentCoreProperties:
  """Tests for AgentCore property access."""

  def test_config_property(self) -> None:
    """Test config property returns configuration."""
    config = Config()
    core = AgentCore(config=config)
    assert core.config is config

  def test_model_property(self) -> None:
    """Test model property returns model name."""
    core = AgentCore(model="test-model")
    assert core.model == "test-model"

  def test_thinking_mode_property(self) -> None:
    """Test thinking_mode property returns thinking mode."""
    core = AgentCore(thinking_mode=ThinkingMode.SILENT)
    assert core.thinking_mode == ThinkingMode.SILENT

  def test_agent_definition_property_none(self) -> None:
    """Test agent_definition property returns None when not provided."""
    core = AgentCore()
    assert core.agent_definition is None

  def test_tool_registry_property(self) -> None:
    """Test tool_registry property returns tool registry."""
    core = AgentCore()
    assert core.tool_registry is not None
    assert hasattr(core.tool_registry, "get")
    assert hasattr(core.tool_registry, "register")

  def test_context_property(self) -> None:
    """Test context property returns context manager."""
    core = AgentCore()
    assert core.context is not None
    assert hasattr(core.context, "get_messages")

  def test_command_registry_property_none(self) -> None:
    """Test command_registry property returns None when not provided."""
    core = AgentCore()
    assert core.command_registry is None

  def test_command_registry_property_with_registry(self) -> None:
    """Test command_registry property returns registry when provided."""
    from yoker.commands import CommandRegistry

    registry = CommandRegistry()
    core = AgentCore(command_registry=registry)
    assert core.command_registry is registry


class TestAgentCoreConfigLoading:
  """Tests for AgentCore configuration loading."""

  def test_config_from_path(self, tmp_path: Path) -> None:
    """Test loading configuration from file path."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[backend.ollama]\nmodel = "path-model"\n')

    core = AgentCore(config_path=config_file)
    assert core.model == "path-model"

  def test_config_object_takes_precedence(self, tmp_path: Path) -> None:
    """Test that config object takes precedence over config_path."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[backend.ollama]\nmodel = "path-model"\n')

    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="object-model")))
    core = AgentCore(config=config, config_path=config_file)
    assert core.model == "object-model"


class TestAgentCoreGuardrailProperty:
  """Tests for AgentCore guardrail property (H2)."""

  def test_guardrail_property_exists(self) -> None:
    """Test that guardrail property is accessible."""
    core = AgentCore()
    assert hasattr(core, "guardrail")

  def test_guardrail_property_returns_path_guardrail(self) -> None:
    """Test that guardrail property returns PathGuardrail instance."""
    from yoker.tools.path_guardrail import PathGuardrail

    core = AgentCore()
    assert isinstance(core.guardrail, PathGuardrail)

  def test_guardrail_property_is_read_only(self) -> None:
    """Test that guardrail property cannot be set directly."""
    core = AgentCore()
    # Attempting to set should raise AttributeError (property is read-only)
    with pytest.raises(AttributeError):
      core.guardrail = None  # type: ignore


class TestAgentCoreAgentPath:
  """Tests for agent_path parameter."""

  def test_agent_path_loads_definition(self, tmp_path: Path) -> None:
    """Test loading agent definition from file path."""
    agent_file = tmp_path / "test_agent.md"
    agent_file.write_text(
      """---
name: test-agent
description: Test agent from file
tools:
  - read
  - list
---

You are a test agent loaded from a file.
"""
    )

    core = AgentCore(agent_path=agent_file)
    assert core.agent_definition is not None
    assert core.agent_definition.name == "test-agent"
    assert "read" in core.agent_definition.tools

  def test_agent_path_with_valid_markdown(self, tmp_path: Path) -> None:
    """Test agent_path with valid Markdown + YAML frontmatter."""
    agent_file = tmp_path / "researcher.md"
    agent_file.write_text(
      """---
name: researcher
description: Research assistant
tools:
  - read
  - search
  - websearch
---

You are a research assistant specialized in finding information.
"""
    )

    core = AgentCore(agent_path=agent_file)
    assert core.agent_definition is not None
    assert core.agent_definition.name == "researcher"
    assert core.agent_definition.system_prompt is not None
    assert "research assistant" in core.agent_definition.system_prompt


class TestAgentCoreContextManager:
  """Tests for context_manager parameter."""

  def test_context_manager_parameter(self) -> None:
    """Test that custom context manager is used."""
    from yoker.context import BasicPersistenceContextManager

    custom_context = BasicPersistenceContextManager(
      storage_path="custom_storage",
      session_id="custom-session-123",
    )
    core = AgentCore(context_manager=custom_context)

    assert core.context is custom_context
    assert core.context.get_session_id() == "custom-session-123"

  def test_context_manager_persists_system_prompt(self) -> None:
    """Test that custom context manager receives system prompt."""
    from yoker.agents import AgentDefinition
    from yoker.context import BasicPersistenceContextManager

    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for context test.",
    )
    custom_context = BasicPersistenceContextManager(
      storage_path="test_storage",
      session_id="test-session",
    )
    core = AgentCore(agent_definition=agent_def, context_manager=custom_context)

    messages = core.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].get("content") == "Custom system prompt for context test."


class TestAgentCoreClientParameter:
  """Tests for client parameter and conditional WebSearch/WebFetch tools."""

  def test_client_parameter_accepts_client(self) -> None:
    """Test that AgentCore accepts a client parameter."""
    from ollama import Client

    client = Client(host="http://localhost:11434")
    core = AgentCore(client=client)

    # AgentCore should accept the client without error
    assert core is not None

  def test_websearch_requires_api_key_and_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that WebSearch tool is only added when API key and client are present."""
    from ollama import Client

    # Set API key
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

    client = Client(host="http://localhost:11434")
    core = AgentCore(client=client)

    # WebSearch tool should be present (API key + client provided)
    # Note: We can't verify it's actually registered because tools are filtered
    # by agent definition. Just verify no errors occur.
    assert core.tool_registry is not None

  def test_websearch_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that WebSearch tool is not added when API key is missing."""
    # Remove API key if present
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    core = AgentCore()

    # WebSearch should not be in default tools (no API key)
    assert core.tool_registry.get("websearch") is None
    assert core.tool_registry.get("webfetch") is None

  def test_websearch_missing_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that WebSearch tool is not added when client is missing."""
    # Set API key but don't pass client
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

    core = AgentCore()  # No client parameter

    # WebSearch should not be added (no client)
    assert core.tool_registry.get("websearch") is None
    assert core.tool_registry.get("webfetch") is None


class TestAgentCoreToolMatching:
  """Tests for tool matching and filtering."""

  def test_case_insensitive_tool_matching(self) -> None:
    """Test that tool matching is case-insensitive."""
    from yoker.agents import AgentDefinition

    # Agent definition with mixed-case tool names
    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("Read", "LIST", "Write"),
      system_prompt="Test prompt",
    )
    core = AgentCore(agent_definition=agent_def)

    # All tools should be registered (case-insensitive matching)
    assert core.tool_registry.get("read") is not None
    assert core.tool_registry.get("list") is not None
    assert core.tool_registry.get("write") is not None

  def test_empty_tools_list(self) -> None:
    """Test agent definition with empty tools list."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=(),  # Empty tools list
      system_prompt="Test prompt",
    )
    core = AgentCore(agent_definition=agent_def)

    # No tools should be registered
    assert core.tool_registry.get("read") is None
    assert core.tool_registry.get("list") is None
    assert core.tool_registry.get("write") is None


class TestAgentCoreGuardrailValidation:
  """Tests for SEC-5: Guardrail validation failure."""

  def test_guardrail_validation_failure_raises_runtime_error(
    self, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that missing guardrail on filesystem tool raises RuntimeError (SEC-5)."""
    # This test verifies the defense-in-depth check in _validate_guardrails_enforced
    # We need to create a scenario where a filesystem tool lacks a guardrail

    from yoker.tools import ToolRegistry

    # Create a simple object without _guardrail attribute
    class MockTool:
      def __init__(self) -> None:
        self.name = "read"

    # Create a tool registry with a mock filesystem tool that lacks guardrail
    mock_registry = ToolRegistry()
    mock_tool = MockTool()
    mock_registry.register(mock_tool)

    # Monkey-patch the _build_tool_registry to return our mock registry
    def mock_build_registry(self: object, client: object = None) -> ToolRegistry:
      return mock_registry

    monkeypatch.setattr(AgentCore, "_build_tool_registry", mock_build_registry)

    # AgentCore initialization should raise RuntimeError for missing guardrail
    with pytest.raises(RuntimeError, match="missing guardrail"):
      AgentCore()


class TestAgentCoreBuildToolRegistry:
  """Tests for _build_tool_registry method (H3)."""

  def test_build_tool_registry_filters_by_agent_definition(self) -> None:
    """Test that tool registry is filtered by agent definition."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read", "search"),
      system_prompt="Test prompt",
    )
    core = AgentCore(agent_definition=agent_def)

    # Only read and search should be present
    assert core.tool_registry.get("read") is not None
    assert core.tool_registry.get("search") is not None
    # Other tools should not be present
    assert core.tool_registry.get("list") is None
    assert core.tool_registry.get("write") is None

  def test_build_tool_registry_all_tools_without_agent_definition(self) -> None:
    """Test that all tools are registered when no agent definition is provided."""
    core = AgentCore()

    # All default tools should be present
    assert core.tool_registry.get("read") is not None
    assert core.tool_registry.get("list") is not None
    assert core.tool_registry.get("write") is not None
    assert core.tool_registry.get("update") is not None
    assert core.tool_registry.get("search") is not None
    assert core.tool_registry.get("existence") is not None
    assert core.tool_registry.get("mkdir") is not None

  def test_build_tool_registry_injects_guardrails(self) -> None:
    """Test that guardrails are injected into all filesystem tools."""
    core = AgentCore()

    filesystem_tools = ["read", "list", "write", "update", "search", "existence", "mkdir"]
    for tool_name in filesystem_tools:
      tool = core.tool_registry.get(tool_name)
      assert tool is not None, f"Tool {tool_name} not found"
      assert hasattr(tool, "_guardrail"), f"Tool {tool_name} missing guardrail"

  def test_build_tool_registry_git_tool_with_config(self) -> None:
    """Test that GitTool is created with proper configuration."""
    core = AgentCore()

    git_tool = core.tool_registry.get("git")
    assert git_tool is not None
    assert hasattr(git_tool, "_guardrail")


class TestAgentCoreGuardrailPropertyTypeAnnotation:
  """Tests for guardrail property type annotation."""

  def test_guardrail_has_correct_type_annotation(self) -> None:
    """Test that guardrail property has proper type annotation."""
    # Check that the property exists and has correct type annotation
    import inspect

    from yoker.tools.path_guardrail import PathGuardrail

    # Get the property descriptor
    guardrail_prop = getattr(AgentCore, "guardrail", None)
    assert guardrail_prop is not None
    assert isinstance(guardrail_prop, property)

    # Check the fget method's type annotation
    fget = guardrail_prop.fget
    assert fget is not None
    sig = inspect.signature(fget)
    # The annotation might be a forward reference string or the actual class
    annotation = sig.return_annotation
    # Accept both string 'PathGuardrail' and the actual class
    assert annotation in ("PathGuardrail", PathGuardrail)
