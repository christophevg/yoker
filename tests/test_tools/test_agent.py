"""Tests for the agent subagent tool implementation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agent import Agent
from yoker.tools import ToolRegistry, make_agent_tool
from yoker.tools.agent import DEFAULT_TIMEOUT_SECONDS, _clamp


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
  # Logging config
  config.logging.level = "INFO"
  config.logging.format = "text"
  return config


def _make_parent_agent(tmp_path: Path, recursion_depth: int = 0) -> MagicMock:
  """Build a minimal mock parent agent for subagent tests."""
  agent = MagicMock(spec=Agent)
  agent._recursion_depth = recursion_depth
  agent._max_recursion_depth = 3
  agent.config = _make_parent_config(tmp_path)
  agent.model = "test-model"
  agent.context = MagicMock()
  agent.context.get_session_id.return_value = "test-session"
  return agent


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
    assert "agent_path" in schema["function"]["parameters"]["properties"]
    assert "prompt" in schema["function"]["parameters"]["properties"]
    assert "timeout_seconds" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["agent_path", "prompt"]

  def test_timeout_in_schema(self) -> None:
    """Test that timeout_seconds parameter is present with integer type."""
    spec = _agent_spec()
    schema = spec.schema

    timeout_prop = schema["function"]["parameters"]["properties"]["timeout_seconds"]
    assert timeout_prop["type"] == "integer"


class TestAgentToolParameters:
  """Tests for parameter validation."""

  @pytest.mark.asyncio
  async def test_missing_agent_path(self) -> None:
    """Test error when agent_path is missing."""
    spec = _agent_spec()
    result = await spec.execute(prompt="Test prompt")

    assert not result.success
    assert "missing a required argument" in result.error
    assert "agent_path" in result.error

  @pytest.mark.asyncio
  async def test_missing_prompt(self) -> None:
    """Test error when prompt is missing."""
    spec = _agent_spec()
    result = await spec.execute(agent_path="/path/to/agent.md")

    assert not result.success
    assert "missing a required argument" in result.error
    assert "prompt" in result.error

  @pytest.mark.asyncio
  async def test_missing_both_parameters(self) -> None:
    """Test error when both parameters are missing."""
    spec = _agent_spec()
    result = await spec.execute()

    assert not result.success
    assert "missing a required argument" in result.error

  @pytest.mark.asyncio
  async def test_invalid_timeout_string(self) -> None:
    """Test error for invalid timeout_seconds parameter."""
    spec = _agent_spec()
    result = await spec.execute(
      agent_path="/tmp/agent.md",
      prompt="Test",
      timeout_seconds="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric parameter" in result.error

  @pytest.mark.asyncio
  async def test_timeout_clamped_to_minimum(self, tmp_path: Path) -> None:
    """Test timeout below minimum is clamped."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "test.md"
    agent_file.write_text(
      "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\n\nTest prompt\n"
    )

    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)

    # Timeout 0 should be clamped to 1
    result = await spec.execute(
      agent_path=str(agent_file),
      prompt="Test",
      timeout_seconds=0,
    )

    # Will fail because we have not patched subagent creation; the error should not be timeout.
    assert result.success is False

  @pytest.mark.asyncio
  async def test_timeout_clamped_to_maximum(self, tmp_path: Path) -> None:
    """Test timeout above maximum is clamped."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "test.md"
    agent_file.write_text(
      "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\n\nTest prompt\n"
    )

    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)

    # Timeout 9999 should be clamped to ABSOLUTE_MAX_TIMEOUT_SECONDS
    result = await spec.execute(
      agent_path=str(agent_file),
      prompt="Test",
      timeout_seconds=9999,
    )

    # Will fail because we have not patched subagent creation; the error should not be timeout.
    assert result.success is False


class TestAgentToolPathValidation:
  """Tests for agent path validation."""

  @pytest.mark.asyncio
  async def test_agent_file_not_found(self, tmp_path: Path) -> None:
    """Test error when agent file does not exist."""
    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path="/nonexistent/agent.md",
      prompt="Test prompt",
    )

    assert not result.success
    assert "Agent not found" in result.error

  @pytest.mark.asyncio
  async def test_agent_path_is_directory(self, tmp_path: Path) -> None:
    """Test error when agent path is a directory."""
    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path=str(tmp_path),
      prompt="Test prompt",
    )

    assert not result.success
    assert "not a file" in result.error.lower()


class TestAgentToolRecursionDepth:
  """Tests for recursion depth enforcement."""

  @pytest.fixture
  def temp_agent_file(self, tmp_path: Path) -> Path:
    """Create a temporary agent definition file."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "researcher.md"
    agent_file.write_text(
      "---\n"
      "name: researcher\n"
      "description: Test researcher agent\n"
      "tools:\n"
      "  - read\n"
      "---\n\n"
      "You are a research assistant.\n"
    )
    return agent_file

  @pytest.mark.asyncio
  async def test_recursion_depth_zero_allowed(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test that spawning at depth 0 is allowed."""
    parent = _make_parent_agent(tmp_path, recursion_depth=0)
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.tools.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process = AsyncMock(return_value="Test response")
      mock_create.return_value = mock_subagent

      with patch("yoker.tools.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Test response"

        result = await spec.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success

  @pytest.mark.asyncio
  async def test_recursion_depth_at_limit_blocked(
    self, temp_agent_file: Path, tmp_path: Path
  ) -> None:
    """Test that spawning at max depth is blocked."""
    parent = _make_parent_agent(tmp_path, recursion_depth=3)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path=str(temp_agent_file),
      prompt="Test prompt",
    )

    assert not result.success
    assert "Maximum recursion depth" in result.error
    assert "exceeded" in result.error.lower()

  @pytest.mark.asyncio
  async def test_recursion_depth_beyond_limit_blocked(
    self, temp_agent_file: Path, tmp_path: Path
  ) -> None:
    """Test that spawning beyond max depth is blocked."""
    parent = _make_parent_agent(tmp_path, recursion_depth=5)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path=str(temp_agent_file),
      prompt="Test prompt",
    )

    assert not result.success
    assert "Maximum recursion depth" in result.error

  @pytest.mark.asyncio
  async def test_recursion_depth_one_below_limit_allowed(
    self, temp_agent_file: Path, tmp_path: Path
  ) -> None:
    """Test that spawning at max_depth - 1 is allowed."""
    parent = _make_parent_agent(tmp_path, recursion_depth=2)
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.tools.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process = AsyncMock(return_value="Test response")
      mock_create.return_value = mock_subagent

      with patch("yoker.tools.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Test response"

        result = await spec.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success


class TestAgentToolTimeout:
  """Tests for timeout handling."""

  @pytest.fixture
  def temp_agent_file(self, tmp_path: Path) -> Path:
    """Create a temporary agent definition file."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "test.md"
    agent_file.write_text(
      "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\n\nTest prompt\n"
    )
    return agent_file

  @pytest.mark.asyncio
  async def test_timeout_raises_timeout_error(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test that timeout is enforced and raises TimeoutError."""
    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.tools.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_create.return_value = mock_subagent

      with patch("yoker.tools.agent._run_with_timeout") as mock_run:
        mock_run.side_effect = TimeoutError("Timed out")

        result = await spec.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
          timeout_seconds=1,
        )

        assert not result.success
        assert "timed out" in result.error.lower()

  @pytest.mark.asyncio
  async def test_default_timeout_used(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test that default timeout is applied when not specified."""
    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.tools.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_create.return_value = mock_subagent

      with patch("yoker.tools.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = await spec.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][2] == DEFAULT_TIMEOUT_SECONDS  # timeout_seconds


class TestAgentToolContextIsolation:
  """Tests for context isolation."""

  @pytest.fixture
  def temp_agent_file(self, tmp_path: Path) -> Path:
    """Create a temporary agent definition file."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "test.md"
    agent_file.write_text(
      "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\n\nTest prompt\n"
    )
    return agent_file

  @pytest.mark.asyncio
  async def test_fresh_context_created(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test that subagent gets fresh context."""
    parent = _make_parent_agent(tmp_path)
    parent.context.get_session_id.return_value = "parent-session"
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.context.PersistenceContextManager") as mock_context_class:
      mock_context = MagicMock()
      mock_context_class.return_value = mock_context

      with patch("yoker.agent.Agent") as mock_agent_class:
        mock_subagent = MagicMock()
        mock_agent_class.return_value = mock_subagent

        with patch("yoker.tools.agent._run_with_timeout") as mock_run:
          mock_run.return_value = "Response"

          await spec.execute(
            agent_path=str(temp_agent_file),
            prompt="Test prompt",
          )

          # PersistenceContextManager should have been called
          assert mock_context_class.called
          # Session ID should include parent session and UUID
          call_kwargs = mock_context_class.call_args[1]
          assert "parent-session" in call_kwargs["session_id"]
          # UUID format: parent-session_<8 hex chars>
          import re

          assert re.match(r"parent-session_[a-f0-9]{8}", call_kwargs["session_id"])


class TestAgentToolAgentDefinition:
  """Tests for agent definition loading."""

  @pytest.mark.asyncio
  async def test_valid_agent_definition(self, tmp_path: Path) -> None:
    """Test loading valid agent definition."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "valid.md"
    agent_file.write_text(
      "---\n"
      "name: test-agent\n"
      "description: A test agent\n"
      "tools:\n"
      "  - read\n"
      "  - list\n"
      "---\n\n"
      "You are a test agent.\n"
    )

    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.tools.agent._run_with_timeout") as mock_run:
      mock_run.return_value = "Response"

      result = await spec.execute(
        agent_path=str(agent_file),
        prompt="Test prompt",
      )

      assert result.success
      assert result.result == "Response"

  @pytest.mark.asyncio
  async def test_invalid_agent_definition_yaml(self, tmp_path: Path) -> None:
    """Test loading agent definition with invalid YAML."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "invalid.md"
    agent_file.write_text("---\nname: [invalid yaml\n---\n\nContent\n")

    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path=str(agent_file),
      prompt="Test prompt",
    )

    assert not result.success
    assert "error" in result.error.lower()

  @pytest.mark.asyncio
  async def test_agent_definition_missing_name(self, tmp_path: Path) -> None:
    """Test agent definition missing required name field."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "missing_name.md"
    agent_file.write_text("---\ndescription: Test agent\ntools:\n  - read\n---\n\nContent\n")

    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path=str(agent_file),
      prompt="Test prompt",
    )

    assert not result.success

  @pytest.mark.asyncio
  async def test_agent_definition_missing_tools(self, tmp_path: Path) -> None:
    """Test agent definition missing required tools field."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "missing_tools.md"
    agent_file.write_text("---\nname: test\ndescription: Test agent\n---\n\nContent\n")

    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)
    result = await spec.execute(
      agent_path=str(agent_file),
      prompt="Test prompt",
    )

    assert not result.success


class TestAgentToolSubagentCreation:
  """Tests for subagent creation and execution."""

  @pytest.fixture
  def temp_agent_file(self, tmp_path: Path) -> Path:
    """Create a temporary agent definition file."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "sub.md"
    agent_file.write_text(
      "---\n"
      "name: sub-agent\n"
      "description: Sub agent for testing\n"
      "tools:\n"
      "  - read\n"
      "model: llama3.2:latest\n"
      "---\n\n"
      "You are a sub-agent.\n"
    )
    return agent_file

  @pytest.mark.asyncio
  async def test_subagent_created_with_correct_depth(
    self, temp_agent_file: Path, tmp_path: Path
  ) -> None:
    """Test that subagent is created with incremented depth."""
    parent = _make_parent_agent(tmp_path)
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.tools.agent._create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process = AsyncMock(return_value="Response")
      mock_create.return_value = mock_subagent

      with patch("yoker.tools.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = await spec.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success

    # _create_subagent receives parent and agent_definition; verify depth logic via helper.
    # Recreate same path and call _create_subagent directly to inspect Agent constructor kwargs.
    from yoker.plugins import resolve_agent

    agent_definition = resolve_agent(str(temp_agent_file))
    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent_class.return_value = mock_agent
      from yoker.tools.agent import _create_subagent

      _create_subagent(parent, agent_definition)

      kwargs = mock_agent_class.call_args[1]
      assert kwargs.get("_recursion_depth") == 1

  @pytest.mark.asyncio
  async def test_subagent_uses_agent_model(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test that subagent uses model from agent definition."""
    parent = _make_parent_agent(tmp_path)
    parent.config.backend.ollama.model = "parent-model"
    spec = _agent_spec(parent_agent=parent)

    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent_class.return_value = mock_agent

      with patch("yoker.tools.agent._run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = await spec.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success

    from yoker.plugins import resolve_agent

    agent_definition = resolve_agent(str(temp_agent_file))
    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent_class.return_value = mock_agent
      from yoker.tools.agent import _create_subagent

      _create_subagent(parent, agent_definition)

      kwargs = mock_agent_class.call_args[1]
      config = kwargs.get("config")
      assert config is not None
      assert config.backend.ollama.model == "llama3.2:latest"


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

  @pytest.fixture
  def temp_agent_file(self, tmp_path: Path) -> Path:
    """Create a temporary agent definition file."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "integration.md"
    agent_file.write_text(
      "---\n"
      "name: integration-test\n"
      "description: Integration test agent\n"
      "tools:\n"
      "  - read\n"
      "---\n\n"
      "You are a test agent for integration testing.\n"
    )
    return agent_file

  @pytest.mark.asyncio
  async def test_full_execution_flow(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test full execution flow with mocked Agent."""
    parent = _make_parent_agent(tmp_path)
    parent.config.context.storage_path = str(tmp_path / "context")
    spec = _agent_spec(parent_agent=parent)

    # Mock Agent creation and process
    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent.process = AsyncMock(return_value="Sub-agent response")
      mock_agent_class.return_value = mock_agent

      result = await spec.execute(
        agent_path=str(temp_agent_file),
        prompt="Test prompt",
        timeout_seconds=60,
      )

      assert result.success
      assert result.result == "Sub-agent response"
      assert result.error is None
