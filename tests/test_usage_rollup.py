"""Tests for the stats rollup (yoker.usage.rollup) — pure record math."""

from typing import Any

import pytest

from yoker.usage.rollup import (
  SCOPES,
  peak_concurrency,
  render_stats,
  rollup,
  subtree_ids,
)


def _rec(kind: str, **overrides: Any) -> dict[str, Any]:
  base: dict[str, Any] = {
    "ts": "2026-09-16T13:00:00+00:00",
    "session_id": "sess-1",
    "model": "glm-5.3-flash",
    "agent": "yoker:primary",
    "input_tokens": 0,
    "output_tokens": 0,
    "duration_ms": 0,
    "agent_id": "primary",
    "parent_agent_id": None,
  }
  base.update({"kind": kind})
  base.update(overrides)
  return base


class TestSubtreeIds:
  """Spawn-tree resolution from spawn records + live parent map."""

  def test_no_spawn_records_yields_caller_only(self) -> None:
    records = [_rec(kind="llm_call", agent_id="primary")]
    assert subtree_ids("primary", records) == {"primary"}

  def test_direct_child_from_spawn_record(self) -> None:
    records = [
      _rec(kind="spawn", agent_id="researcher", parent_agent_id="primary"),
      _rec(kind="llm_call", agent_id="researcher"),
    ]
    assert subtree_ids("primary", records) == {"primary", "researcher"}

  def test_transitive_grandchild(self) -> None:
    records = [
      _rec(kind="spawn", agent_id="researcher", parent_agent_id="primary"),
      _rec(kind="spawn", agent_id="writer", parent_agent_id="researcher"),
    ]
    assert subtree_ids("primary", records) == {"primary", "researcher", "writer"}

  def test_sibling_excluded(self) -> None:
    records = [
      _rec(kind="spawn", agent_id="researcher", parent_agent_id="primary"),
      _rec(kind="spawn", agent_id="reviewer", parent_agent_id="other-agent"),
    ]
    assert "reviewer" not in subtree_ids("primary", records)

  def test_live_parents_unioned(self) -> None:
    # No spawn records in the log window — the live map supplies the link.
    records: list[dict[str, Any]] = []
    result = subtree_ids(
      "primary", records, live_parents={"primary": None, "researcher": "primary"}
    )
    assert result == {"primary", "researcher"}

  def test_child_spawned_before_watermark_resolves_via_live_map(self) -> None:
    # Spawn record filtered out by `since`, but the child is still live.
    records = [_rec(kind="llm_call", agent_id="researcher")]
    result = subtree_ids(
      "primary",
      records,
      live_parents={"researcher": "primary", "primary": None},
    )
    assert result == {"primary", "researcher"}

  def test_child_connected_to_caller_terminates_on_parent_cycle(self) -> None:
    """Corrupt parent chains may loop (a→b→a). A cycle disconnected from
    the caller never joins the subtree; BFS must terminate regardless."""
    records = [
      _rec(kind="spawn", agent_id="child", parent_agent_id="primary"),
      _rec(kind="spawn", agent_id="a", parent_agent_id="b"),
      _rec(kind="spawn", agent_id="b", parent_agent_id="a"),
    ]
    result = subtree_ids("primary", records)
    assert result == {"primary", "child"}

  def test_cycle_through_caller_terminates(self) -> None:
    """A cycle that passes through the caller still terminates and
    includes the reachable members."""
    records = [
      _rec(kind="spawn", agent_id="a", parent_agent_id="primary"),
      _rec(kind="spawn", agent_id="b", parent_agent_id="a"),
      # corrupt back-edge: primary's parent recorded as b
      _rec(kind="spawn", agent_id="primary", parent_agent_id="b"),
    ]
    result = subtree_ids("primary", records)
    assert result == {"primary", "a", "b"}


