"""Tests for config auto-discovery using Clevis."""

from pathlib import Path
from unittest.mock import patch

import pytest
from clevis import SecurityAction, get_config

from yoker.config import AgentsConfig, Config


class TestClevisIntegration:
  """Tests for Clevis integration."""

  def test_get_config_returns_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_config() returns a valid Config."""
    # Change to temp directory to avoid loading project config
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      # Use security bypass for tests (temp files are group/other readable)
      config = get_config(
        Config,
        name="yoker",
        cli=False,
        security={
          "file_permissions": SecurityAction.DONT_CHECK,
          "directory_permissions": SecurityAction.DONT_CHECK,
        },
      )
      assert isinstance(config, Config)
      # With no config files, should use defaults
      assert config.harness.name == "yoker"


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
      config = get_config(
        Config,
        name="yoker",
        cli=False,
        security={
          "file_permissions": SecurityAction.DONT_CHECK,
          "directory_permissions": SecurityAction.DONT_CHECK,
        },
      )
      agent = Agent(config=config)

    # Should have loaded agent definition from config
    assert agent.definition.name == "file:researcher"
    assert "research agent" in agent.definition.system_prompt

  def test_agent_definition_config_missing_file(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that missing agent definition file raises an error."""
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
      config = get_config(
        Config,
        name="yoker",
        cli=False,
        security={
          "file_permissions": SecurityAction.DONT_CHECK,
          "directory_permissions": SecurityAction.DONT_CHECK,
        },
      )

      # Should raise ValueError for missing file
      with pytest.raises(ValueError, match=r"Agent not found: \./agents/missing\.md"):
        Agent(config=config)

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
      simple_name="explicit",
      description="Explicit agent",
      tools=("read",),
      system_prompt="You are the explicit agent.",
    )

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      config = get_config(
        Config,
        name="yoker",
        cli=False,
        security={
          "file_permissions": SecurityAction.DONT_CHECK,
          "directory_permissions": SecurityAction.DONT_CHECK,
        },
      )
      agent = Agent(config=config, agent_definition=explicit_definition)

    # Should use explicit agent definition, not config
    assert agent.definition.name == "explicit"

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
      config = get_config(
        Config,
        name="yoker",
        cli=False,
        security={
          "file_permissions": SecurityAction.DONT_CHECK,
          "directory_permissions": SecurityAction.DONT_CHECK,
        },
      )
      agent = Agent(config=config, agent_path=explicit_agent_file)

    # Should use explicit path, not config
    assert agent.definition.name == "file:explicit-agent"
