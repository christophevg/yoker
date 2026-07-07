"""Edge-case tests for Session spawn resolution, config derivation, and tool
rendering (coverage gaps).

Targets the specific uncovered lines in ``src/yoker/session/``:

  - ``session.py`` lines 286-289: ``spawn`` resolution failure paths
    (``ValueError`` re-raise and generic-``Exception`` wrapping).
  - ``session.py`` lines 511-520: ``_derive_config`` model-override branch.
  - ``tools.py`` line 52: ``_clamp`` bounds.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config
from yoker.session import Session
from yoker.session.tools import (
  ABSOLUTE_MAX_TIMEOUT_SECONDS,
  _clamp,
)


class TestSpawnResolutionFailure:
  """Tests for Session.spawn resolution failure paths (session.py 286-289)."""

  @pytest.mark.asyncio
  async def test_spawn_re_raises_value_error_from_registry(self) -> None:
    """When registry.resolve raises ValueError, spawn re-raises it unchanged.

    Covers session.py lines 286-287: the ``except ValueError: raise`` branch.
    """
    config = Config()
    async with Session(config=config) as session:
      # Make the registry's resolve raise ValueError (unknown agent name).
      with patch.object(session.agents, "resolve", side_effect=ValueError("not found")):
        with pytest.raises(ValueError, match="not found"):
          await session.spawn("ghost")
      # No agent was registered.
      assert session.get_agent("ghost") is None

  @pytest.mark.asyncio
  async def test_spawn_wraps_non_value_error_from_registry(self) -> None:
    """When registry.resolve raises a non-ValueError, spawn wraps it in ValueError.

    Covers session.py lines 288-289: the ``except Exception as e: raise
    ValueError(...) from e`` branch.
    """
    config = Config()
    async with Session(config=config) as session:
      with patch.object(
        session.agents,
        "resolve",
        side_effect=RuntimeError("registry corrupted"),
      ):
        with pytest.raises(ValueError, match="Agent resolution failed"):
          await session._spawn_and_run("researcher", "hi")
      assert session.get_agent("researcher") is None


class TestDeriveConfigModelOverride:
  """Tests for Session._derive_config with a model override (session.py 511-520)."""

  def test_derive_config_returns_parent_when_no_model_override(self) -> None:
    """No model on the definition → parent config returned unchanged (shared backend)."""
    config = Config()
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
      model=None,
    )
    derived = Session._derive_config(config, agent_def)
    assert derived is config

  def test_derive_config_applies_model_override(self) -> None:
    """A model override produces a derived config with the new model on the
    active provider's sub-config.

    Covers session.py lines 511-520: the ``dataclasses.replace`` branch that
    builds a new backend with the overridden model.
    """
    from yoker.config import BackendConfig, OllamaConfig

    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="original-model")))
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
      model="cheaper-model",
    )
    derived = Session._derive_config(config, agent_def)
    # The derived config has a different backend with the overridden model.
    assert derived is not config
    assert derived.backend.config.model == "cheaper-model"
    # The parent config is untouched (frozen dataclass).
    assert config.backend.config.model == "original-model"

  def test_derive_config_preserves_provider(self) -> None:
    """The derived config keeps the same provider as the parent."""
    from yoker.config import BackendConfig, OllamaConfig

    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="a")))
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
      model="b",
    )
    derived = Session._derive_config(config, agent_def)
    assert derived.backend.provider == config.backend.provider

  @pytest.mark.asyncio
  async def test_spawn_with_model_override_uses_fresh_backend(self) -> None:
    """End-to-end: spawning an agent with a model override goes through the
    ``_derive_config`` model-override branch and gets a fresh backend."""
    from yoker.config import BackendConfig, OllamaConfig

    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="parent-model")))
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
      model="child-model",
    )
    async with Session(config=config) as session:
      session.agents.register(agent_def)
      # Patch Agent so spawn doesn't construct a real one.
      with patch("yoker.core.Agent") as mock_agent_cls:
        mock_child = MagicMock()
        mock_child.process = AsyncMock(return_value="ok")
        mock_child.tools = MagicMock()
        mock_agent_cls.return_value = mock_child
        # Patch create_backend to verify a fresh backend is created for the
        # new provider signature (model override → different cache key).
        with patch("yoker.session.session.create_backend") as mock_create:
          mock_backend = MagicMock()
          mock_create.return_value = mock_backend
          await session._spawn_and_run("researcher", "hi")
        # A fresh backend was created (not cached from the parent config).
        mock_create.assert_called_once()

  def test_derive_config_model_override_does_not_mutate_parent_subconfig(self) -> None:
    """The parent config's sub-config object is not mutated by the override."""
    from yoker.config import BackendConfig, OllamaConfig

    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="a")))
    agent_def = AgentDefinition(
      simple_name="researcher",
      description="Researcher",
      tools=("read",),
      model="b",
    )
    _ = Session._derive_config(config, agent_def)
    # Parent's sub-config still has its original model.
    assert config.backend.config.model == "a"


