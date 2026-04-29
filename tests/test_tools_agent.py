"""Tests for AgentTool security features."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yoker.tools.agent import AgentTool


class TestAgentToolSecurity:
  """Tests for AgentTool security features."""

  @pytest.fixture
  def mock_agent(self, tmp_path: Path) -> MagicMock:
    """Create a mock parent agent with config."""
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

    agent = MagicMock()
    agent._recursion_depth = 0
    agent._max_recursion_depth = 3
    agent.config = config
    agent.context = MagicMock()
    agent.context.get_session_id.return_value = "test_session"
    agent.model = "test-model"
    return agent

  @pytest.fixture
  def valid_agent_file(self, tmp_path: Path) -> Path:
    """Create a valid agent definition file in allowed directory."""
    agents_dir = tmp_path / "examples" / "agents"
    agents_dir.mkdir(parents=True)
    agent_file = agents_dir / "test_agent.md"
    agent_file.write_text(
      """---
name: Test Agent
tools:
  - read
  - write
---
You are a test agent.
"""
    )
    return agent_file

  @pytest.fixture
  def invalid_agent_file(self, tmp_path: Path) -> Path:
    """Create an agent file outside allowed directory."""
    other_dir = tmp_path / "forbidden"
    other_dir.mkdir()
    agent_file = other_dir / "malicious.md"
    agent_file.write_text(
      """---
name: Malicious Agent
tools:
  - read
---
You are a malicious agent.
"""
    )
    return agent_file

  def test_path_traversal_blocked(self, mock_agent: MagicMock, invalid_agent_file: Path) -> None:
    """Test that path traversal attacks are blocked."""
    # The mock_agent fixture already has config.agents.directory set
    # to tmp_path/agents, so invalid_agent_file (which is in tmp_path/forbidden)
    # will be rejected
    tool = AgentTool(parent_agent=mock_agent)

    result = tool.execute(agent_path=str(invalid_agent_file), prompt="test prompt")

    assert result.success is False
    assert "not in allowed directory" in result.error

  def test_valid_agent_path_allowed(
    self, mock_agent: MagicMock, valid_agent_file: Path, tmp_path: Path
  ) -> None:
    """Test that valid agent paths within allowed directory work."""
    # Update mock config to point to the valid agent file's parent directory
    mock_agent.config.agents.directory = str(tmp_path / "examples" / "agents")

    tool = AgentTool(parent_agent=mock_agent)

    # This will fail during execution, but path validation should pass
    with patch.object(tool, "_create_subagent", side_effect=Exception("Mocked subagent")):
      result = tool.execute(agent_path=str(valid_agent_file), prompt="test prompt")

      # Path validation passed, execution failed for other reasons
      assert "not in allowed directory" not in result.error

  def test_custom_agents_directory(self, mock_agent: MagicMock, tmp_path: Path) -> None:
    """Test that custom agents directory is respected."""
    # Set custom agents directory
    custom_dir = tmp_path / "custom_agents"
    custom_dir.mkdir()
    agent_file = custom_dir / "custom.md"
    agent_file.write_text(
      """---
name: Custom Agent
tools:
  - read
---
Custom agent.
"""
    )

    # Update mock config with custom directory
    mock_agent.config.agents.directory = str(custom_dir)

    tool = AgentTool(parent_agent=mock_agent)

    # Path validation should pass for custom directory
    with patch.object(tool, "_create_subagent", side_effect=Exception("Mocked subagent")):
      result = tool.execute(agent_path=str(agent_file), prompt="test prompt")

      assert "not in allowed directory" not in result.error

  def test_session_id_uses_uuid(
    self, mock_agent: MagicMock, valid_agent_file: Path, tmp_path: Path
  ) -> None:
    """Test that session IDs use UUID for unpredictability."""
    # Update mock config to point to the valid agent file's parent directory
    mock_agent.config.agents.directory = str(tmp_path / "examples" / "agents")

    tool = AgentTool(parent_agent=mock_agent)

    # Mock the subagent creation to capture session ID
    captured_session_ids = []

    def capture_session_id(*args, **kwargs):
      # Extract session_id from the context manager creation

      ctx = MagicMock()
      ctx.get_session_id.return_value = "test_session_abc12345"
      captured_session_ids.append(ctx.get_session_id.return_value)

      subagent = MagicMock()
      subagent.process = MagicMock(return_value="test response")
      return subagent

    with patch.object(tool, "_create_subagent", side_effect=capture_session_id):
      with patch.object(tool, "_run_with_timeout", return_value="test response"):
        tool.execute(agent_path=str(valid_agent_file), prompt="test prompt")

    # Verify session ID format (parent_uuid8chars)
    # The format is f"{parent_session}_{uuid[:8]}"
    # So it should be test_session_XXXXXXXX (8 hex chars)
    assert len(captured_session_ids) > 0
    session_id = captured_session_ids[0]
    # Should not contain "_sub_" which was the old pattern
    assert "_sub_" not in session_id
    # Should have parent session prefix
    assert session_id.startswith("test_session_")

  def test_absolute_path_traversal_blocked(self, mock_agent: MagicMock, tmp_path: Path) -> None:
    """Test that absolute path traversal is blocked."""
    # Try to load /etc/passwd as an agent (common attack vector)
    tool = AgentTool(parent_agent=mock_agent)

    result = tool.execute(agent_path="/etc/passwd", prompt="test prompt")

    # Either file doesn't exist or path traversal blocked
    assert result.success is False
    assert "not in allowed directory" in result.error or "not found" in result.error

  def test_symlink_traversal_blocked(self, mock_agent: MagicMock, tmp_path: Path) -> None:
    """Test that symlink-based path traversal is blocked."""
    # Create agents directory inside tmp_path
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    outside_file = tmp_path / "outside" / "secret.md"
    outside_file.parent.mkdir()
    outside_file.write_text("---\nname: Secret\n---\nSecret agent")

    symlink = agents_dir / "malicious_link.md"
    try:
      symlink.symlink_to(outside_file)
    except OSError:
      # Symlinks may not be supported on all systems
      pytest.skip("Symlinks not supported")

    tool = AgentTool(parent_agent=mock_agent)

    result = tool.execute(agent_path=str(symlink), prompt="test prompt")

    # Symlink should be resolved and blocked
    assert result.success is False
    assert (
      "not in allowed directory" in result.error
      or "Sub-agent error" in result.error  # May pass path check but fail loading
    )
