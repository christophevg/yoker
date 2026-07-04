"""Tests for SessionConfig and the [session] config section (MBI-007 7.6)."""

import pytest

from yoker.config import Config, SessionConfig
from yoker.exceptions import ValidationError


class TestSessionConfig:
  """Tests for SessionConfig dataclass (task 7.6.1)."""

  def test_defaults(self) -> None:
    """SessionConfig() yields the design defaults."""
    cfg = SessionConfig()
    assert cfg.max_agents == 10
    assert cfg.default_isolation_policy == "fresh"
    assert cfg.event_aggregation is True

  def test_frozen(self) -> None:
    """SessionConfig is frozen."""
    cfg = SessionConfig()
    with pytest.raises(AttributeError):
      cfg.max_agents = 5  # type: ignore[misc]

  def test_invalid_max_agents_zero(self) -> None:
    """max_agents must be positive."""
    with pytest.raises(ValidationError):
      SessionConfig(max_agents=0)

  def test_invalid_max_agents_negative(self) -> None:
    """max_agents must be positive."""
    with pytest.raises(ValidationError):
      SessionConfig(max_agents=-1)

  def test_invalid_isolation_policy(self) -> None:
    """default_isolation_policy must be fresh or fork."""
    with pytest.raises(ValidationError):
      SessionConfig(default_isolation_policy="shared")

  def test_valid_fork_policy(self) -> None:
    """fork is an accepted isolation policy."""
    cfg = SessionConfig(default_isolation_policy="fork")
    assert cfg.default_isolation_policy == "fork"

  def test_event_aggregation_can_be_disabled(self) -> None:
    """event_aggregation is a plain bool toggle."""
    cfg = SessionConfig(event_aggregation=False)
    assert cfg.event_aggregation is False


class TestConfigSessionField:
  """Tests for Config.session field (task 7.6.2)."""

  def test_config_has_session_with_defaults(self) -> None:
    """Config().session is a SessionConfig with defaults."""
    config = Config()
    assert isinstance(config.session, SessionConfig)
    assert config.session.max_agents == 10
    assert config.session.default_isolation_policy == "fresh"
    assert config.session.event_aggregation is True

  def test_config_session_can_be_overridden(self) -> None:
    """Config accepts a custom SessionConfig."""
    config = Config(session=SessionConfig(max_agents=20))
    assert config.session.max_agents == 20

  def test_config_is_strict_superset(self) -> None:
    """Existing TOML files without [session] still load — superset check."""
    # A Config constructed with no session field explicitly set must work;
    # this mirrors loading an old TOML file that has no [session] section.
    config = Config()
    # Touching every pre-existing section confirms the superset property:
    assert config.harness.name == "yoker"
    assert config.backend.provider == "ollama"
    assert config.context.manager == "basic_persistence"
    assert config.tools.agent.max_recursion_depth == 3
    assert config.ui.mode == "interactive"
    # And the new section is present with defaults:
    assert config.session.max_agents == 10

  def test_recursion_depth_field_unchanged(self) -> None:
    """task 7.6.3: config.tools.agent.max_recursion_depth stays in place."""
    config = Config()
    # The field location is unchanged; only the consumer changes (Session).
    assert config.tools.agent.max_recursion_depth == 3
