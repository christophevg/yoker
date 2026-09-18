"""Tests for the Session-injected stats tool (make_stats_tool)."""

import json
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from yoker.agents import AgentDefinition
from yoker.config import Config, UsageConfig
from yoker.session import Session
from yoker.session.tools import make_stats_tool


def _write_log(path: Any, records: list[dict[str, Any]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w") as f:
    for r in records:
      f.write(json.dumps(r) + "\n")


def _rec(session_id: str, kind: str, **overrides: Any) -> dict[str, Any]:
  base: dict[str, Any] = {
    "ts": "2026-09-16T13:00:00+00:00",
    "session_id": session_id,
    "model": "glm-5.3-flash",
    "agent": "yoker:primary",
    "input_tokens": 0,
    "output_tokens": 0,
    "duration_ms": 0,
    "agent_id": "primary",
    "parent_agent_id": None,
    "kind": kind,
  }
  base.update(overrides)
  return base


@pytest.fixture
def log_path(tmp_path: Any) -> Any:
  return tmp_path / "usage.jsonl"


@pytest.fixture
def sid() -> str:
  """Fixed session id so test records match the tool's session filter."""
  return f"sess-{uuid.uuid4().hex[:8]}"


class TestStatsToolScopes:
  @pytest.mark.asyncio
  async def test_self_scope_counts_caller_records(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    _write_log(
      log_path,
      [
        _rec(sid, kind="llm_call", input_tokens=21503, output_tokens=383, duration_ms=8307),
        _rec(sid, kind="turn", duration_ms=8690),
        _rec(sid, kind="llm_call", agent_id="researcher", input_tokens=900, output_tokens=90),
      ],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="self")

    assert result.success
    assert "[self]" in result.result
    assert "input_tokens: 21503" in result.result
    assert "output_tokens: 383" in result.result
    assert "turns: 1" in result.result

  @pytest.mark.asyncio
  async def test_session_scope_includes_lifecycle_and_self_block(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    _write_log(
      log_path,
      [
        _rec(sid, kind="llm_call", agent_id="primary", input_tokens=100, output_tokens=10),
        _rec(sid, kind="spawn", agent_id="researcher", parent_agent_id="primary"),
        _rec(sid, kind="spawn", agent_id="writer", parent_agent_id="researcher"),
        _rec(sid, kind="llm_call", agent_id="researcher", input_tokens=900, output_tokens=90),
        _rec(sid, kind="release", agent_id="writer"),
      ],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="session")

    assert result.success
    # Both blocks present: requested session scope + self perspective.
    assert "[self]" in result.result and "[session]" in result.result
    assert "spawns: 2" in result.result
    assert "releases: 1" in result.result
    assert "peak_concurrency: 2" in result.result

  @pytest.mark.asyncio
  async def test_subtree_scope_resolves_from_spawn_records(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    _write_log(
      log_path,
      [
        _rec(sid, kind="spawn", agent_id="researcher", parent_agent_id="primary"),
        _rec(sid, kind="llm_call", agent_id="primary", input_tokens=100, output_tokens=10),
        _rec(sid, kind="llm_call", agent_id="researcher", input_tokens=900, output_tokens=90),
        _rec(sid, kind="llm_call", agent_id="other", input_tokens=777, output_tokens=77),
      ],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="subtree")

    assert result.success
    assert "input_tokens: 1000" in result.result  # primary + researcher; other excluded

  @pytest.mark.asyncio
  async def test_subtree_uses_live_map_for_unlogged_children(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    """A live child whose spawn record is missing from the log (e.g. filtered
    by `since`) is still part of the subtree via the session's active map."""
    _write_log(
      log_path,
      [_rec(sid, kind="llm_call", agent_id="child", input_tokens=500, output_tokens=50)],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))

      # Register a stub live child in the active map. The subtree resolver
      # reads only the identity attributes; teardown (__aexit__) needs
      # aclose() + context.close() — provide minimal versions of both.
      stub = SimpleNamespace(
        _agent_id="child",
        _parent_agent_id="primary",
        aclose=AsyncMock(),
        context=SimpleNamespace(close=Mock()),
      )
      session._agents_map["child"] = stub  # type: ignore[index,assignment]

      tool = make_stats_tool(session, caller_id="primary")
      result = await tool(scope="subtree")

    assert result.success
    assert "input_tokens: 500" in result.result  # child included via live map

  @pytest.mark.asyncio
  async def test_since_watermark_keeps_released_child_in_subtree(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    """N2 regression: a child spawned BEFORE the watermark and already
    released (gone from the live map) must still count in the subtree —
    tree resolution uses full history, the watermark only filters
    aggregation. The child's post-watermark records are aggregated."""
    _write_log(
      log_path,
      [
        # Full history: spawn happened at 12:00 (before the watermark).
        _rec(
          sid,
          kind="spawn",
          ts="2026-09-16T12:00:00+00:00",
          agent_id="child",
          parent_agent_id="primary",
        ),
        _rec(sid, kind="release", ts="2026-09-16T12:05:00+00:00", agent_id="child"),
        # Post-watermark work by the released child.
        _rec(
          sid,
          kind="llm_call",
          ts="2026-09-16T14:00:00+00:00",
          agent_id="child",
          input_tokens=333,
          output_tokens=33,
        ),
      ],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="subtree", since="2026-09-16T13:00:00+00:00")

    assert result.success
    # The child's post-watermark tokens ARE reported — tree intact.
    assert "input_tokens: 333" in result.result

  @pytest.mark.asyncio
  async def test_subtree_resolution_is_session_scoped(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    """N1 regression: agent ids are session-local and the log accumulates
    every session — a same-named agent spawned by a DIFFERENT parent in an
    earlier session must not leak into this session's subtree."""
    _write_log(
      log_path,
      [
        # Earlier session: "researcher" spawned by someone else entirely.
        _rec(
          "earlier-session",
          kind="spawn",
          ts="2026-09-15T09:00:00+00:00",
          agent_id="researcher",
          parent_agent_id="unrelated-root",
        ),
        # This session: "researcher" spawned by the caller.
        _rec(
          sid,
          kind="spawn",
          ts="2026-09-16T13:00:00+00:00",
          agent_id="researcher",
          parent_agent_id="primary",
        ),
        _rec(
          sid,
          kind="llm_call",
          ts="2026-09-16T13:01:00+00:00",
          agent_id="researcher",
          input_tokens=50,
          output_tokens=5,
        ),
      ],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="subtree")

    assert result.success
    # The researcher's tokens from THIS session are included (spawned by
    # primary here), and the stale earlier-session link caused no errors.
    assert "input_tokens: 50" in result.result


class TestStatsToolDelta:
  @pytest.mark.asyncio
  async def test_since_filters_strictly_after_watermark(
    self, sid: str, tmp_path: Any, log_path: Any
  ) -> None:
    _write_log(
      log_path,
      [
        _rec(
          sid, kind="llm_call", ts="2026-09-16T12:00:00+00:00", input_tokens=100, output_tokens=10
        ),
        _rec(
          sid, kind="llm_call", ts="2026-09-16T14:00:00+00:00", input_tokens=200, output_tokens=20
        ),
      ],
    )
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="self", since="2026-09-16T12:00:00+00:00")

    assert result.success
    assert "input_tokens: 200" in result.result  # strictly after the watermark
    assert "since: 2026-09-16T12:00:00+00:00" in result.result


class TestStatsToolErrors:
  @pytest.mark.asyncio
  async def test_unknown_scope_is_tool_error(self, sid: str, log_path: Any) -> None:
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(log_path))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="galaxy")

    assert not result.success
    assert "Unknown scope" in (result.error or "")

  @pytest.mark.asyncio
  async def test_missing_log_file_is_tool_error(self, sid: str, tmp_path: Any) -> None:
    missing = tmp_path / "nope" / "usage.jsonl"
    async with Session(config=Config(), session_id=sid) as session:
      session.config.usage = UsageConfig(enabled=True, path=str(missing))
      tool = make_stats_tool(session, caller_id="primary")

      result = await tool(scope="self")

    assert not result.success
    assert "telemetry log" in (result.error or "")


class TestStatsInjection:
  @pytest.mark.asyncio
  async def test_stats_injected_on_session_agents(self, sid: str) -> None:
    """Every session agent (primary included) gets yoker:stats."""
    async with Session(config=Config(), session_id=sid) as session:
      assert "yoker:stats" in session.agent.tools

  @pytest.mark.asyncio
  async def test_stats_stripped_by_explicit_tools_filter(self, sid: str) -> None:
    """Least privilege: an explicit tools: list without stats strips it.

    Exercised through inject_tools directly with a hand-built agent
    (NOT the full _create_agent path — that needs backend/setup mocking);
    inject_tools is where the re-applied definition filter lives, and the
    same semantics are covered for real agents by the session spawn tests.
    Also pins the bare-name grant case: tools: ("stats",) keeps yoker:stats.
    """
    config = Config()
    async with Session(config=config, session_id=sid) as session:
      # Spawn via the internal path with a patched Agent class is heavy;
      # instead verify the filter contract directly on a fresh agent:
      # inject_tools re-applies the definition filter after registration.
      from yoker.core import Agent

      agent = Agent.__new__(Agent)
      # Minimal attributes the filter pass touches:
      agent.definition = AgentDefinition(simple_name="x", description="X", tools=("read",))
      agent.tools = type(session.agent.tools)()  # empty ToolRegistry
      session.inject_tools(agent, "x")
      assert "yoker:stats" not in agent.tools
      assert "yoker:send_message" not in agent.tools  # same filter semantics

      # Bare-name grant: "stats" matches the yoker-prefixed registration.
      granted = Agent.__new__(Agent)
      granted.definition = AgentDefinition(simple_name="y", description="Y", tools=("stats",))
      granted.tools = type(session.agent.tools)()
      session.inject_tools(granted, "y")
      assert "yoker:stats" in granted.tools

  @pytest.mark.asyncio
  async def test_stats_survives_when_other_tools_explicitly_granted(self, sid: str) -> None:
    """An explicit tools: list that DOES include stats keeps it."""
    config = Config()
    async with Session(config=config, session_id=sid) as session:
      from yoker.core import Agent

      agent = Agent.__new__(Agent)
      agent.definition = AgentDefinition(
        simple_name="z", description="Z", tools=("read", "send_message", "stats")
      )
      agent.tools = type(session.agent.tools)()
      session.inject_tools(agent, "z")
      assert "yoker:stats" in agent.tools
