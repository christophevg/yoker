"""Tests for agent definition loading from files and via the registry.

Agent references are resolved by name through the :class:`yoker.session.Session`'s
:class:`~yoker.agents.AgentRegistry` (populated from configured directories
and loaded plugins — MBI-007 Decision 10). The historical ``plugin://``
agent-reference scheme has been removed in favour of ``--with <pkg>`` (load
plugin) + ``--agent <name>`` (registry lookup).
"""

import tempfile
from pathlib import Path

import pytest

from yoker.agent import Agent
from yoker.session import Session


class TestAgentDefinitionFileValidation:
  """Test validation of agent definition files."""

  def test_invalid_file_path_raises_error(self):
    """Test that invalid file path raises ValueError.

    MBI-007 Phase 2: name resolution (which a non-existent path becomes)
    requires a Session. With a Session, the registry raises
    ``ValueError("Agent not found: ...")``.
    """
    from yoker.config import Config

    session = Session(config=Config())
    with pytest.raises(ValueError, match="Agent not found: /nonexistent/path/to/agent.md"):
      Agent(config=Config(), agent_path="/nonexistent/path/to/agent.md", session=session)

  def test_invalid_file_path_without_session_raises(self):
    """Without a Session, an unresolvable reference raises a clear ValueError."""
    with pytest.raises(ValueError, match="cannot be resolved without a Session"):
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
    """Test that invalid config.agents.definition raises ValueError.

    MBI-007 Phase 2: name resolution requires a Session. With a Session, the
    registry raises ``ValueError("Agent not found: ...")``.
    """
    from yoker.config import AgentsConfig, Config

    config = Config(agents=AgentsConfig(definition="/nonexistent/agent.md"))
    session = Session(config=config)

    with pytest.raises(ValueError, match=r"Agent not found: /nonexistent/agent\.md"):
      Agent(config=config, session=session)


class TestRegistryAgentResolution:
  """Test resolving agents by name through the Session's AgentRegistry.

  Replaces the former ``plugin://`` agent-reference tests. An agent reference
  that is not an existing file path is resolved by name through the Session's
  registry (populated from ``config.agents.directories`` and loaded plugins):
  a bare name matches a unique ``simple_name`` across namespaces; a
  namespaced name matches exactly; an ambiguous bare name raises
  ``ValueError``.

  MBI-007 Phase 2: the AgentRegistry is owned by the Session (Decision 10),
  so name resolution requires constructing the Agent within a Session.
  """

  def _make_agents_dir(self, tmp_path: Path, agents: dict[str, str]) -> Path:
    """Write agent definition files into a temp directory and return it."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    for filename, body in agents.items():
      (agents_dir / filename).write_text(body, encoding="utf-8")
    return agents_dir

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
    agent = Agent(config=config, agent_path="writer", session=session)
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
    agent = Agent(config=config, agent_path=f"{ns}:writer", session=session)
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
      Agent(config=config, agent_path="writer", session=session)

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
      Agent(config=config, agent_path="nope", session=session)

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
    with pytest.raises(ValueError, match="cannot be resolved without a Session"):
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
