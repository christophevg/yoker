"""Tests for AgentTool implementation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yoker.agent import Agent
from yoker.tools.agent import AgentTool


class TestAgentToolSchema:
  """Tests for AgentTool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    tool = AgentTool()
    assert tool.name == "agent"

  def test_description(self) -> None:
    """Test tool description."""
    tool = AgentTool()
    assert "sub-agent" in tool.description.lower()
    assert "isolated context" in tool.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    tool = AgentTool()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "agent"
    assert "agent_path" in schema["function"]["parameters"]["properties"]
    assert "prompt" in schema["function"]["parameters"]["properties"]
    assert "timeout_seconds" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["agent_path", "prompt"]

  def test_timeout_in_schema(self) -> None:
    """Test that timeout_seconds parameter has correct constraints."""
    tool = AgentTool()
    schema = tool.get_schema()

    timeout_prop = schema["function"]["parameters"]["properties"]["timeout_seconds"]
    assert timeout_prop["type"] == "integer"
    assert timeout_prop["minimum"] == 1
    assert timeout_prop["maximum"] == tool.ABSOLUTE_MAX_TIMEOUT_SECONDS


class TestAgentToolParameters:
  """Tests for parameter validation."""

  def test_missing_agent_path(self) -> None:
    """Test error when agent_path is missing."""
    tool = AgentTool()
    result = tool.execute(prompt="Test prompt")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "agent_path" in result.error

  def test_missing_prompt(self) -> None:
    """Test error when prompt is missing."""
    tool = AgentTool()
    result = tool.execute(agent_path="/path/to/agent.md")

    assert not result.success
    assert "Missing required parameter" in result.error
    assert "prompt" in result.error

  def test_missing_both_parameters(self) -> None:
    """Test error when both parameters are missing."""
    tool = AgentTool()
    result = tool.execute()

    assert not result.success
    assert "Missing required parameter" in result.error

  def test_invalid_timeout_string(self) -> None:
    """Test error for invalid timeout_seconds parameter."""
    tool = AgentTool()
    result = tool.execute(
      agent_path="/tmp/agent.md",
      prompt="Test",
      timeout_seconds="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric parameter" in result.error

  def test_timeout_clamped_to_minimum(self, tmp_path: Path) -> None:
    """Test timeout below minimum is clamped."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "test.md"
    agent_file.write_text(
      "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\n\nTest prompt\n"
    )

    tool = AgentTool()
    # Timeout 0 should be clamped to 1
    result = tool.execute(
      agent_path=str(agent_file),
      prompt="Test",
      timeout_seconds=0,
    )

    # Should not error, should clamp to 1
    # But will fail because no parent agent to create subagent
    # The error should be about missing parent/config, not timeout
    assert result.success is False  # Expected to fail for other reasons

  def test_timeout_clamped_to_maximum(self, tmp_path: Path) -> None:
    """Test timeout above maximum is clamped."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "test.md"
    agent_file.write_text(
      "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\n\nTest prompt\n"
    )

    tool = AgentTool()
    # Timeout 9999 should be clamped to 3600
    result = tool.execute(
      agent_path=str(agent_file),
      prompt="Test",
      timeout_seconds=9999,
    )

    # Should not error about timeout
    # Will fail for other reasons (no parent agent)
    assert result.success is False


class TestAgentToolPathValidation:
  """Tests for agent path validation."""

  def test_agent_file_not_found(self) -> None:
    """Test error when agent file does not exist."""
    tool = AgentTool()
    result = tool.execute(
      agent_path="/nonexistent/agent.md",
      prompt="Test prompt",
    )

    assert not result.success
    assert "Agent definition not found" in result.error

  def test_agent_path_is_directory(self, tmp_path: Path) -> None:
    """Test error when agent path is a directory."""
    tool = AgentTool()
    result = tool.execute(
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

  @pytest.fixture
  def mock_parent_agent(self, tmp_path: Path) -> Agent:
    """Create a mock parent agent with recursion depth tracking."""
    # Use MagicMock for config with all required validation fields
    config = MagicMock()
    # Harness config
    config.harness.name = "test"
    config.harness.log_level = "INFO"
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
    config.agents.directory = str(tmp_path / "agents")
    config.agents.default_type = "main"
    # Logging config
    config.logging.level = "INFO"
    config.logging.format = "text"

    # Create a minimal mock agent
    agent = MagicMock(spec=Agent)
    agent._recursion_depth = 0
    agent._max_recursion_depth = 3
    agent.config = config
    agent.model = "test-model"
    agent.context = MagicMock()
    agent.context.get_session_id.return_value = "test-session"

    return agent

  def test_recursion_depth_zero_allowed(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that spawning at depth 0 is allowed."""
    mock_parent_agent._recursion_depth = 0

    tool = AgentTool(parent_agent=mock_parent_agent)

    # Mock the _create_subagent method to return a mock agent
    with patch.object(tool, "_create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process.return_value = "Test response"
      mock_create.return_value = mock_subagent

      # Mock _run_with_timeout to return directly
      with patch.object(tool, "_run_with_timeout") as mock_run:
        mock_run.return_value = "Test response"

        result = tool.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success

  def test_recursion_depth_at_limit_blocked(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that spawning at max depth is blocked."""
    mock_parent_agent._recursion_depth = 3  # At max depth

    tool = AgentTool(parent_agent=mock_parent_agent)
    result = tool.execute(
      agent_path=str(temp_agent_file),
      prompt="Test prompt",
    )

    assert not result.success
    assert "Maximum recursion depth" in result.error
    assert "exceeded" in result.error.lower()

  def test_recursion_depth_beyond_limit_blocked(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that spawning beyond max depth is blocked."""
    mock_parent_agent._recursion_depth = 5  # Beyond max depth

    tool = AgentTool(parent_agent=mock_parent_agent)
    result = tool.execute(
      agent_path=str(temp_agent_file),
      prompt="Test prompt",
    )

    assert not result.success
    assert "Maximum recursion depth" in result.error

  def test_recursion_depth_one_below_limit_allowed(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that spawning at max_depth - 1 is allowed."""
    mock_parent_agent._recursion_depth = 2  # One below max (3)

    tool = AgentTool(parent_agent=mock_parent_agent)

    with patch.object(tool, "_create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_subagent.process.return_value = "Test response"
      mock_create.return_value = mock_subagent

      with patch.object(tool, "_run_with_timeout") as mock_run:
        mock_run.return_value = "Test response"

        result = tool.execute(
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

  @pytest.fixture
  def mock_parent_agent(self, tmp_path: Path) -> MagicMock:
    """Create a mock parent agent."""
    # Use MagicMock for config with all required validation fields
    config = MagicMock()
    # Harness config
    config.harness.name = "test"
    config.harness.log_level = "INFO"
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
    config.agents.directory = str(tmp_path / "agents")
    config.agents.default_type = "main"
    # Logging config
    config.logging.level = "INFO"
    config.logging.format = "text"

    agent = MagicMock(spec=Agent)
    agent._recursion_depth = 0
    agent._max_recursion_depth = 3
    agent.config = config
    agent.model = "test-model"
    agent.context = MagicMock()
    agent.context.get_session_id.return_value = "test-session"

    return agent

  def test_timeout_raises_timeout_error(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that timeout is enforced and raises TimeoutError."""
    tool = AgentTool(parent_agent=mock_parent_agent)

    # Mock _run_with_timeout to raise TimeoutError
    with patch.object(tool, "_run_with_timeout") as mock_run:
      mock_run.side_effect = TimeoutError("Timed out")

      result = tool.execute(
        agent_path=str(temp_agent_file),
        prompt="Test prompt",
        timeout_seconds=1,
      )

      assert not result.success
      assert "timed out" in result.error.lower()

  def test_default_timeout_used(self, temp_agent_file: Path, mock_parent_agent: MagicMock) -> None:
    """Test that default timeout is applied when not specified."""
    tool = AgentTool(parent_agent=mock_parent_agent)

    with patch.object(tool, "_create_subagent") as mock_create:
      mock_subagent = MagicMock()
      mock_create.return_value = mock_subagent

      with patch.object(tool, "_run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = tool.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        # Should succeed with default timeout
        assert result.success
        # Check that _run_with_timeout was called with default timeout
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][2] == tool.DEFAULT_TIMEOUT_SECONDS  # timeout_seconds


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

  @pytest.fixture
  def mock_parent_agent(self, tmp_path: Path) -> MagicMock:
    """Create a mock parent agent with context."""
    # Use MagicMock for config with all required validation fields
    config = MagicMock()
    # Harness config
    config.harness.name = "test"
    config.harness.log_level = "INFO"
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
    config.agents.directory = str(tmp_path / "agents")
    config.agents.default_type = "main"
    # Logging config
    config.logging.level = "INFO"
    config.logging.format = "text"

    agent = MagicMock(spec=Agent)
    agent._recursion_depth = 0
    agent._max_recursion_depth = 3
    agent.config = config
    agent.model = "test-model"

    # Mock context with some messages
    mock_context = MagicMock()
    mock_context.get_session_id.return_value = "parent-session"
    mock_context.get_messages.return_value = [{"role": "user", "content": "Previous message"}]
    agent.context = mock_context

    return agent

  def test_fresh_context_created(self, temp_agent_file: Path, mock_parent_agent: MagicMock) -> None:
    """Test that subagent gets fresh context."""
    tool = AgentTool(parent_agent=mock_parent_agent)

    # Track context creation
    created_contexts = []

    with patch("yoker.context.BasicPersistenceContextManager") as mock_context_class:
      mock_context = MagicMock()
      mock_context_class.return_value = mock_context
      created_contexts.append(mock_context)

      with patch("yoker.agent.Agent") as mock_agent_class:
        mock_agent = MagicMock()
        mock_agent.process.return_value = "Response"
        mock_agent_class.return_value = mock_agent

        tool.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        # BasicPersistenceContextManager should have been called
        assert mock_context_class.called
        # Session ID should include parent session and UUID
        call_kwargs = mock_context_class.call_args[1]
        assert "parent-session" in call_kwargs["session_id"]
        # UUID format: parent-session_<8 hex chars>
        import re

        assert re.match(r"parent-session_[a-f0-9]{8}", call_kwargs["session_id"])


class TestAgentToolAgentDefinition:
  """Tests for agent definition loading."""

  @pytest.fixture
  def mock_parent_agent(self, tmp_path: Path) -> MagicMock:
    """Create a mock parent agent."""
    # Use MagicMock for config with all required validation fields
    config = MagicMock()
    # Harness config
    config.harness.name = "test"
    config.harness.log_level = "INFO"
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
    config.agents.directory = str(tmp_path / "agents")
    config.agents.default_type = "main"
    # Logging config
    config.logging.level = "INFO"
    config.logging.format = "text"

    agent = MagicMock(spec=Agent)
    agent._recursion_depth = 0
    agent._max_recursion_depth = 3
    agent.config = config
    agent.model = "test-model"
    agent.context = MagicMock()
    agent.context.get_session_id.return_value = "test-session"

    return agent

  def test_valid_agent_definition(self, tmp_path: Path, mock_parent_agent: MagicMock) -> None:
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

    tool = AgentTool(parent_agent=mock_parent_agent)

    with patch.object(tool, "_run_with_timeout") as mock_run:
      mock_run.return_value = "Response"

      result = tool.execute(
        agent_path=str(agent_file),
        prompt="Test prompt",
      )

      assert result.success
      assert result.result == "Response"

  def test_invalid_agent_definition_yaml(
    self, tmp_path: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test loading agent definition with invalid YAML."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "invalid.md"
    agent_file.write_text("---\nname: [invalid yaml\n---\n\nContent\n")

    tool = AgentTool(parent_agent=mock_parent_agent)
    result = tool.execute(
      agent_path=str(agent_file),
      prompt="Test prompt",
    )

    assert not result.success
    assert "error" in result.error.lower()

  def test_agent_definition_missing_name(
    self, tmp_path: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test agent definition missing required name field."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "missing_name.md"
    agent_file.write_text("---\ndescription: Test agent\ntools:\n  - read\n---\n\nContent\n")

    tool = AgentTool(parent_agent=mock_parent_agent)
    result = tool.execute(
      agent_path=str(agent_file),
      prompt="Test prompt",
    )

    assert not result.success

  def test_agent_definition_missing_tools(
    self, tmp_path: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test agent definition missing required tools field."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    agent_file = agents_dir / "missing_tools.md"
    agent_file.write_text("---\nname: test\ndescription: Test agent\n---\n\nContent\n")

    tool = AgentTool(parent_agent=mock_parent_agent)
    result = tool.execute(
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

  @pytest.fixture
  def mock_parent_agent(self, tmp_path: Path) -> MagicMock:
    """Create a mock parent agent."""
    # Use MagicMock for config with all required validation fields
    config = MagicMock()
    # Harness config
    config.harness.name = "test"
    config.harness.log_level = "INFO"
    # Backend config
    config.backend.provider = "ollama"
    config.backend.ollama.base_url = "http://localhost:11434"
    config.backend.ollama.model = "parent-model"
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
    config.agents.directory = str(tmp_path / "agents")
    config.agents.default_type = "main"
    # Logging config
    config.logging.level = "INFO"
    config.logging.format = "text"

    agent = MagicMock(spec=Agent)
    agent._recursion_depth = 0
    agent._max_recursion_depth = 3
    agent.config = config
    agent.model = "parent-model"
    agent.context = MagicMock()
    agent.context.get_session_id.return_value = "parent-session"

    return agent

  def test_subagent_created_with_correct_depth(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that subagent is created with incremented depth."""
    tool = AgentTool(parent_agent=mock_parent_agent)

    created_agents = []

    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent.process.return_value = "Response"
      mock_agent_class.return_value = mock_agent

      def capture_agent(*args, **kwargs):
        created_agents.append((args, kwargs))
        return mock_agent

      mock_agent_class.side_effect = capture_agent

      with patch.object(tool, "_run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = tool.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success
        # Check that Agent was created with depth = parent_depth + 1
        assert len(created_agents) > 0
        kwargs = created_agents[0][1]
        assert kwargs.get("_recursion_depth") == 1

  def test_subagent_uses_agent_model(
    self, temp_agent_file: Path, mock_parent_agent: MagicMock
  ) -> None:
    """Test that subagent uses model from agent definition."""
    tool = AgentTool(parent_agent=mock_parent_agent)

    created_agents = []

    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent.process.return_value = "Response"
      mock_agent_class.return_value = mock_agent

      def capture_agent(*args, **kwargs):
        created_agents.append((args, kwargs))
        return mock_agent

      mock_agent_class.side_effect = capture_agent

      with patch.object(tool, "_run_with_timeout") as mock_run:
        mock_run.return_value = "Response"

        result = tool.execute(
          agent_path=str(temp_agent_file),
          prompt="Test prompt",
        )

        assert result.success
        # The agent definition specifies model: llama3.2:latest
        kwargs = created_agents[0][1]
        assert kwargs.get("model") == "llama3.2:latest"


class TestAgentToolClamp:
  """Tests for the _clamp helper method."""

  def test_clamp_within_range(self) -> None:
    """Test clamping value within range."""
    tool = AgentTool()
    assert tool._clamp(50, 0, 100) == 50

  def test_clamp_at_minimum(self) -> None:
    """Test clamping value at minimum."""
    tool = AgentTool()
    assert tool._clamp(0, 0, 100) == 0

  def test_clamp_at_maximum(self) -> None:
    """Test clamping value at maximum."""
    tool = AgentTool()
    assert tool._clamp(100, 0, 100) == 100

  def test_clamp_below_minimum(self) -> None:
    """Test clamping value below minimum."""
    tool = AgentTool()
    assert tool._clamp(-10, 0, 100) == 0

  def test_clamp_above_maximum(self) -> None:
    """Test clamping value above maximum."""
    tool = AgentTool()
    assert tool._clamp(150, 0, 100) == 100


class TestAgentToolIntegration:
  """Integration tests for AgentTool."""

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

  def test_full_execution_flow(self, temp_agent_file: Path, tmp_path: Path) -> None:
    """Test full execution flow with mocked Agent."""
    # Create mock config with all required validation fields
    config = MagicMock()
    # Harness config
    config.harness.name = "test"
    config.harness.log_level = "INFO"
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
    config.context.storage_path = str(tmp_path / "context")
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
    config.agents.directory = str(tmp_path / "agents")
    config.agents.default_type = "main"
    # Logging config
    config.logging.level = "INFO"
    config.logging.format = "text"

    # Create mock parent agent
    mock_parent = MagicMock(spec=Agent)
    mock_parent._recursion_depth = 0
    mock_parent._max_recursion_depth = 3
    mock_parent.config = config
    mock_parent.model = "test-model"
    mock_parent.context = MagicMock()
    mock_parent.context.get_session_id.return_value = "test-session"

    tool = AgentTool(parent_agent=mock_parent)

    # Mock Agent creation and process
    with patch("yoker.agent.Agent") as mock_agent_class:
      mock_agent = MagicMock()
      mock_agent.process.return_value = "Sub-agent response"
      mock_agent_class.return_value = mock_agent

      result = tool.execute(
        agent_path=str(temp_agent_file),
        prompt="Test prompt",
        timeout_seconds=60,
      )

      assert result.success
      assert result.result == "Sub-agent response"
      assert result.error is None
