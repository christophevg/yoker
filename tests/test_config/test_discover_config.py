"""Tests for config auto-discovery."""

from pathlib import Path
from unittest.mock import patch

import pytest

from yoker.config import Config, discover_config, load_config
from yoker.config.schema import AgentsConfig
from yoker.exceptions import ConfigurationError


class TestDiscoverConfig:
  """Tests for discover_config function."""

  def test_discover_config_no_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test discover_config returns defaults when no config files exist."""
    # Change to temp directory (no yoker.toml)
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to point to temp directory (no .yoker.toml)
    with patch.object(Path, "home", return_value=tmp_path):
      config, path = discover_config()

    assert config == Config()
    assert path is None

  def test_discover_config_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test discover_config finds config in current directory."""
    # Create yoker.toml in temp directory
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      """
[harness]
name = "test-project"
version = "2.0"

[agents]
directory = "./test-agents"
definition = "./test-agents/test.md"
"""
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to point elsewhere
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      config, path = discover_config()

    assert config.harness.name == "test-project"
    assert config.harness.version == "2.0"
    assert config.agents.directory == "./test-agents"
    assert config.agents.definition == "./test-agents/test.md"
    assert path == config_file

  def test_discover_config_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test discover_config finds config in home directory."""
    # Create .yoker.toml in mock home directory
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    config_file = home_dir / ".yoker.toml"
    config_file.write_text(
      """
[harness]
name = "home-project"
version = "3.0"

[agents]
directory = "./home-agents"
"""
    )

    # Change to temp directory (no yoker.toml in cwd)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    # Mock Path.home() to point to mock home
    with patch.object(Path, "home", return_value=home_dir):
      config, path = discover_config()

    assert config.harness.name == "home-project"
    assert config.harness.version == "3.0"
    assert config.agents.directory == "./home-agents"
    assert path == config_file

  def test_discover_config_cwd_takes_precedence(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test discover_config prefers cwd over home directory."""
    # Create yoker.toml in cwd
    cwd_config_file = tmp_path / "yoker.toml"
    cwd_config_file.write_text(
      """
[harness]
name = "cwd-project"
"""
    )

    # Create .yoker.toml in home
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    home_config_file = home_dir / ".yoker.toml"
    home_config_file.write_text(
      """
[harness]
name = "home-project"
"""
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to point to mock home
    with patch.object(Path, "home", return_value=home_dir):
      config, path = discover_config()

    # Should load cwd config, not home config
    assert config.harness.name == "cwd-project"
    assert path == cwd_config_file

  def test_discover_config_invalid_toml(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test discover_config raises error for invalid TOML."""
    # Create invalid yoker.toml
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      """
[harness
name = "invalid"
"""
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      with pytest.raises(ConfigurationError, match="Failed to parse TOML"):
        discover_config()

  def test_discover_config_empty_file(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test discover_config handles empty config file."""
    # Create empty yoker.toml
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      config, path = discover_config()

    # Empty file should result in default config
    assert config == Config()
    assert path == config_file


class TestAgentsConfigDefinition:
  """Tests for AgentsConfig.definition field."""

  def test_agents_config_definition_default(self) -> None:
    """Test that definition field defaults to empty string."""
    config = AgentsConfig()
    assert config.definition == ""

  def test_agents_config_definition_explicit(self) -> None:
    """Test that definition field can be set explicitly."""
    config = AgentsConfig(definition="./agents/researcher.md")
    assert config.definition == "./agents/researcher.md"

  def test_agents_config_definition_from_toml(self, tmp_path: Path) -> None:
    """Test that definition field is parsed from TOML."""
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      """
[agents]
directory = "./agents"
definition = "./agents/researcher.md"
default_type = "main"
"""
    )

    config = load_config(config_file)
    assert config.agents.directory == "./agents"
    assert config.agents.definition == "./agents/researcher.md"
    assert config.agents.default_type == "main"

  def test_agents_config_definition_missing_in_toml(self, tmp_path: Path) -> None:
    """Test that definition field defaults when not in TOML."""
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      """
[agents]
directory = "./agents"
"""
    )

    config = load_config(config_file)
    assert config.agents.definition == ""


class TestAgentDefinitionResolution:
  """Tests for agent definition resolution from config."""

  def test_agent_definition_from_config(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that Agent loads agent definition from config."""
    from yoker.agent import Agent

    # Create agent definition file
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    agent_file = agents_dir / "researcher.md"
    agent_file.write_text(
      """---
name: researcher
description: Research agent
tools: read, list
---
You are a research agent.
"""
    )

    # Create config file with agent definition (use forward slashes for TOML)
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      f"""
[agents]
definition = "{agent_file.as_posix()}"
"""
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      agent = Agent()

    # Should have loaded agent definition from config
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "researcher"
    assert "research agent" in agent.agent_definition.system_prompt

  def test_agent_definition_config_missing_file(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that Agent falls back to default when config agent definition file is missing."""
    from yoker.agent import Agent

    # Create config file with missing agent definition
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      """
[agents]
definition = "./agents/missing.md"
"""
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      agent = Agent()

    # Should have fallen back to default (no agent definition)
    assert agent.agent_definition is None

  def test_agent_definition_explicit_overrides_config(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that explicit agent_definition parameter overrides config."""
    from yoker.agent import Agent
    from yoker.agents import AgentDefinition

    # Create config file with agent definition
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      """
[agents]
definition = "./agents/researcher.md"
"""
    )

    # Create explicit agent definition
    explicit_definition = AgentDefinition(
      name="explicit",
      description="Explicit agent",
      tools=("read",),
      system_prompt="You are the explicit agent.",
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      agent = Agent(agent_definition=explicit_definition)

    # Should use explicit agent definition, not config
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "explicit"

  def test_agent_definition_path_overrides_config(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that explicit agent_path parameter overrides config."""
    from yoker.agent import Agent

    # Create agent definition files
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    config_agent_file = agents_dir / "config.md"
    config_agent_file.write_text(
      """---
name: config-agent
description: Config agent
tools: read
---
You are the config agent.
"""
    )

    explicit_agent_file = agents_dir / "explicit.md"
    explicit_agent_file.write_text(
      """---
name: explicit-agent
description: Explicit agent
tools: read
---
You are the explicit agent.
"""
    )

    # Create config file with agent definition (use forward slashes for TOML)
    config_file = tmp_path / "yoker.toml"
    config_file.write_text(
      f"""
[agents]
definition = "{config_agent_file.as_posix()}"
"""
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      agent = Agent(agent_path=explicit_agent_file)

    # Should use explicit path, not config
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "explicit-agent"


class TestConfigLogging:
  """Tests for config discovery logging."""

  def test_logs_config_discovered_cwd(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that discover_config logs when config is discovered in cwd."""
    from yoker.config import discover_config

    # Create yoker.toml in temp directory
    config_file = tmp_path / "yoker.toml"
    config_file.write_text('[harness]\nname = "test"')

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to point elsewhere
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      config, path = discover_config()

    # Should discover config in cwd
    assert path == config_file
    assert config.harness.name == "test"

  def test_logs_config_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that discover_config returns defaults when no config found."""
    from yoker.config import discover_config

    # Change to temp directory (no config files)
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to point to temp directory (no config files)
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      config, path = discover_config()

    # Should return defaults
    assert path is None
    assert config == Config()