class TestClamp:
  """Tests for _clamp bounds (tools.py line 52)."""

  def test_clamp_below_minimum_returns_minimum(self) -> None:
    """A value below the minimum is clamped up to the minimum."""
    assert _clamp(0, 1, ABSOLUTE_MAX_TIMEOUT_SECONDS) == 1

  def test_clamp_above_maximum_returns_maximum(self) -> None:
    """A value above the maximum is clamped down to the maximum."""
    assert _clamp(10_000, 1, ABSOLUTE_MAX_TIMEOUT_SECONDS) == ABSOLUTE_MAX_TIMEOUT_SECONDS

  def test_clamp_in_range_returns_value(self) -> None:
    """A value within the range is returned unchanged."""
    assert _clamp(60, 1, ABSOLUTE_MAX_TIMEOUT_SECONDS) == 60


class TestSpawnTimeoutDefaultClamping:
  """Integration: the ``agent`` tool clamps the timeout to [1, ABSOLUTE_MAX]."""

  @pytest.mark.asyncio
  async def test_timeout_below_minimum_clamped_to_one(self) -> None:
    """A timeout below 1 is clamped to 1 second before being forwarded."""
    from yoker.session.tools import make_spawn_agent_tool

    session = MagicMock()
    session.agents = MagicMock()
    session.agents.names = []
    session._spawn_and_run = AsyncMock(return_value=("r", "ok"))
    requester = MagicMock()
    requester.definition = AgentDefinition(
      simple_name="parent",
      description="Parent",
      tools=("read",),
      agents=("researcher",),
    )
    tool = make_spawn_agent_tool(session, requester)
    await tool(agent_name="researcher", prompt="hi", timeout_seconds=-5)
    call_kwargs = session._spawn_and_run.call_args.kwargs
    assert call_kwargs["timeout_seconds"] == 1

  @pytest.mark.asyncio
  async def test_timeout_above_max_clamped_to_absolute_max(self) -> None:
    """A timeout above ABSOLUTE_MAX_TIMEOUT_SECONDS is clamped down."""
    from yoker.session.tools import make_spawn_agent_tool

    session = MagicMock()
    session.agents = MagicMock()
    session.agents.names = []
    session._spawn_and_run = AsyncMock(return_value=("r", "ok"))
    requester = MagicMock()
    requester.definition = AgentDefinition(
      simple_name="parent",
      description="Parent",
      tools=("read",),
      agents=("researcher",),
    )
    tool = make_spawn_agent_tool(session, requester)
    await tool(agent_name="researcher", prompt="hi", timeout_seconds=99_999)
    call_kwargs = session._spawn_and_run.call_args.kwargs
    assert call_kwargs["timeout_seconds"] == ABSOLUTE_MAX_TIMEOUT_SECONDS


__all__ = [
  "TestSpawnResolutionFailure",
  "TestDeriveConfigModelOverride",
  "TestClamp",
  "TestSpawnTimeoutDefaultClamping",
]
