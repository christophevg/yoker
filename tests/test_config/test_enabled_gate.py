"""Tests for the ``enabled`` master switch on Config.

The ``enabled`` field defaults to ``False``. The user must explicitly set
``enabled = true`` in their config to acknowledge the risks of running an
LLM-powered agent. These tests verify the gate behavior in:

  - Config defaults
  - CLI handlers (check_enabled → abort)
  - Python API (_check_enabled → ConfigurationError)
  - Agent constructor (gate with dev/test bypass)
"""

import os
from unittest.mock import patch

import pytest

from yoker.config import Config
from yoker.exceptions import ConfigurationError


class TestEnabledDefault:
  """The enabled field defaults to False."""

  def test_enabled_defaults_false(self) -> None:
    config = Config()
    assert config.enabled is False

  def test_enabled_can_be_set_true(self) -> None:
    config = Config(enabled=True)
    assert config.enabled is True


class TestCheckEnabledCLIGate:
  """cli.shared.check_enabled aborts when enabled is False (non-dev mode)."""

  def test_aborts_when_disabled(self) -> None:
    from yoker.cli.shared import check_enabled

    config = Config(enabled=False)
    clean_env = {
      k: v for k, v in os.environ.items() if k not in ("YOKER_DEV_MODE", "PYTEST_CURRENT_TEST")
    }
    with patch.dict(os.environ, clean_env, clear=True):
      with pytest.raises(SystemExit) as exc_info:
        check_enabled(config)
    assert exc_info.value.code == 1

  def test_passes_when_enabled(self) -> None:
    from yoker.cli.shared import check_enabled

    config = Config(enabled=True)
    # Should not raise
    check_enabled(config)

  def test_bypassed_in_dev_mode(self) -> None:
    from yoker.cli.shared import check_enabled

    config = Config(enabled=False)
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      # Should not raise
      check_enabled(config)

  def test_bypassed_under_pytest(self) -> None:
    """PYTEST_CURRENT_TEST is set during test runs, so the gate is bypassed."""
    from yoker.cli.shared import check_enabled

    config = Config(enabled=False)
    # PYTEST_CURRENT_TEST is already set by pytest, so this should not raise.
    # But let's be explicit.
    with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test"}):
      check_enabled(config)


class TestCheckEnabledAPIGate:
  """api._check_enabled raises ConfigurationError when enabled is False."""

  def test_raises_when_disabled(self) -> None:
    from yoker.api import _check_enabled

    config = Config(enabled=False)
    # Clear dev/test env vars to test the real gate
    clean_env = {
      k: v for k, v in os.environ.items() if k not in ("YOKER_DEV_MODE", "PYTEST_CURRENT_TEST")
    }
    with patch.dict(os.environ, clean_env, clear=True):
      with pytest.raises(ConfigurationError):
        _check_enabled(config)

  def test_passes_when_enabled(self) -> None:
    from yoker.api import _check_enabled

    config = Config(enabled=True)
    # Should not raise regardless of env
    _check_enabled(config)

  def test_passes_when_config_is_none(self) -> None:
    from yoker.api import _check_enabled

    # None config means deferred to Agent constructor
    _check_enabled(None)

  def test_bypassed_in_dev_mode(self) -> None:
    from yoker.api import _check_enabled

    config = Config(enabled=False)
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      _check_enabled(config)


class TestAgentConstructorGate:
  """Agent.__init__ raises ConfigurationError when enabled is False (non-dev)."""

  def test_raises_when_disabled(self) -> None:
    from yoker.core import Agent

    config = Config(enabled=False)
    clean_env = {
      k: v for k, v in os.environ.items() if k not in ("YOKER_DEV_MODE", "PYTEST_CURRENT_TEST")
    }
    with patch.dict(os.environ, clean_env, clear=True):
      with pytest.raises(ConfigurationError):
        Agent(config=config)

  def test_passes_when_enabled(self) -> None:
    from yoker.core import Agent

    config = Config(enabled=True)
    # Should not raise the enabled gate (may fail later for other reasons,
    # but not with ConfigurationError about "enabled")
    try:
      Agent(config=config)
    except ConfigurationError as e:
      if "enabled" in str(e):
        pytest.fail("Agent raised ConfigurationError about enabled when it was True")
    except Exception:
      # Other errors (no backend, etc.) are fine — we only care about the gate
      pass

  def test_bypassed_in_dev_mode(self) -> None:
    from yoker.core import Agent

    config = Config(enabled=False)
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      try:
        Agent(config=config)
      except ConfigurationError as e:
        if "enabled" in str(e):
          pytest.fail("Agent raised ConfigurationError about enabled in dev mode")
      except Exception:
        pass
