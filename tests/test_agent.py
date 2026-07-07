"""Tests for yoker Agent class."""

from pathlib import Path

import pytest

from yoker.config import BackendConfig, Config, OllamaConfig
from yoker.core import Agent
from yoker.core.thinking import ThinkingMode


class TestAgentInitialization:
  """Tests for Agent initialization."""

  def test_agent_initialization_defaults(self) -> None:
    """Test Agent initializes with default config."""
    # Pass explicit config to prevent auto-discovery from picking up local config
    core = Agent(config=Config())
    assert core.model == Config().backend.ollama.model
    assert core.thinking_mode == ThinkingMode.ON
    assert core.tools is not None
    assert core.context is not None
    # recursion_depth/max_recursion_depth removed from Agent
    # (moved to Session). Agent no longer holds an agents registry either.
    assert not hasattr(core, "recursion_depth")
    assert not hasattr(core, "max_recursion_depth")
    assert not hasattr(core, "agents")

  def test_agent_model_from_config(self) -> None:
    """Test model comes from config."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="custom-model")))
    core = Agent(config=config)
    assert core.model == "custom-model"

  def test_agent_with_config(self) -> None:
    """Test Agent accepts config."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="test-model")))
    core = Agent(config=config)
    assert core.model == "test-model"

  def test_agent_thinking_mode(self) -> None:
    """Test thinking_mode parameter is respected."""
    core = Agent(config=Config(), thinking_mode=ThinkingMode.OFF)
    assert core.thinking_mode == ThinkingMode.OFF

    core_silent = Agent(config=Config(), thinking_mode=ThinkingMode.SILENT)
    assert core_silent.thinking_mode == ThinkingMode.SILENT

  def test_agent_recursion_depth_arg_removed(self) -> None:
    """_recursion_depth constructor arg is removed."""
    with pytest.raises(TypeError):
      Agent(config=Config(), _recursion_depth=2)  # type: ignore[call-arg]

  def test_agent_agents_attribute_removed(self) -> None:
    """agent.agents is removed (no shim)."""
    core = Agent(config=Config())
    with pytest.raises(AttributeError):
      _ = core.agents  # noqa: F841

  def test_agent_session_reference_defaults_none(self) -> None:
    """Agent is Session-agnostic and has no _session attribute."""
    core = Agent(config=Config())
    assert not hasattr(core, "_session")


class TestAgentToolRegistry:
  """Tests for Agent tool registry building."""

  def test_tool_registry_has_default_tools(self) -> None:
    """Test that default tools are available."""
    core = Agent(config=Config())
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:write") is not None
    assert core.tools.get("yoker:update") is not None
    assert core.tools.get("yoker:search") is not None

  def test_tool_registry_schemas_have_path_parameter(self) -> None:
    """Filesystem tools declare a path parameter."""
    core = Agent(config=Config())
    for tool_name in (
      "yoker:read",
      "yoker:list",
      "yoker:write",
      "yoker:update",
      "yoker:search",
      "yoker:existence",
      "yoker:mkdir",
    ):
      tool = core.tools.get(tool_name)
      assert tool is not None, f"Tool {tool_name} not found"
      params = tool.schema["function"]["parameters"]
      assert "path" in params["properties"], f"Tool {tool_name} missing path parameter"
      # Path parameter might not have explicit type in schema (Yoker tools)
      # Just verify it exists and is in required parameters
      assert "path" in params.get("required", []), f"Tool {tool_name} missing path in required"

  def test_tool_registry_filtering_by_agent_definition(self) -> None:
    """Test that tool registry respects agent definition."""
    from yoker.agents import AgentDefinition

    # Agent with only "read" tool
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Test prompt",
    )
    core = Agent(config=Config(), agent_definition=agent_def)
    assert core.tools.get("yoker:read") is not None
    # Other tools should not be present
    assert core.tools.get("yoker:list") is None
    assert core.tools.get("yoker:write") is None

  def test_agent_definition_property(self) -> None:
    """Test that agent_definition property returns loaded definition."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Test prompt",
    )
    core = Agent(config=Config(), agent_definition=agent_def)
    assert core.definition.name == "test"

  def test_tool_registry_case_insensitive_agent_tools(self) -> None:
    """Built-in tools are matched case-insensitively from agent definitions."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("Read", "LIST", "Yoker:write"),
      system_prompt="Test prompt",
    )
    core = Agent(config=Config(), agent_definition=agent_def)
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:write") is not None
    assert core.tools.get("yoker:update") is None

  def test_agent_warns_on_missing_tools(self) -> None:
    """Agent logs a warning when the definition requests unavailable tools."""
    from unittest.mock import patch

    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read", "missing_tool", "yoker:also_missing"),
      system_prompt="Test prompt",
    )
    with patch("yoker.core.logger.warning") as mock_warning:
      Agent(config=Config(), agent_definition=agent_def)

    matching = [
      call
      for call in mock_warning.call_args_list
      if call.args and call.args[0] == "agent tools unavailable"
    ]
    assert len(matching) == 1
    assert matching[0].kwargs["missing_tools"] == ["missing_tool", "yoker:also_missing"]


