"""Tests for the ``yoker loop <source>`` subcommand handler (MBI-004 task 4.8)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.cli.loop import (
  MAX_CONSECUTIVE_FAILURES,
  _interruptible_sleep,
  _run_loop,
  run_loop,
)
from yoker.config import Config
from yoker.plugins.file_manifest import FileManifestResult


def _make_loop_config(
  source: str = "pkgq",
  interval: int = 0,
  max_iterations: int = 3,
  max_duration: int | None = None,
  persist: bool = False,
  session_id: str | None = None,
) -> MagicMock:
  """Build a mock LoopConfig for testing."""
  cfg = MagicMock()
  cfg.source = source
  cfg.interval = interval
  cfg.max_iterations = max_iterations
  cfg.max_duration = max_duration
  cfg.persist = persist
  cfg.session_id = session_id
  cfg.logging = Config().logging
  cfg.ui = Config().ui
  cfg.tools = Config().tools
  cfg.context = Config().context
  return cfg


def _make_resolved(
  kind: str = "module",
  trust_key: str = "module:pkgq",
  manifest: FileManifestResult | None = None,
  cleanup: MagicMock | None = None,
) -> MagicMock:
  resolved = MagicMock()
  resolved.kind = kind
  resolved.source_string = "pkgq"
  resolved.path = Path("/tmp/fake")
  resolved.trust_key = trust_key
  resolved.manifest = manifest
  resolved.cleanup = cleanup
  return resolved


def _make_loaded(
  agent: str | None = "coder",
  prompt: str | None = "do stuff",
  cleanup: MagicMock | None = None,
) -> MagicMock:
  loaded = MagicMock()
  loaded.agent = agent
  loaded.prompt = prompt
  loaded.cleanup = cleanup
  loaded.components = MagicMock()
  loaded.components.tools = []
  loaded.components.skills = []
  loaded.components.agents = []
  loaded.components.source = "pkgq"
  return loaded


class TestRunLoopMissingSource:
  """Missing source -> clear error, exit non-zero."""

  def test_no_source_errors(self) -> None:
    config = _make_loop_config(source="")

    with (
      patch("yoker.cli.loop.load_subcommand_config", return_value=config),
      patch("yoker.cli.loop.configure_logging"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_loop([])

    assert exc.value.code == 1


class TestRunLoopTrustGate:
  """Trust gate fires ONCE before load_source."""

  def test_untrusted_source_aborts_without_load(self) -> None:
    resolved = _make_resolved()
    config = _make_loop_config()

    with (
      patch("yoker.cli.loop.load_subcommand_config", return_value=config),
      patch("yoker.cli.loop.resolve_source", return_value=resolved),
      patch("yoker.cli.loop.check_source_allowed", return_value=False) as m_check,
      patch("yoker.cli.loop.load_source") as m_load,
      patch("yoker.cli.loop.configure_logging"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_loop([])

    assert exc.value.code == 1
    m_check.assert_called_once()
    m_load.assert_not_called()

  def test_trusted_source_loads_once(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(cleanup=MagicMock())
    config = _make_loop_config(max_iterations=1)

    with (
      patch("yoker.cli.loop.load_subcommand_config", return_value=config),
      patch("yoker.cli.loop.resolve_source", return_value=resolved),
      patch("yoker.cli.loop.check_source_allowed", return_value=True),
      patch("yoker.cli.loop.load_source", return_value=loaded) as m_load,
      patch("yoker.cli.loop.configure_logging"),
      patch("yoker.cli.loop.asyncio.run"),
    ):
      run_loop([])

    m_load.assert_called_once_with(resolved)


class TestRunLoopMissingAgentOrPrompt:
  """Missing agent or prompt -> clear error, exit non-zero."""

  def test_missing_agent_errors(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(agent=None, prompt="do X")
    config = _make_loop_config()

    with (
      patch("yoker.cli.loop.load_subcommand_config", return_value=config),
      patch("yoker.cli.loop.resolve_source", return_value=resolved),
      patch("yoker.cli.loop.check_source_allowed", return_value=True),
      patch("yoker.cli.loop.load_source", return_value=loaded),
      patch("yoker.cli.loop.configure_logging"),
      patch("yoker.cli.loop.asyncio.run"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_loop([])

    assert exc.value.code == 1

  def test_missing_prompt_errors(self) -> None:
    resolved = _make_resolved()
    loaded = _make_loaded(agent="coder", prompt=None)
    config = _make_loop_config()

    with (
      patch("yoker.cli.loop.load_subcommand_config", return_value=config),
      patch("yoker.cli.loop.resolve_source", return_value=resolved),
      patch("yoker.cli.loop.check_source_allowed", return_value=True),
      patch("yoker.cli.loop.load_source", return_value=loaded),
      patch("yoker.cli.loop.configure_logging"),
      patch("yoker.cli.loop.asyncio.run"),
    ):
      with pytest.raises(SystemExit) as exc:
        run_loop([])

    assert exc.value.code == 1


class TestRunLoopMaxIterations:
  """Loop runs N iterations with --max-iterations."""

  def test_loop_runs_n_iterations(self, capsys) -> None:
    config = _make_loop_config(max_iterations=3, interval=0)
    loaded = _make_loaded()

    call_count = 0

    async def fake_iteration(*args, **kwargs):
      nonlocal call_count
      call_count += 1

    with (
      patch("yoker.cli.loop._run_iteration", side_effect=fake_iteration),
      patch("yoker.cli.loop._interruptible_sleep", new_callable=AsyncMock),
    ):
      asyncio.run(_run_loop(config, loaded, "coder", "do X", [], None, 300))

    assert call_count == 3
    out = capsys.readouterr().out
    assert "Iteration 1/3" in out
    assert "Iteration 3/3" in out
    assert "3 iterations completed" in out


class TestRunLoopStopsAfterFailures:
  """Loop stops after 3 consecutive failures."""

  def test_stops_after_three_failures(self, capsys) -> None:
    config = _make_loop_config(max_iterations=10, interval=0)
    loaded = _make_loaded()

    async def failing_iteration(*args, **kwargs):
      raise RuntimeError("boom")

    with (
      patch("yoker.cli.loop._run_iteration", side_effect=failing_iteration),
      patch("yoker.cli.loop._interruptible_sleep", new_callable=AsyncMock),
    ):
      asyncio.run(_run_loop(config, loaded, "coder", "do X", [], None, 300))

    out = capsys.readouterr().out
    assert f"{MAX_CONSECUTIVE_FAILURES} consecutive failures" in out
    # Should NOT have run 10 iterations.
    assert "Iteration 10/10" not in out


class TestRunLoopBackoff:
  """Exponential backoff is applied after failures."""

  def test_backoff_increases_with_failures(self, capsys) -> None:
    config = _make_loop_config(max_iterations=10, interval=0)
    loaded = _make_loaded()

    async def failing(*args, **kwargs):
      raise RuntimeError("boom")

    sleep_calls: list[int] = []

    async def fake_sleep(seconds, stop_flag):
      sleep_calls.append(seconds)

    with (
      patch("yoker.cli.loop._run_iteration", side_effect=failing),
      patch("yoker.cli.loop._interruptible_sleep", side_effect=fake_sleep),
    ):
      asyncio.run(_run_loop(config, loaded, "coder", "do X", [], None, 300))

    # Backoff sleeps: 2**1=2, 2**2=4, 2**3=8 (before 3rd failure stops).
    backoff_sleeps = [s for s in sleep_calls if s in (2, 4, 8)]
    assert len(backoff_sleeps) >= 1
    assert 2 in backoff_sleeps


class TestRunLoopMaxDuration:
  """Loop stops when --max-duration is reached."""

  def test_max_duration_stops_loop(self, capsys) -> None:
    config = _make_loop_config(max_iterations=100, interval=0, max_duration=0)
    loaded = _make_loaded()

    async def fake_iteration(*args, **kwargs):
      pass

    with (
      patch("yoker.cli.loop._run_iteration", side_effect=fake_iteration),
      patch("yoker.cli.loop._interruptible_sleep", new_callable=AsyncMock),
    ):
      asyncio.run(_run_loop(config, loaded, "coder", "do X", [], None, 300))

    out = capsys.readouterr().out
    assert "max duration reached" in out


class TestInterruptibleSleep:
  """_interruptible_sleep wakes early when stop_flag is set."""

  def test_sleep_returns_after_timeout(self) -> None:
    stop_flag = asyncio.Event()

    async def run():
      await _interruptible_sleep(0, stop_flag)

    asyncio.run(run())  # should not hang

  def test_sleep_wakes_on_stop_flag(self) -> None:
    stop_flag = asyncio.Event()

    async def run():
      stop_flag.set()
      await _interruptible_sleep(100, stop_flag)

    asyncio.run(run())  # should return immediately due to stop_flag


class TestRunLoopCleanup:
  """Source cleanup is called after the loop."""

  def test_cleanup_called_after_loop(self) -> None:
    resolved = _make_resolved()
    cleanup = MagicMock()
    loaded = _make_loaded(cleanup=cleanup)
    config = _make_loop_config(max_iterations=1)

    with (
      patch("yoker.cli.loop.load_subcommand_config", return_value=config),
      patch("yoker.cli.loop.resolve_source", return_value=resolved),
      patch("yoker.cli.loop.check_source_allowed", return_value=True),
      patch("yoker.cli.loop.load_source", return_value=loaded),
      patch("yoker.cli.loop.configure_logging"),
      patch("yoker.cli.loop.asyncio.run"),
    ):
      run_loop([])

    cleanup.assert_called_once()
