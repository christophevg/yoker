"""Tests for Session.spawn — allowlist, depth, max_agents, backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config
from yoker.session import Session


def _make_requester(allowlist=(), session=None):
  """Build a mock requester Agent with a definition allowlist."""
  agent = MagicMock()
  agent.definition = AgentDefinition(
    simple_name="parent",
    description="Parent",
    tools=("read",),
    agents=tuple(allowlist),
  )
  return agent


class TestSpawnAllowlist:
  """Tests for AgentDefinition.agents allowlist enforcement."""

  @pytest.mark.asyncio
  async def test_top_level_spawn_bypasses_allowlist(self) -> None:
    """requester=None skips the allowlist check (trusted top-level caller)."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      # Patch yoker.session.Agent — the reference Session._create_agent calls.
      with patch("yoker.session.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.tools = MagicMock()
        mock_agent_cls.return_value = mock_child
        child, agent_id = await session._spawn_internal("researcher", requester=None)
        response = await child.process("hi")
      assert agent_id == "researcher"
      assert response == "ok"

  @pytest.mark.asyncio
  async def test_empty_allowlist_rejects_spawn(self) -> None:
    """An empty allowlist on the requester rejects the spawn."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      requester = _make_requester(allowlist=(), session=session)
      with pytest.raises(ValueError, match="no allowed spawns"):
        await session.spawn("researcher", requester=requester)

  @pytest.mark.asyncio
  async def test_name_not_in_allowlist_rejects(self) -> None:
    """A name not in the requester's allowlist is rejected."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      requester = _make_requester(allowlist=("writer",), session=session)
      with pytest.raises(ValueError, match="allowlist"):
        await session.spawn("researcher", requester=requester)

  @pytest.mark.asyncio
  async def test_name_in_allowlist_proceeds(self) -> None:
    """A name in the requester's allowlist proceeds to spawn."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      requester = _make_requester(allowlist=("researcher",), session=session)
      with patch("yoker.session.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.tools = MagicMock()
        mock_agent_cls.return_value = mock_child
        child, agent_id = await session._spawn_internal("researcher", requester=requester)
        response = await child.process("hi")
      assert response == "ok"

  @pytest.mark.asyncio
  async def test_allowlist_check_precedes_depth_check(self) -> None:
    """Allowlist rejection takes precedence over depth/capacity errors."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      # allowlist violation should fire before any depth/capacity check.
      requester = _make_requester(allowlist=("writer",), session=session)
      requester.definition = AgentDefinition(
        simple_name="parent",
        description="Parent",
        tools=("read",),
        agents=("writer",),
      )
      with pytest.raises(ValueError, match="allowlist"):
        await session.spawn("researcher", requester=requester)


class TestSpawnMaxAgents:
  """Tests for the session max_agents cap."""

  @pytest.mark.asyncio
  async def test_spawn_rejected_when_max_agents_reached(self) -> None:
    """Spawning beyond config.session.max_agents raises ValueError."""

    from yoker.config import SessionConfig

    config = Config(session=SessionConfig(max_agents=1))
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      # Fill the active map to the cap.
      session._agents_map["occupant"] = MagicMock()
      with pytest.raises(ValueError, match="max_agents"):
        await session.spawn("researcher")


class TestSpawnAgentMap:
  """Tests for agent map and name disambiguation in spawn."""

  @pytest.mark.asyncio
  async def test_spawn_registers_then_removes_agent(self) -> None:
    """Spawn registers the agent in the map and removes it on completion."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      with patch("yoker.session.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.tools = MagicMock()
        mock_agent_cls.return_value = mock_child
        child, agent_id = await session._spawn_internal("researcher")
        await child.process("hi")
        session.release(child)
      # Hardening: confirm the mock class was actually constructed. A stale
      # patch target would let a real Agent reach localhost:11434 and mask the
      # bug behind a local Ollama daemon.
      mock_agent_cls.assert_called_once()
      # agent removed from active list after release.
      assert session.get_agent("researcher") is None
      assert agent_id == "researcher"

  @pytest.mark.asyncio
  async def test_duplicate_spawns_get_disambiguated(self) -> None:
    """Second spawn of the same definition name gets a -2 suffix."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      with patch("yoker.session.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.tools = MagicMock()
        mock_agent_cls.return_value = mock_child
        first_child, first_id = await session._spawn_internal("researcher")
        await first_child.process("first")
        session.release(first_child)
        second_child, second_id = await session._spawn_internal("researcher")
        await second_child.process("second")
        session.release(second_child)
      # Hardening: confirm the mock class was actually constructed (twice, once
      # per spawn). A stale patch target would let a real Agent reach
      # localhost:11434 and mask the bug behind a local Ollama daemon.
      assert mock_agent_cls.call_count == 2
      # Both completed; counters reflect two spawns of "researcher".
      assert session._name_counters["researcher"] == 2
      assert first_id == "researcher"
      assert second_id == "researcher-2"


class TestSessionBackendFactory:
  """Tests for Session.get_backend — sharing and freshness."""

  def test_same_config_returns_same_backend(self) -> None:
    """get_backend is idempotent for the same config (shared backend)."""
    config = Config()
    session = Session(config=config)
    # Session.__init__ already cached a backend for the primary agent; clear
    # the cache to test get_backend in isolation against the patched factory.
    session._backends.clear()
    # yoker/session/session.py was collapsed into yoker/session/__init__.py,
    # so create_backend now lives on yoker.session directly.
    with patch("yoker.session.create_backend") as mock_create:
      mock_backend = MagicMock()
      mock_create.return_value = mock_backend
      b1 = session.get_backend(config)
      b2 = session.get_backend(config)
    assert b1 is b2
    mock_create.assert_called_once_with(config)

  def test_different_model_returns_fresh_backend(self) -> None:
    """A model override produces a different cache key → fresh backend."""

    from yoker.config import BackendConfig, OllamaConfig

    config_a = Config(backend=BackendConfig(ollama=OllamaConfig(model="a")))
    config_b = Config(backend=BackendConfig(ollama=OllamaConfig(model="b")))
    session = Session(config=config_a)
    # Clear the cache populated by Session.__init__ so get_backend calls the
    # patched create_backend.
    session._backends.clear()
    with patch("yoker.session.create_backend") as mock_create:
      b_a = MagicMock()
      b_b = MagicMock()
      mock_create.side_effect = [b_a, b_b]
      first = session.get_backend(config_a)
      second = session.get_backend(config_b)
    assert first is b_a
    assert second is b_b

  def test_backend_key_stable_for_same_provider_settings(self) -> None:
    """The cache key is deterministic for identical provider settings."""
    config = Config()
    key1 = Session._backend_key(config)
    key2 = Session._backend_key(config)
    assert key1 == key2
    assert "ollama" in key1


class TestSessionRegistryPopulation:
  """Tests for Session._load_agents."""

  def test_session_creates_empty_registry(self) -> None:
    """Session has an AgentRegistry instance."""
    session = Session(config=Config())
    from yoker.agents import AgentRegistry

    assert isinstance(session.agents, AgentRegistry)

  def test_session_loads_agents_from_config_directories(self, tmp_path) -> None:
    """Agent definitions in config.agents.directories are loaded into session.agents."""
    from dataclasses import replace

    from yoker.config import AgentsConfig

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "researcher.md").write_text(
      """---
name: researcher
description: Researcher
tools:
  - read
---

You are a researcher.
"""
    )
    config = Config()
    config = replace(config, agents=AgentsConfig(directories=(str(agents_dir),)))
    session = Session(config=config)
    assert "agents:researcher" in session.agents.names