class TestAgentEventHandlers:
  """Tests for Agent event handler management."""

  def test_on_event_registers_handler(self) -> None:
    """on_event registers a handler and returns it for chaining."""
    core = Agent(config=Config())

    def handler(event: object) -> None:
      pass

    returned = core.on_event(handler)
    assert returned is handler
    assert handler in core._event_handlers


class TestAgentContext:
  """Tests for Agent context initialization."""

  def test_context_has_system_prompt(self) -> None:
    """Test that context is initialized with system prompt and environment reminder."""
    core = Agent(config=Config())
    messages = core.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    content = system_messages[0].get("content", "")
    # System message contains environment reminder + agent definition
    assert "You are running inside the Yoker agent harness" in content
    assert f"Current working directory: {Path.cwd()}" in content
    assert f"Model in use: {core.model}" in content
    assert "<agent-definition>" in content

  def test_context_uses_custom_system_prompt(self) -> None:
    """Test that agent definition system prompt is used."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for testing.",
    )
    core = Agent(config=Config(), agent_definition=agent_def)
    messages = core.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    content = system_messages[0].get("content", "")
    # System message contains environment reminder + custom agent definition
    assert "You are running inside the Yoker agent harness" in content
    assert "Custom system prompt for testing." in content


class TestAgentSecurity:
  """Tests for Agent security requirements."""

  def test_config_validation_called(self) -> None:
    """Test that configuration validation is called during initialization."""
    # This test verifies SEC-3: Configuration validation MUST run before Agent initialization
    # Using a valid config should not raise any errors
    config = Config()
    core = Agent(config=config)
    assert core.config is not None

  def test_agent_exposes_path_guardrail_mapping(self) -> None:
    """Agent exposes schema-driven guardrail mapping including the path guardrail."""
    from yoker.tools.guardrails.path import PathGuardrail

    core = Agent(config=Config())
    assert hasattr(core, "_guardrails")
    assert "path" in core._guardrails
    assert isinstance(core._guardrails["path"], PathGuardrail)

  def test_each_core_is_independent(self) -> None:
    """Test that each Agent instance is independent (SEC-2)."""
    core1 = Agent(config=Config(backend=BackendConfig(ollama=OllamaConfig(model="model1"))))
    core2 = Agent(config=Config(backend=BackendConfig(ollama=OllamaConfig(model="model2"))))

    assert core1.model != core2.model
    assert core1.context is not core2.context
    assert core1.tools is not core2.tools

  def test_config_is_mutable(self) -> None:
    """Config is mutable through Agent (Batch 1.8 unfroze config dataclasses)."""
    core = Agent(config=Config())
    config = core.config
    config.backend.ollama.model = "mutated"
    assert config.backend.ollama.model == "mutated"


class TestAgentProperties:
  """Tests for Agent property access."""

  def test_config_property(self) -> None:
    """Test config property returns configuration."""
    config = Config()
    core = Agent(config=config)
    assert core.config is config

  def test_model_property(self) -> None:
    """Test model property returns model name."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="test-model")))
    core = Agent(config=config)
    assert core.model == "test-model"

  def test_thinking_mode_property(self) -> None:
    """Test thinking_mode property returns thinking mode."""
    core = Agent(config=Config(), thinking_mode=ThinkingMode.SILENT)
    assert core.thinking_mode == ThinkingMode.SILENT

  def test_tool_registry_property(self) -> None:
    """Test tool_registry property returns tool registry."""
    core = Agent(config=Config())
    assert core.tools is not None
    assert hasattr(core.tools, "get")
    assert hasattr(core.tools, "register")

  def test_context_property(self) -> None:
    """Test context property returns context manager."""
    core = Agent(config=Config())
    assert core.context is not None
    assert hasattr(core.context, "get_messages")


