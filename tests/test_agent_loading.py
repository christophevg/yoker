"""Tests for agent definition loading from files and via the registry.

Agent references are resolved by name through the :class:`yoker.session.Session`'s
:class:`~yoker.agents.AgentRegistry` (populated from configured directories
and loaded plugins). The Agent is Session-agnostic: name resolution is
performed by the Session layer, which passes the resolved
:class:`AgentDefinition` to the :class:`Agent` constructor.
"""

import tempfile
from pathlib import Path

import pytest

from yoker.core import Agent
from yoker.session import Session


class TestAgentDefinitionFileValidation:
  """Test validation of agent definition files."""

  def test_invalid_file_path_raises_error(self):
    """Test that invalid file path raises ValueError.

    A non-existent path is loaded directly by the Agent (no Session
    needed); the loader raises ``ValueError``.
    """
    from yoker.config import Config

    with pytest.raises(ValueError):
      Agent(config=Config(), agent_path="/nonexistent/path/to/agent.md")

  def test_invalid_file_path_without_session_raises(self):
    """Without a Session, an unresolvable name reference raises a clear ValueError."""
    with pytest.raises(ValueError, match="cannot be resolved by a standalone Agent"):
      Agent(agent_path="/nonexistent/path/to/agent.md")

  def test_valid_file_path_loads_successfully(self):
    """Test that valid file path loads successfully."""
    # Use existing example agent
    agent_path = Path("examples/agents/markdown.md")
    if agent_path.exists():
      from yoker.config import Config

      agent = Agent(config=Config(), agent_path=agent_path)
      assert agent.definition is not None
      assert agent.definition.name == "file:markdown"
    else:
      pytest.skip("Example agent file not found")

  def test_config_definition_validates_file_exists(self):
    """Test that config.agents.definition validates file existence."""
    from yoker.config import AgentsConfig, Config

    # Create a temp file for testing with valid frontmatter
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
      f.write(
        "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\nTest system prompt\n"
      )
      f.flush()
      temp_path = f.name

    try:
      # Valid file should work
      config = Config(agents=AgentsConfig(definition=temp_path))
      agent = Agent(config=config)
      assert agent.definition is not None
      assert agent.definition.name == "file:test"
    finally:
      Path(temp_path).unlink()

  def test_config_definition_invalid_file_raises_error(self):
    """Test that an invalid config.agents.definition (non-file name) raises.

    A non-existent path that is not a file is treated as a name reference.
    Without a Session, the Agent raises "cannot be resolved by a standalone
    Agent".
    """
    from yoker.config import AgentsConfig, Config

    config = Config(agents=AgentsConfig(definition="/nonexistent/agent.md"))
    with pytest.raises(ValueError, match="cannot be resolved by a standalone Agent"):
      Agent(config=config)


class TestRegistryAgentResolution:
  """Test resolving agents by name through the Session's AgentRegistry.

  The AgentRegistry is owned by the Session. The Session-agnostic Agent
  cannot resolve names from a registry, so the Session layer resolves the
  reference and passes the resolved :class:`AgentDefinition` to the Agent
  via the ``agent_definition=`` constructor parameter.
  """

  def _make_agents_dir(self, tmp_path: Path, agents: dict[str, str]) -> Path:
    """Write agent definition files into a temp directory and return it."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    for filename, body in agents.items():
      (agents_dir / filename).write_text(body, encoding="utf-8")
    return agents_dir

  def _resolve(self, session: Session, name: str):
    """Resolve an agent name via the session registry."""
    return session.agents.resolve(name)

  def test_bare_name_resolves_unique(self, tmp_path):
    """A bare name resolves when exactly one agent has that simple_name."""
    from yoker.config import AgentsConfig, Config

    agents_dir = self._make_agents_dir(
      tmp_path,
      {
        "writer.md": ("---\nname: writer\ndescription: writes\ntools:\n  - read\n---\nbody\n"),
      },
    )
    config = Config(agents=AgentsConfig(directories=(str(agents_dir),)))
    session = Session(config=config)
    resolved = self._resolve(session, "writer")
    agent = Agent(config=config, agent_definition=resolved)
    assert agent.definition is not None
    assert agent.definition.simple_name == "writer"

  def test_namespaced_name_resolves_exactly(self, tmp_path):
    """A namespaced name (namespace:simple) matches the exact key."""
    from yoker.config import AgentsConfig, Config

    agents_dir = self._make_agents_dir(
      tmp_path,
      {
        "writer.md": ("---\nname: writer\ndescription: writes\ntools:\n  - read\n---\nbody\n"),
      },
    )
    config = Config(agents=AgentsConfig(directories=(str(agents_dir),)))
    # The directory name becomes the namespace.
    ns = agents_dir.name
    session = Session(config=config)
    resolved = self._resolve(session, f"{ns}:writer")
    agent = Agent(config=config, agent_definition=resolved)
    assert agent.definition is not None
    assert agent.definition.name == f"{ns}:writer"

  def test_ambiguous_bare_name_raises(self, tmp_path):
    """A bare name matching several agents raises ValueError listing them."""
    from yoker.config import AgentsConfig, Config

    # Two directories, each namespace defaults to the folder name, so two
    # agents named "writer" land in different namespaces and both load.
    agents_dir = self._make_agents_dir(
      tmp_path,
      {
        "writer.md": ("---\nname: writer\ndescription: a\ntools:\n  - read\n---\nbody\n"),
      },
    )
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "writer.md").write_text(
      "---\nname: writer\ndescription: b\ntools:\n  - read\n---\nbody\n",
      encoding="utf-8",
    )
    config = Config(agents=AgentsConfig(directories=(str(agents_dir), str(other_dir))))
    session = Session(config=config)
    with pytest.raises(ValueError, match="ambiguous"):
      self._resolve(session, "writer")

  def test_unknown_agent_name_raises_error(self, tmp_path):
    """An unknown agent name raises ValueError."""
    from yoker.config import AgentsConfig, Config

    agents_dir = self._make_agents_dir(
      tmp_path,
      {
        "writer.md": ("---\nname: writer\ndescription: writes\ntools:\n  - read\n---\nbody\n"),
      },
    )
    config = Config(agents=AgentsConfig(directories=(str(agents_dir),)))
    session = Session(config=config)
    with pytest.raises(ValueError, match="Agent not found: nope"):
      self._resolve(session, "nope")

  def test_resolution_without_session_raises(self, tmp_path):
    """Resolving a name without a Session raises a clear ValueError."""
    from yoker.config import AgentsConfig, Config

    agents_dir = self._make_agents_dir(
      tmp_path,
      {
        "writer.md": ("---\nname: writer\ndescription: writes\ntools:\n  - read\n---\nbody\n"),
      },
    )
    config = Config(agents=AgentsConfig(directories=(str(agents_dir),)))
    with pytest.raises(ValueError, match="cannot be resolved by a standalone Agent"):
      Agent(config=config, agent_path="writer")


class TestAgentDefinitionLoading:
  """Test general agent definition loading behavior."""

  def test_agent_path_and_definition_both_provided(self):
    """Test that agent_definition takes precedence when both are provided."""
    from yoker.agents import AgentDefinition
    from yoker.config import Config

    # Create a valid agent definition
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Test prompt",
    )

    # When both provided, agent_definition should take precedence
    # agent_path should be ignored (not even validated)
    agent = Agent(config=Config(), agent_definition=agent_def, agent_path="/nonexistent/path.md")

    # agent_definition should be used, not agent_path
    assert agent.definition is not None
    assert agent.definition.name == "test"
