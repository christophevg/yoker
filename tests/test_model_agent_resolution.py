"""Tests for model and agent resolution from configuration."""

from pathlib import Path
from unittest.mock import patch

import pytest

from yoker.agent import Agent
from yoker.config import Config


class TestModelResolution:
  """Tests for model resolution from configuration."""

  def test_model_from_config_model_field(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that config.model takes precedence over backend.ollama.model."""
    from yoker.config import BackendConfig, OllamaConfig

    # Create config with model override
    config = Config(
      model="override-model:latest",
      backend=BackendConfig(ollama=OllamaConfig(model="backend-model:latest")),
    )

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config)

    # Should use config.model, not backend.ollama.model
    assert agent.model == "override-model:latest"

  def test_model_from_backend_ollama_model(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that backend.ollama.model is used when config.model is None."""
    from yoker.config import BackendConfig, OllamaConfig

    # Create config without model override
    config = Config(
      backend=BackendConfig(ollama=OllamaConfig(model="backend-model:latest")),
    )

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config)

    # Should use backend.ollama.model
    assert agent.model == "backend-model:latest"

  def test_model_from_agent_definition(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that agent definition model takes highest precedence."""
    from yoker.agents import AgentDefinition
    from yoker.config import BackendConfig, OllamaConfig

    # Create config with model override
    config = Config(
      model="override-model:latest",
      backend=BackendConfig(ollama=OllamaConfig(model="backend-model:latest")),
    )

    # Create agent definition with model
    agent_def = AgentDefinition(
      name="Test Agent",
      description="Test agent",
      system_prompt="You are a test agent.",
      tools=["read"],
      model="agent-model:latest",
    )

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config, agent_definition=agent_def)

    # Should use agent definition model
    assert agent.model == "agent-model:latest"


class TestAgentResolution:
  """Tests for agent definition resolution from configuration."""

  def test_agent_from_config_agent_field(self, tmp_path: Path) -> None:
    """Test that config.agent is used for agent definition path."""
    # Create a test agent file
    agent_file = tmp_path / "test_agent.md"
    agent_file.write_text("""---
name: Test Agent
description: Test agent for config resolution
tools:
  - read
model: test-model:latest
---
You are a test agent.
""")

    # Create config with agent path
    config = Config(agent=str(agent_file))

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config)

    # Should load agent definition from config.agent
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "Test Agent"
    assert agent.agent_definition.model == "test-model:latest"

  def test_agent_fallback_to_agents_definition(self, tmp_path: Path) -> None:
    """Test fallback to config.agents.definition for backward compatibility."""
    # Create a test agent file
    agent_file = tmp_path / "legacy_agent.md"
    agent_file.write_text("""---
name: Legacy Agent
description: Legacy agent for backward compatibility
tools:
  - read
---
You are a legacy agent.
""")

    # Create config with legacy agents.definition field
    from yoker.config import AgentsConfig

    config = Config(agents=AgentsConfig(definition=str(agent_file)))

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config)

    # Should load agent definition from config.agents.definition
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "Legacy Agent"

  def test_explicit_agent_path_overrides_config(self, tmp_path: Path) -> None:
    """Test that explicit agent_path parameter overrides config.agent."""
    # Create two test agent files
    config_agent = tmp_path / "config_agent.md"
    config_agent.write_text("""---
name: Config Agent
description: Agent from config
tools:
  - read
---
You are from config.
""")

    explicit_agent = tmp_path / "explicit_agent.md"
    explicit_agent.write_text("""---
name: Explicit Agent
description: Agent from explicit path
tools:
  - read
---
You are from explicit path.
""")

    # Create config with agent path
    config = Config(agent=str(config_agent))

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config, agent_path=str(explicit_agent))

    # Should use explicit agent_path, not config.agent
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "Explicit Agent"

  def test_no_agent_definition_uses_default(self) -> None:
    """Test that no agent definition results in default behavior."""
    # Create config without agent
    config = Config()

    # Mock the Ollama client to avoid network calls
    with patch("yoker.agent.AsyncClient"):
      agent = Agent(config=config)

    # Should have no agent definition
    assert agent.agent_definition is None