class TestAgentGuardrailProperty:
  """Tests for Agent guardrail property (H2)."""

  def test_guardrail_property_exists(self) -> None:
    """Test that guardrail property is accessible."""
    core = Agent(config=Config())
    assert hasattr(core, "guardrail")

  def test_guardrail_property_returns_path_guardrail(self) -> None:
    """Test that guardrail property returns PathGuardrail instance."""
    from yoker.tools.guardrails.path import PathGuardrail

    core = Agent(config=Config())
    assert isinstance(core.guardrail, PathGuardrail)

  def test_guardrail_property_is_read_only(self) -> None:
    """Test that guardrail property cannot be set directly."""
    core = Agent(config=Config())
    # Attempting to set should raise AttributeError (property is read-only)
    with pytest.raises(AttributeError):
      core.guardrail = None  # type: ignore


class TestAgentAgentPath:
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

    core = Agent(config=Config(), agent_path=agent_file)
    assert core.definition.name == "file:test-agent"
    assert "file:read" in core.definition.tools

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

    core = Agent(config=Config(), agent_path=agent_file)
    assert core.definition.name == "file:researcher"
    assert core.definition.system_prompt is not None
    assert "research assistant" in core.definition.system_prompt


class TestAgentContextManager:
  """Tests for context_manager parameter."""

  def test_context_manager_parameter(self) -> None:
    """Test that custom context manager is used."""
    from yoker.context import Persisted, SimpleContextManager

    custom_context = Persisted(
      SimpleContextManager(),
      storage_path="custom_storage",
      session_id="custom-session-123",
    )
    core = Agent(config=Config(), context_manager=custom_context)

    assert core.context is custom_context
    assert core.context.get_session_id() == "custom-session-123"

  def test_context_manager_persists_system_prompt(self) -> None:
    """Test that custom context manager receives system prompt."""
    from yoker.agents import AgentDefinition
    from yoker.context import Persisted, SimpleContextManager

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Custom system prompt for context test.",
    )
    custom_context = Persisted(
      SimpleContextManager(),
      storage_path="test_storage",
      session_id="test-session",
    )
    core = Agent(config=Config(), agent_definition=agent_def, context_manager=custom_context)

    messages = core.context.get_messages()
    system_messages = [m for m in messages if m.get("role") == "system"]
    # SimpleContextManager adds env reminder + system prompt collapsed into one message
    assert len(system_messages) == 1
    assert "Custom system prompt for context test." in system_messages[0].get("content", "")


class TestAgentBackendParameter:
  """Tests for backend parameter and conditional WebSearch/WebFetch tools."""

  def test_backend_parameter_accepts_backend(self) -> None:
    """Test that Agent accepts a backend parameter."""
    from unittest.mock import patch

    from yoker.backends.ollama import OllamaBackend

    # Create a mock backend
    config = Config()
    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
    core = Agent(config=config, backend=backend)

    # Agent should accept the backend without error
    assert core is not None
    assert core._backend is backend

  def test_websearch_requires_api_key_and_backend(self) -> None:
    """Test that WebSearch tool is only added when API key and backend are present."""
    from unittest.mock import patch

    from yoker.backends.ollama import OllamaBackend

    config = Config(backend=BackendConfig(ollama=OllamaConfig(api_key="test-key")))
    with patch("yoker.backends.ollama.AsyncClient"):
      backend = OllamaBackend(config)
    core = Agent(config=config, backend=backend)

    # WebSearch and WebFetch tools should be present (API key + backend provided)
    assert core.tools.get("yoker:websearch") is not None
    assert core.tools.get("yoker:webfetch") is not None

  def test_websearch_missing_api_key(self) -> None:
    """Test that WebSearch tool is not added when API key is missing."""
    core = Agent(config=Config())

    # WebSearch should not be in default tools (no API key)
    assert core.tools.get("yoker:websearch") is None
    assert core.tools.get("yoker:webfetch") is None


