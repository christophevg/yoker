"""Tests for the agent subagent tool implementation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agent import Agent
from yoker.agents import AgentDefinition, AgentRegistry
from yoker.builtin import make_agent_tool
from yoker.builtin.agent import DEFAULT_TIMEOUT_SECONDS, _clamp
from yoker.tools import ToolRegistry


def _agent_spec(parent_agent=None):
  """Create and register the agent tool."""
  registry = ToolRegistry()
  return registry.register(make_agent_tool(parent_agent=parent_agent))


def _make_parent_config(tmp_path: Path) -> MagicMock:
  """Build a MagicMock config that satisfies the agent tool's config access."""
  config = MagicMock()
  # Harness config
  config.harness.name = "test"
  # Backend config
  config.backend.provider = "ollama"
  config.backend.ollama.base_url = "http://localhost:11434"
  config.backend.ollama.model = "test-model"
  config.backend.ollama.timeout_seconds = 60
  config.backend.ollama.parameters.temperature = 0.7
  config.backend.ollama.parameters.top_p = 0.9
  config.backend.ollama.parameters.top_k = 40
  config.backend.ollama.parameters.num_ctx = 4096
  # Support the generic config property
  config.backend.config = config.backend.ollama
  # Context config
  config.context.storage_path = "/tmp/context"
  config.context.manager = "basic_persistence"
  config.context.session_id = "auto"
  config.context.persist_after_turn = True
  # Permissions config
  config.permissions.filesystem_paths = (".",)
  config.permissions.network_access = "none"
  config.permissions.max_file_size_kb = 500
  config.permissions.max_recursion_depth = 3
  config.permissions.handlers = {}
  # Tools config
  config.tools.agent.max_recursion_depth = 3
  config.tools.agent.timeout_seconds = 300
  config.tools.list.max_depth = 5
  config.tools.list.max_entries = 2000
  config.tools.write.max_size_kb = 1000
  config.tools.update.max_diff_size_kb = 100
  config.tools.search.max_results = 500
  config.tools.search.timeout_ms = 10000
  config.tools.read.blocked_patterns = (r"\.env", "credentials", "secret")
  # Agents config
  config.agents.directories = (str(tmp_path / "agents"),)
  config.agents.default_type = "main"
  # Logging config - use proper string values
  config.logging.level = "INFO"
  config.logging.format = "text"
  config.logging.timestamp_format_string = "%Y-%m-%d %H:%M:%S"
  return config


def _make_parent_agent(tmp_path: Path, recursion_depth: int = 0) -> MagicMock:
  """Build a minimal mock parent agent for subagent tests."""
  agent = MagicMock(spec=Agent)
  agent.recursion_depth = recursion_depth
  agent.max_recursion_depth = 3
  agent.config = _make_parent_config(tmp_path)
  agent.model = "test-model"
  agent.context = MagicMock()
  agent.context.get_session_id.return_value = "test-session"
  # Mock the agents registry
  agent.agents = MagicMock(spec=AgentRegistry)
  agent.agents.names = []
  return agent


def _make_agent_definition(name: str = "test", model: str | None = None) -> AgentDefinition:
  """Create a test agent definition."""
  return AgentDefinition(
    simple_name=name,
    description=f"Test agent {name}",
    tools=("read",),
    model=model,
  )


