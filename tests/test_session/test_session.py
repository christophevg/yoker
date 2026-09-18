"""Tests for the Session class — async context manager + lifecycle."""

import asyncio
import json
import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.config import Config, UsageConfig
from yoker.events import SessionEndEvent, SessionStartEvent
from yoker.session import Session


class TestSessionLifecycle:
  """Tests for Session async context manager."""

  def test_session_id_auto_generated(self) -> None:
    """Session generates a non-empty id when none is provided."""
    session = Session(config=Config())
    assert isinstance(session.id, str)
    assert session.id != ""

  def test_session_id_explicit(self) -> None:
    """Session honours an explicit session_id argument."""
    session = Session(config=Config(), session_id="audit-2026-07-04")
    assert session.id == "audit-2026-07-04"

  def test_session_ids_are_unique(self) -> None:
    """Two sessions get different ids."""
    a = Session(config=Config())
    b = Session(config=Config())
    assert a.id != b.id

  @pytest.mark.asyncio
  async def test_aenter_aexit_clean(self) -> None:
    """async with Session(...) enters and exits cleanly."""
    async with Session(config=Config()) as session:
      assert session.id != ""
    # Exiting should not raise.

  @pytest.mark.asyncio
  async def test_emits_session_start_on_enter(self) -> None:
    """SESSION_START is emitted on __aenter__."""
    session = Session(config=Config())
    received: list = []
    session.on_event(lambda e: received.append(e))
    async with session:
      pass
    start_events = [e for e in received if isinstance(e, SessionStartEvent)]
    assert len(start_events) == 1
    assert start_events[0].session_id == session.id

  @pytest.mark.asyncio
  async def test_emits_session_end_on_exit(self) -> None:
    """SESSION_END is emitted on __aexit__."""
    session = Session(config=Config())
    received: list = []
    session.on_event(lambda e: received.append(e))
    async with session:
      pass
    end_events = [e for e in received if isinstance(e, SessionEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].session_id == session.id

  @pytest.mark.asyncio
  async def test_run_bracket_written_to_usage_log(self, tmp_path: Any, monkeypatch: Any) -> None:
    """R3: entering/exiting the session context writes run_start/run_end
    to the usage log — outcome completed, positive duration, agents_active.

    delenv(PYTEST_CURRENT_TEST) lets the usage logger write but would
    also strip the enabled-gate's pytest bypass — YOKER_DEV_MODE=1
    re-supplies the gate bypass without blocking usage logging."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    log_path = tmp_path / "usage.jsonl"

    session = Session(config=Config(), session_id="run-bracket-test")
    session.config.usage = UsageConfig(enabled=True, path=str(log_path))
    async with session:
      pass

    with open(log_path) as f:
      records = [json.loads(line) for line in f if line.strip()]
    run_records = [r for r in records if r.get("kind", "").startswith("run_")]
    assert [r["kind"] for r in run_records] == ["run_start", "run_end"]
    assert all(r["session_id"] == "run-bracket-test" for r in run_records)
    assert run_records[0]["detail"]["pid"] == os.getpid()
    assert run_records[1]["detail"]["outcome"] == "completed"
    assert run_records[1]["detail"]["duration_ms"] >= 0
    assert run_records[1]["detail"]["agents_active"] == 1  # primary only

  @pytest.mark.asyncio
  async def test_run_end_logs_error_outcome_on_exception(
    self, tmp_path: Any, monkeypatch: Any
  ) -> None:
    """An exception escaping the context marks run_end outcome=error with
    the error summary, and the bracket still closes."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    log_path = tmp_path / "usage.jsonl"

    session = Session(config=Config(), session_id="run-error-test")
    session.config.usage = UsageConfig(enabled=True, path=str(log_path))
    with pytest.raises(RuntimeError, match="boom"):
      async with session:
        raise RuntimeError("boom")

    with open(log_path) as f:
      records = [json.loads(line) for line in f if line.strip()]
    run_end = [r for r in records if r.get("kind") == "run_end"]
    assert len(run_end) == 1  # bracket closed despite the exception
    assert run_end[0]["detail"]["outcome"] == "error"
    assert "RuntimeError: boom" in run_end[0]["detail"]["error"]

  @pytest.mark.asyncio
  async def test_run_end_written_before_teardown_releases(
    self, tmp_path: Any, monkeypatch: Any
  ) -> None:
    """run_end is written FIRST in __aexit__ — even if teardown then
    raises, the bracket is closed (crash detection stays honest). The
    exc parameter only carries BODY exceptions, so a clean body yields
    outcome=completed even when teardown subsequently fails."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    log_path = tmp_path / "usage.jsonl"

    session = Session(config=Config(), session_id="run-teardown-test")
    session.config.usage = UsageConfig(enabled=True, path=str(log_path))

    from unittest.mock import AsyncMock

    with pytest.raises(RuntimeError, match="teardown fail"):
      async with session:
        # Sabotage teardown: aclose raises.
        session._agents_map["primary"].aclose = AsyncMock(side_effect=RuntimeError("teardown fail"))  # type: ignore[union-attr]

    # Teardown raised and propagated — but run_end was written first.
    with open(log_path) as f:
      records = [json.loads(line) for line in f if line.strip()]
    run_end = [r for r in records if r.get("kind") == "run_end"]
    assert len(run_end) == 1
    # Body was clean, so outcome reflects the body — but the bracket
    # CLOSED despite the teardown failure (the point of writing first).
    assert run_end[0]["detail"]["outcome"] == "completed"

  @pytest.mark.asyncio
  async def test_outstanding_tasks_cancelled_on_exit(self) -> None:
    """On __aexit__, outstanding spawned tasks are cancelled."""
    session = Session(config=Config())

    async def long_running() -> None:
      try:
        await asyncio.sleep(10)
      except asyncio.CancelledError:
        raise

    async with session:
      # Simulate a tracked spawned task by scheduling one through _emit
      # via an async handler — but we want a real task in _tasks.
      task = asyncio.ensure_future(long_running())
      session._tasks.add(task)

    # After exit, the task must be cancelled.
    assert task.cancelled() or task.done()

  def test_on_event_stores_handler(self) -> None:
    """on_event appends to the internal handler list."""

    def h1(event) -> None:
      pass

    def h2(event) -> None:
      pass

    session = Session(config=Config())
    session.on_event(h1)
    session.on_event(h2)
    assert h1 in session._event_handlers
    assert h2 in session._event_handlers


class TestSessionAgentMap:
  """Tests for name→agent map and name disambiguation."""

  def test_get_agent_returns_none_when_empty(self) -> None:
    """get_agent returns None when no agent with that name exists."""
    session = Session(config=Config())
    assert session.get_agent("researcher") is None

  def test_get_agent_returns_instance(self) -> None:
    """get_agent returns the registered agent instance."""
    session = Session(config=Config())
    fake_agent = MagicMock(name="researcher-agent")
    session._agents_map["researcher"] = fake_agent
    assert session.get_agent("researcher") is fake_agent

  def test_generate_agent_name_first_is_bare(self) -> None:
    """First spawn of a definition name returns the bare name (D2)."""
    session = Session(config=Config())
    assert session._generate_agent_name("researcher") == "researcher"

  def test_generate_agent_name_second_is_suffixed(self) -> None:
    """Second spawn of the same name gets -2 suffix (D2)."""
    session = Session(config=Config())
    session._generate_agent_name("researcher")
    assert session._generate_agent_name("researcher") == "researcher-2"

  def test_generate_agent_name_third_is_suffixed(self) -> None:
    """Third spawn of the same name gets -3 suffix (D2)."""
    session = Session(config=Config())
    session._generate_agent_name("researcher")
    session._generate_agent_name("researcher")
    assert session._generate_agent_name("researcher") == "researcher-3"

  def test_generate_agent_name_independent_per_definition(self) -> None:
    """Disambiguation counters are tracked per definition name."""
    session = Session(config=Config())
    session._generate_agent_name("researcher")
    session._generate_agent_name("researcher")
    # A different definition name is unaffected by the researcher counter.
    assert session._generate_agent_name("reviewer") == "reviewer"