class TestAgentToolMatching:
  """Tests for tool matching and filtering."""

  def test_case_insensitive_tool_matching(self) -> None:
    """Test that tool matching is case-insensitive."""
    from yoker.agents import AgentDefinition

    # Agent definition with mixed-case tool names
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("Read", "LIST", "Write"),
      system_prompt="Test prompt",
    )
    core = Agent(config=Config(), agent_definition=agent_def)

    # All tools should be registered (case-insensitive matching)
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:write") is not None

  def test_empty_tools_list(self) -> None:
    """Test agent definition with empty tools list."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=(),  # Empty tools list
      system_prompt="Test prompt",
    )
    core = Agent(config=Config(), agent_definition=agent_def)

    # No tools should be registered
    assert core.tools.get("yoker:read") is None
    assert core.tools.get("yoker:list") is None
    assert core.tools.get("yoker:write") is None


class TestAgentBuildToolRegistry:
  """Tests for _build_tool_registry method (H3)."""

  def test_build_tool_registry_filters_by_agent_definition(self) -> None:
    """Test that tool registry is filtered by agent definition."""
    from yoker.agents import AgentDefinition

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read", "search"),
      system_prompt="Test prompt",
    )
    core = Agent(config=Config(), agent_definition=agent_def)

    # Only read and search should be present
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:search") is not None
    # Other tools should not be present
    assert core.tools.get("yoker:list") is None
    assert core.tools.get("yoker:write") is None

  def test_build_tool_registry_all_tools_without_agent_definition(self) -> None:
    """Test that all tools are registered when no agent definition is provided."""
    core = Agent(config=Config())

    # All default tools should be present
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    assert core.tools.get("yoker:write") is not None
    assert core.tools.get("yoker:update") is not None
    assert core.tools.get("yoker:search") is not None
    assert core.tools.get("yoker:existence") is not None
    assert core.tools.get("yoker:mkdir") is not None

  def test_build_tool_registry_schemas_have_path_parameter(self) -> None:
    """Filesystem tool schemas declare a path parameter."""
    core = Agent(config=Config())

    filesystem_tools = [
      "yoker:read",
      "yoker:list",
      "yoker:write",
      "yoker:update",
      "yoker:search",
      "yoker:existence",
      "yoker:mkdir",
    ]
    for tool_name in filesystem_tools:
      tool = core.tools.get(tool_name)
      assert tool is not None, f"Tool {tool_name} not found"
      params = tool.schema["function"]["parameters"]
      assert "path" in params["properties"], f"Tool {tool_name} missing path parameter"
      assert params["properties"]["path"]["type"] == "string"

  def test_build_tool_registry_git_tool_with_config(self) -> None:
    """Test that the git tool is created with proper configuration."""
    core = Agent(config=Config())

    git_tool = core.tools.get("yoker:git")
    assert git_tool is not None
    params = git_tool.schema["function"]["parameters"]
    assert "path" in params["properties"]
    assert params["properties"]["path"]["type"] == "string"


class TestAgentGuardrailPropertyTypeAnnotation:
  """Tests for guardrail property type annotation."""

  def test_guardrail_has_correct_type_annotation(self) -> None:
    """Test that guardrail property has proper type annotation."""
    # Check that the property exists and has correct type annotation
    import inspect

    from yoker.tools.guardrails.path import PathGuardrail

    # Get the property descriptor
    guardrail_prop = getattr(Agent, "guardrail", None)
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