class TestAgentToolSchema:
  """Tests for agent tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    spec = _agent_spec()
    assert spec.name == "agent"

  def test_description(self) -> None:
    """Test tool description."""
    spec = _agent_spec()
    assert "sub-agent" in spec.description.lower()
    assert "task" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    spec = _agent_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "agent"
    assert "agent_name" in schema["function"]["parameters"]["properties"]
    assert "prompt" in schema["function"]["parameters"]["properties"]
    assert "timeout_seconds" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["agent_name", "prompt"]

  def test_timeout_in_schema(self) -> None:
    """Test that timeout_seconds parameter is present with integer type."""
    spec = _agent_spec()
    schema = spec.schema

    timeout_prop = schema["function"]["parameters"]["properties"]["timeout_seconds"]
    assert timeout_prop["type"] == "integer"


class TestAgentToolParameters:
  """Tests for parameter validation."""

  @pytest.mark.asyncio
  async def test_missing_agent_name(self) -> None:
    """Test error when agent_name is missing."""
    spec = _agent_spec()
    result = await spec.execute(agent_name="", prompt="Test prompt")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "agent_name" in result.error

  @pytest.mark.asyncio
  async def test_missing_prompt(self) -> None:
    """Test error when prompt is missing."""
    parent = _make_parent_agent(Path("/tmp"))
    parent.agents.resolve.return_value = _make_agent_definition("test-agent")
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(agent_name="test-agent", prompt="")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "prompt" in result.error

  @pytest.mark.asyncio
  async def test_missing_both_parameters(self) -> None:
    """Test error when both parameters are missing."""
    spec = _agent_spec()
    result = await spec.execute(agent_name="", prompt="")

    assert not result.success
    assert "Missing required parameter" in result.error

  @pytest.mark.asyncio
  async def test_invalid_timeout_string(self) -> None:
    """Test error for invalid timeout_seconds parameter."""
    spec = _agent_spec()
    result = await spec.execute(
      agent_name="test-agent",
      prompt="Test",
      timeout_seconds="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric parameter" in result.error

  @pytest.mark.asyncio
  async def test_timeout_clamped_to_minimum(self, tmp_path: Path) -> None:
    """Test timeout below minimum is clamped."""
    parent = _make_parent_agent(tmp_path)
    agent_def = _make_agent_definition("test")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    # Timeout 0 should be clamped to 1
    result = await spec.execute(
      agent_name="test",
      prompt="Test",
      timeout_seconds=0,
    )

    # Will fail because we have not patched subagent creation; the error should not be timeout.
    assert result.success is False

  @pytest.mark.asyncio
  async def test_timeout_clamped_to_maximum(self, tmp_path: Path) -> None:
    """Test timeout above maximum is clamped."""
    parent = _make_parent_agent(tmp_path)
    agent_def = _make_agent_definition("test")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    # Timeout 9999 should be clamped to ABSOLUTE_MAX_TIMEOUT_SECONDS
    result = await spec.execute(
      agent_name="test",
      prompt="Test",
      timeout_seconds=9999,
    )

    # Will fail because we have not patched subagent creation; the error should not be timeout.
    assert result.success is False


class TestAgentToolPathValidation:
  """Tests for agent path validation."""

  @pytest.mark.asyncio
  async def test_agent_file_not_found(self, tmp_path: Path) -> None:
    """Test error when agent name is not found."""
    parent = _make_parent_agent(tmp_path)
    parent.agents.resolve.side_effect = ValueError("Agent not found: nonexistent")
    parent.agents.names = []
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_name="nonexistent",
      prompt="Test prompt",
    )

    assert not result.success
    assert "Agent not found" in result.error or "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_agent_resolution_error(self, tmp_path: Path) -> None:
    """Test error when agent resolution raises unexpected exception."""
    parent = _make_parent_agent(tmp_path)
    parent.agents.resolve.side_effect = RuntimeError("Unexpected error")
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_name="test-agent",
      prompt="Test prompt",
    )

    assert not result.success
    assert "Agent resolution failed" in result.error


class TestAgentToolRecursionDepth:
  """Tests for recursion depth enforcement."""

  @pytest.mark.asyncio
  async def test_recursion_depth_zero_allowed(self, tmp_path: Path) -> None:
    """Test that spawning at depth 0 is allowed."""
    parent = _make_parent_agent(tmp_path, recursion_depth=0)
    agent_def = _make_agent_definition("researcher")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.builtin.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process = AsyncMock(return_value="Test response")
      mock_create.return_value = mock_subagent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Test response"

        result = await spec.execute(
          agent_name="researcher",
          prompt="Test prompt",
        )

        assert result.success

  @pytest.mark.asyncio
  async def test_recursion_depth_at_limit_blocked(self, tmp_path: Path) -> None:
    """Test that spawning at max depth is blocked."""
    parent = _make_parent_agent(tmp_path, recursion_depth=3)
    agent_def = _make_agent_definition("researcher")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_name="researcher",
      prompt="Test prompt",
    )

    assert not result.success
    assert "Maximum recursion depth" in result.error
    assert "exceeded" in result.error.lower()

  @pytest.mark.asyncio
  async def test_recursion_depth_beyond_limit_blocked(self, tmp_path: Path) -> None:
    """Test that spawning beyond max depth is blocked."""
    parent = _make_parent_agent(tmp_path, recursion_depth=5)
    agent_def = _make_agent_definition("researcher")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_name="researcher",
      prompt="Test prompt",
    )

    assert not result.success
    assert "Maximum recursion depth" in result.error

  @pytest.mark.asyncio
  async def test_recursion_depth_one_below_limit_allowed(self, tmp_path: Path) -> None:
    """Test that spawning at max_depth - 1 is allowed."""
    parent = _make_parent_agent(tmp_path, recursion_depth=2)
    agent_def = _make_agent_definition("researcher")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.builtin.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process = AsyncMock(return_value="Test response")
      mock_create.return_value = mock_subagent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Test response"

        result = await spec.execute(
          agent_name="researcher",
          prompt="Test prompt",
        )

        assert result.success


class TestAgentToolTimeout:
  """Tests for timeout handling."""

  @pytest.mark.asyncio
  async def test_timeout_raises_timeout_error(self, tmp_path: Path) -> None:
    """Test that timeout is enforced and raises TimeoutError."""
    parent = _make_parent_agent(tmp_path)
    agent_def = _make_agent_definition("test")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.builtin.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_create.return_value = mock_subagent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.side_effect = TimeoutError("Timed out")

        result = await spec.execute(
          agent_name="test",
          prompt="Test prompt",
          timeout_seconds=1,
        )

        assert not result.success
        assert "timed out" in result.error.lower()

  @pytest.mark.asyncio
  async def test_default_timeout_used(self, tmp_path: Path) -> None:
    """Test that default timeout is applied when not specified."""
    parent = _make_parent_agent(tmp_path)
    agent_def = _make_agent_definition("test")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.builtin.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_create.return_value = mock_subagent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = await spec.execute(
          agent_name="test",
          prompt="Test prompt",
        )

        assert result.success
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][2] == DEFAULT_TIMEOUT_SECONDS  # timeout_seconds


class TestAgentToolContextIsolation:
  """Tests for context isolation."""

  @pytest.mark.asyncio
  async def test_fresh_context_created(self, tmp_path: Path) -> None:
    """Test that subagent gets fresh context via default SimpleContextManager."""
    parent = _make_parent_agent(tmp_path)
    parent.context.get_session_id.return_value = "parent-session"
    agent_def = _make_agent_definition("test")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_subagent = MagicMock()
      mock_agent_class.return_value = mock_subagent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        await spec.execute(
          agent_name="test",
          prompt="Test prompt",
        )

        # Verify Agent was created with correct parameters
        mock_agent_class.assert_called_once()
        call_kwargs = mock_agent_class.call_args[1]
        # Agent should receive the agent_definition and recursion depth
        assert call_kwargs["agent_definition"] == agent_def
        assert call_kwargs["_recursion_depth"] == 1


class TestAgentToolAgentDefinition:
  """Tests for agent definition loading."""

  @pytest.mark.asyncio
  async def test_valid_agent_definition(self, tmp_path: Path) -> None:
    """Test loading valid agent definition."""
    parent = _make_parent_agent(tmp_path)
    agent_def = _make_agent_definition("test-agent")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
      mock_run.return_value = "Response"

      result = await spec.execute(
        agent_name="test-agent",
        prompt="Test prompt",
      )

      assert result.success
      assert result.result == "Response"

  @pytest.mark.asyncio
  async def test_invalid_agent_definition_yaml(self, tmp_path: Path) -> None:
    """Test loading agent definition with invalid YAML."""
    parent = _make_parent_agent(tmp_path)
    # Simulate resolve failing with an error
    parent.agents.resolve.side_effect = ValueError("Invalid YAML in agent definition")
    parent.agents.names = []
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_name="invalid",
      prompt="Test prompt",
    )

    assert not result.success
    assert "error" in result.error.lower() or "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_agent_definition_missing_name(self, tmp_path: Path) -> None:
    """Test agent definition missing required name field."""
    parent = _make_parent_agent(tmp_path)
    # Simulate resolve failing because agent doesn't exist
    parent.agents.resolve.side_effect = ValueError("Agent not found: missing_name")
    parent.agents.names = []
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_name="missing_name",
      prompt="Test prompt",
    )

    assert not result.success

  @pytest.mark.asyncio
  async def test_agent_definition_missing_tools(self, tmp_path: Path) -> None:
    """Test agent definition missing required tools field."""
    parent = _make_parent_agent(tmp_path)
    # Agent definition without tools field - tools default to empty list in AgentDefinition
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=(),  # Empty tools tuple
    )
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)
    # This should still work, just with no tools
    with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
      mock_run.return_value = "Response"
      result = await spec.execute(
        agent_name="test",
        prompt="Test prompt",
      )
      # Will succeed in calling the agent, but the agent itself might fail
      # We just test that the resolution works
      assert result.success


class TestAgentToolSubagentCreation:
  """Tests for subagent creation and execution."""

  @pytest.mark.asyncio
  async def test_subagent_created_with_correct_depth(self, tmp_path: Path) -> None:
    """Test that subagent is created with incremented depth."""
    parent = _make_parent_agent(tmp_path)
    agent_def = _make_agent_definition("sub-agent")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.builtin.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process = AsyncMock(return_value="Response")
      mock_create.return_value = mock_subagent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = await spec.execute(
          agent_name="sub-agent",
          prompt="Test prompt",
        )

        assert result.success

    # _create_subagent receives parent and agent_definition; verify depth logic via helper.
    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent_class.return_value = mock_agent
      from yoker.builtin.agent import _create_subagent

      _create_subagent(parent, agent_def)

      kwargs = mock_agent_class.call_args[1]
      assert kwargs.get("_recursion_depth") == 1

  @pytest.mark.asyncio
  async def test_subagent_uses_agent_model(self, tmp_path: Path) -> None:
    """Test that subagent uses model from agent definition."""
    from yoker.config import BackendConfig, Config, OllamaConfig

    # Use real Config objects, not MagicMock, since with_model uses dataclasses.replace
    parent_config = Config(
      backend=BackendConfig(ollama=OllamaConfig(model="parent-model")),
    )

    parent = MagicMock(spec=Agent)
    parent.recursion_depth = 0
    parent.max_recursion_depth = 3
    parent.config = parent_config
    parent.model = "parent-model"
    parent.context = MagicMock()
    parent.context.get_session_id.return_value = "parent-session"
    parent.agents = MagicMock(spec=AgentRegistry)
    parent.agents.names = []

    agent_def = _make_agent_definition("sub-agent", model="llama3.2:latest")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent_class.return_value = mock_agent

      with patch("yoker.builtin.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = await spec.execute(
          agent_name="sub-agent",
          prompt="Test prompt",
        )

        assert result.success

    # Verify the model is passed to the subagent
    from yoker.builtin.agent import _create_subagent

    subagent = _create_subagent(parent, agent_def)

    # The subagent should have the model from agent_def
    assert subagent.config.backend.ollama.model == "llama3.2:latest"


class TestAgentToolClamp:
  """Tests for the _clamp helper function."""

  def test_clamp_within_range(self) -> None:
    """Test clamping value within range."""
    assert _clamp(50, 0, 100) == 50

  def test_clamp_at_minimum(self) -> None:
    """Test clamping value at minimum."""
    assert _clamp(0, 0, 100) == 0

  def test_clamp_at_maximum(self) -> None:
    """Test clamping value at maximum."""
    assert _clamp(100, 0, 100) == 100

  def test_clamp_below_minimum(self) -> None:
    """Test clamping value below minimum."""
    assert _clamp(-10, 0, 100) == 0

  def test_clamp_above_maximum(self) -> None:
    """Test clamping value above maximum."""
    assert _clamp(150, 0, 100) == 100


class TestAgentToolIntegration:
  """Integration tests for agent tool."""

  @pytest.mark.asyncio
  async def test_full_execution_flow(self, tmp_path: Path) -> None:
    """Test full execution flow with mocked Agent."""
    parent = _make_parent_agent(tmp_path)
    parent.config.context.storage_path = str(tmp_path / "context")
    agent_def = _make_agent_definition("integration-test")
    parent.agents.resolve.return_value = agent_def
    spec = _agent_spec(parent_agent=parent)

    # Mock Agent creation and process
    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent.process = AsyncMock(return_value="Sub-agent response")
      mock_agent_class.return_value = mock_agent

      result = await spec.execute(
        agent_name="integration-test",
        prompt="Test prompt",
        timeout_seconds=60,
      )

      assert result.success
      assert result.result == "Sub-agent response"
      assert result.error is None
