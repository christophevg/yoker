"""Tests for Session.spawn — allowlist, depth, max_agents, backend (MBI-007 7.3.3, 7.5)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config
from yoker.session import Session


def _config_with_max_recursion(max_depth: int) -> Config:
  """Build a Config with a specific recursion depth limit."""
  from dataclasses import replace

  from yoker.config import AgentToolConfig

  cfg = Config()
  new_tools = replace(cfg.tools, agent=AgentToolConfig(max_recursion_depth=max_depth))
  return replace(cfg, tools=new_tools)


def _make_requester(allowlist=(), session=None):
  """Build a mock requester Agent with a definition allowlist."""
  agent = MagicMock()
  agent.definition = AgentDefinition(
    simple_name="parent",
    description="Parent",
    tools=("read",),
    agents=tuple(allowlist),
  )
  agent._session = session
  return agent


class TestSpawnAllowlist:
  """Tests for AgentDefinition.agents allowlist enforcement (PR #43 Clarification 3)."""

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
      with patch("yoker.agent.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_agent_cls.return_value = mock_child
        response = await session.spawn("researcher", "hi", requester=None)
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
        await session.spawn("researcher", "hi", requester=requester)

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
        await session.spawn("researcher", "hi", requester=requester)

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
      with patch("yoker.agent.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_agent_cls.return_value = mock_child
        response = await session.spawn("researcher", "hi", requester=requester)
      assert response == "ok"

  @pytest.mark.asyncio
  async def test_allowlist_check_precedes_depth_check(self) -> None:
    """Allowlist rejection takes precedence over depth/capacity errors."""
    config = _config_with_max_recursion(1)
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      # requester at depth 1 would exceed max_recursion_depth=1 on the next
      # spawn, but the allowlist violation should fire first.
      requester = _make_requester(allowlist=("writer",), session=session)
      session._recursion_depths["parent"] = 1
      requester.definition = AgentDefinition(
        simple_name="parent",
        description="Parent",
        tools=("read",),
        agents=("writer",),
      )
      with pytest.raises(ValueError, match="allowlist"):
        await session.spawn("researcher", "hi", requester=requester)


class TestSpawnRecursionDepth:
  """Tests for recursion depth enforcement in Session.spawn."""

  @pytest.mark.asyncio
  async def test_top_level_spawn_depth_one(self) -> None:
    """Top-level spawn (requester=None) runs at depth 1."""
    config = _config_with_max_recursion(3)
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      with patch("yoker.agent.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_agent_cls.return_value = mock_child
        await session.spawn("researcher", "hi")
      # Depth tracked during the run; removed in the finally block.
      assert "researcher" not in session._recursion_depths

  @pytest.mark.asyncio
  async def test_spawn_beyond_max_recursion_rejected(self) -> None:
    """Spawning beyond max_recursion_depth raises ValueError."""
    config = _config_with_max_recursion(1)
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      requester = _make_requester(allowlist=("researcher",), session=session)
      # Simulate the requester already being at depth 1 (the max).
      session._agents_map["parent"] = requester
      session._recursion_depths["parent"] = 1
      with pytest.raises(ValueError, match="Maximum recursion depth"):
        await session.spawn("researcher", "hi", requester=requester)


class TestSpawnMaxAgents:
  """Tests for the session max_agents cap (Decision 7)."""

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
        await session.spawn("researcher", "hi")


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
      with patch("yoker.agent.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_agent_cls.return_value = mock_child
        await session.spawn("researcher", "hi")
      # Clarification 7: agent removed from active list after completion.
      assert session.get_agent("researcher") is None

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
      with patch("yoker.agent.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_agent_cls.return_value = mock_child
        await session.spawn("researcher", "first")
        await session.spawn("researcher", "second")
      # Both completed; counters reflect two spawns of "researcher".
      assert session._name_counters["researcher"] == 2


class TestSessionBackendFactory:
  """Tests for Session.get_backend — sharing and freshness (7.5.1, 7.5.2)."""

  def test_same_config_returns_same_backend(self) -> None:
    """get_backend is idempotent for the same config (shared backend)."""
    config = Config()
    session = Session(config=config)
    with patch("yoker.session.session.create_backend") as mock_create:
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
    with patch("yoker.session.session.create_backend") as mock_create:
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
  """Tests for Session._load_agents (7.3.1)."""

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