class TestPeakConcurrency:
  def test_no_spawns_returns_none(self) -> None:
    assert peak_concurrency([_rec(kind="llm_call")], "sess-1") is None

  def test_sequential_spawns_peak_two(self) -> None:
    records = [
      _rec(kind="spawn", ts="2026-09-16T13:00:01+00:00", agent_id="a"),
      _rec(kind="spawn", ts="2026-09-16T13:00:02+00:00", agent_id="b"),
      _rec(kind="release", ts="2026-09-16T13:00:03+00:00", agent_id="a"),
      _rec(kind="release", ts="2026-09-16T13:00:04+00:00", agent_id="b"),
    ]
    assert peak_concurrency(records, "sess-1") == 2

  def test_overlapping_spawns_peak_two_then_drop(self) -> None:
    records = [
      _rec(kind="spawn", ts="2026-09-16T13:00:01+00:00", agent_id="a"),
      _rec(kind="release", ts="2026-09-16T13:00:02+00:00", agent_id="a"),
      _rec(kind="spawn", ts="2026-09-16T13:00:03+00:00", agent_id="b"),
    ]
    assert peak_concurrency(records, "sess-1") == 1

  def test_unreleased_agents_stay_active(self) -> None:
    # Teardown releases are not logged — the peak sees them still active.
    records = [
      _rec(kind="spawn", ts="2026-09-16T13:00:01+00:00", agent_id="a"),
      _rec(kind="spawn", ts="2026-09-16T13:00:02+00:00", agent_id="b"),
    ]
    assert peak_concurrency(records, "sess-1") == 2

  def test_release_without_spawn_never_lowers_peak(self) -> None:
    # Corrupt log (release with no matching spawn): active goes negative
    # but peak floor-stays at max(0, ...) — and the ghost release consumes
    # the later spawn's delta (net 0). Fail-soft: no crash, no negative peak.
    records = [
      _rec(kind="release", ts="2026-09-16T13:00:01+00:00", agent_id="ghost"),
      _rec(kind="spawn", ts="2026-09-16T13:00:02+00:00", agent_id="a"),
    ]
    assert peak_concurrency(records, "sess-1") == 0

  def test_other_sessions_excluded(self) -> None:
    records = [
      _rec(kind="spawn", ts="2026-09-16T13:00:01+00:00", agent_id="a", session_id="other"),
      _rec(kind="spawn", ts="2026-09-16T13:00:02+00:00", agent_id="b", session_id="sess-1"),
    ]
    assert peak_concurrency(records, "sess-1") == 1


class TestRollup:
  """Scope selection + per-kind aggregation."""

  def test_token_invariant_held_in_rollup(self) -> None:
    records = [
      _rec(kind="llm_call", input_tokens=21503, output_tokens=383, duration_ms=8307),
      _rec(kind="turn", duration_ms=8690),
      _rec(kind="tool_call", tool="yoker__read", success=True, bytes_in=57, bytes_out=1204),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["input_tokens"] == 21503
    assert r["output_tokens"] == 383
    assert r["llm_calls"] == 1
    assert r["llm_wall_ms"] == 8307
    assert r["turns"] == 1
    assert r["turn_wall_ms"] == 8690
    assert r["tool_calls"] == 1
    assert r["tool_failures"] == 0
    assert r["tool_bytes_in"] == 57
    assert r["tool_bytes_out"] == 1204
    assert r["errors"] == 0
    assert r["compactions"] == 0
    # session scope carries lifecycle metrics (present, zero here):
    assert r["spawns"] == 0
    assert r["releases"] == 0

  def test_tool_failures_counted(self) -> None:
    records = [
      _rec(kind="tool_call", tool="yoker__write", success=False, bytes_in=20, bytes_out=88),
      _rec(kind="tool_call", tool="yoker__read", success=True, bytes_in=10, bytes_out=5),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["tool_calls"] == 2
    assert r["tool_failures"] == 1

  def test_compaction_dropped_summed_from_detail(self) -> None:
    records = [
      _rec(
        kind="compaction",
        detail={"run": {"run_id": "run-1", "dropped_count": 5}},
      ),
      _rec(kind="compaction", detail={"run": {"dropped_count": 2}}),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["compactions"] == 2
    assert r["compaction_dropped_messages"] == 7

  def test_compaction_defensive_variants_never_crash(self) -> None:
    """Corrupt detail shapes (N4): detail=None, non-dict detail,
    run=None, run non-dict, dropped_count missing/None — all count the
    compaction but contribute 0 dropped messages."""
    records = [
      _rec(kind="compaction", detail=None),
      _rec(kind="compaction", detail="not-a-dict"),
      _rec(kind="compaction", detail={"run": None}),
      _rec(kind="compaction", detail={"run": "nope"}),
      _rec(kind="compaction", detail={"run": {}}),
      _rec(kind="compaction", detail={"run": {"dropped_count": None}}),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["compactions"] == 6
    assert r["compaction_dropped_messages"] == 0

  def test_errors_counted(self) -> None:
    records = [
      _rec(kind="error", tool="idle_watchdog", success=False),
      _rec(kind="error", tool="tool_failure_escalation", success=False),
      _rec(kind="llm_call", input_tokens=10, output_tokens=1),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["errors"] == 2

  def test_session_scope_without_spawns_has_no_peak_key(self) -> None:
    """peak_concurrency returns None when the session has no spawn
    records — the key is then ABSENT from the rollup result (rendered
    blocks stay honest instead of showing peak_concurrency: None)."""
    r = rollup([_rec(kind="llm_call")], session_id="sess-1", scope="session")
    assert "peak_concurrency" not in r

  def test_self_scope_filters_by_agent_id(self) -> None:
    records = [
      _rec(kind="llm_call", agent_id="primary", input_tokens=100, output_tokens=10),
      _rec(kind="llm_call", agent_id="researcher", input_tokens=900, output_tokens=90),
    ]
    r = rollup(records, session_id="sess-1", scope="self", agent_ids={"primary"})
    assert r["input_tokens"] == 100
    assert r["llm_calls"] == 1

  def test_subtree_scope_includes_descendants(self) -> None:
    records = [
      _rec(kind="llm_call", agent_id="primary", input_tokens=100, output_tokens=10),
      _rec(kind="llm_call", agent_id="researcher", input_tokens=900, output_tokens=90),
      _rec(kind="llm_call", agent_id="writer", input_tokens=500, output_tokens=50),
    ]
    r = rollup(records, session_id="sess-1", scope="subtree", agent_ids={"primary", "researcher"})
    assert r["input_tokens"] == 1000  # primary (100) + researcher (900); writer excluded

  def test_session_scope_filters_by_session(self) -> None:
    records = [
      _rec(kind="llm_call", session_id="sess-1", input_tokens=100, output_tokens=10),
      _rec(kind="llm_call", session_id="other", input_tokens=999, output_tokens=99),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["input_tokens"] == 100

  def test_session_scope_includes_lifecycle(self) -> None:
    records = [
      _rec(kind="spawn", agent_id="a"),
      _rec(kind="spawn", agent_id="b"),
      _rec(kind="release", agent_id="a"),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["spawns"] == 2
    assert r["releases"] == 1
    assert r["peak_concurrency"] == 2

  def test_unknown_scope_raises(self) -> None:
    with pytest.raises(ValueError, match="Unknown scope"):
      rollup([], session_id="sess-1", scope="galaxy")

  def test_self_without_ids_raises(self) -> None:
    with pytest.raises(ValueError, match="requires agent_ids"):
      rollup([], session_id="sess-1", scope="self")

  def test_since_watermark_semantics_are_caller_side(self) -> None:
    """rollup itself does NOT filter by ts — the tool filters before calling
    (documented contract); this test pins that records pass through."""
    records = [
      _rec(kind="llm_call", ts="2026-09-16T12:00:00+00:00", input_tokens=100, output_tokens=10),
      _rec(kind="llm_call", ts="2026-09-16T14:00:00+00:00", input_tokens=200, output_tokens=20),
    ]
    r = rollup(records, session_id="sess-1", scope="session")
    assert r["input_tokens"] == 300

  def test_scopes_tuple_complete(self) -> None:
    assert SCOPES == ("self", "subtree", "session")


class TestRenderStats:
  def test_renders_scope_blocks(self) -> None:
    text = render_stats(
      {
        "self": {"scope": "self", "turns": 1, "input_tokens": 100},
        "session": {"scope": "session", "turns": 3, "input_tokens": 900},
      }
    )
    assert "[self]" in text
    assert "[session]" in text
    assert "turns: 1" in text
    assert "turns: 3" in text
    # scope key not echoed as a line (it's the header)
    assert "\nscope:" not in text
