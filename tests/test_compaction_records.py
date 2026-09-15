"""Round-trip tests for compaction run records in the session JSONL.

Chunk C: compaction run reports persist alongside messages so a resumed
session keeps its compaction history (and the context_report script can
analyze it). Stored=truth: flags and run records must survive save/load.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from yoker.context import BaseContextManager, Persisted


def _msg(role: str, content: str) -> dict[str, Any]:
  return {"role": role, "content": content}


def _tool_result(tool_id: str, content: str) -> dict[str, Any]:
  return {"role": "tool", "name": "read", "tool_id": tool_id, "content": content, "success": True}


def _run(run_id: str, **overrides: Any) -> dict[str, Any]:
  """A minimal-but-complete compaction run report (chunk B schema)."""
  run: dict[str, Any] = {
    "run_id": run_id,
    "timestamp": "2026-09-15T10:00:00",
    "trigger_estimate": 90_985,
    "max_tokens": 80_000,
    "target": 40_000,
    "floor_tokens": 10_000,
    "target_clamped": False,
    "stages": [{"name": "prune_tool_results", "messages": 0, "tokens": 12_300}],
    "dropped_count": 2,
    "remaining_estimate": 38_400,
    "sent_count": 28,
    "first_remaining": "user: next step",
  }
  run.update(overrides)
  return run


class TestCompactionRecordRoundTrip:
  """save → load preserves compaction runs (order, fields)."""

  def test_runs_survive_save_load_in_order(self, tmp_path: Path) -> None:
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-01")
    cm._wrapped._messages = [
      _msg("system", "sys"),
      _msg("user", "turn one"),
      _msg("assistant", "resp1"),
    ]
    cm.record_compaction(_run("aaa11111"))
    cm.record_compaction(_run("bbb22222", dropped_count=0, stages=[]))

    reloaded = Persisted(
      BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-01"
    )
    assert reloaded.load() is True
    runs = reloaded.compaction_runs
    assert [r["run_id"] for r in runs] == ["aaa11111", "bbb22222"]
    first = runs[0]
    assert first["trigger_estimate"] == 90_985
    assert first["max_tokens"] == 80_000
    assert first["target"] == 40_000
    assert first["target_clamped"] is False
    assert first["floor_tokens"] == 10_000
    assert first["stages"] == [{"name": "prune_tool_results", "messages": 0, "tokens": 12_300}]
    assert first["dropped_count"] == 2
    assert first["remaining_estimate"] == 38_400
    assert first["sent_count"] == 28
    assert first["first_remaining"] == "user: next step"

  def test_record_compaction_writes_record_immediately(self, tmp_path: Path) -> None:
    """record_compaction lands the run on disk at once, not at close time."""
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-02")
    cm.add_message("user", "hello")
    cm.record_compaction(_run("ccc33333"))

    with open(cm._file_path) as f:
      types = [json.loads(line)["type"] for line in f]
    assert types[-1] == "compaction"
    # Reload proves the immediate write is complete and loadable.
    reloaded = Persisted(
      BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-02"
    )
    assert reloaded.load() is True
    assert [r["run_id"] for r in reloaded.compaction_runs] == ["ccc33333"]

  def test_record_without_compaction_records_loads(self, tmp_path: Path) -> None:
    """Backward compat: an old file without compaction records loads fine."""
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-03")
    cm.add_message("user", "hello")
    cm.add_message("assistant", "hi")

    reloaded = Persisted(
      BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-03"
    )
    assert reloaded.load() is True
    assert len(reloaded.get_stored_messages()) == 2
    assert reloaded.compaction_runs == []

  def test_process_record_replay_appends_to_runs(self, tmp_path: Path) -> None:
    """_process_record replay of a compaction record appends verbatim."""
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-04")
    run = _run("ddd44444")
    record = {"type": "compaction", "timestamp": run["timestamp"], "data": run}
    cm._process_record(record, 1)
    assert cm._wrapped._compaction_runs == [run]

  def test_process_record_compaction_without_run_id_raises(self, tmp_path: Path) -> None:
    """A compaction record missing run_id is corruption, like bad messages."""
    from yoker.exceptions import ContextCorruptionError

    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-05")
    record = {"type": "compaction", "timestamp": "2026-09-15T10:00:00", "data": {"target": 1}}
    with pytest.raises(ContextCorruptionError):
      cm._process_record(record, 3)

  def test_flags_with_run_id_survive_save_load(self, tmp_path: Path) -> None:
    """Pruned flags carrying the run id round-trip on every record kind."""
    from yoker.context.manager import _pruned_metadata

    flag_stub = _pruned_metadata("stub", "prune_tool_results", chars=42, run="eee55555")
    flag_dropped = _pruned_metadata("dropped", "cutoff", run="fff66666")
    cm = Persisted(BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-06")
    cm._wrapped._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      {**_tool_result("t1", "x" * 100), "pruned": flag_stub},
      {**_msg("assistant", "mid"), "pruned": flag_dropped},
      _msg("assistant", "done"),
    ]
    cm.record_compaction(_run("eee55555"))

    reloaded = Persisted(
      BaseContextManager(), storage_path=tmp_path, session_id="test-compaction-06"
    )
    assert reloaded.load() is True
    stored = reloaded.get_stored_messages()
    assert stored[2]["pruned"] == flag_stub
    assert stored[2]["pruned"]["run"] == "eee55555"
    assert stored[3]["pruned"] == flag_dropped
    # The flagged tool body is hidden from the view (stub projection).
    view_contents = [m.get("content") for m in reloaded.get_context()]
    assert all("x" * 100 not in c for c in view_contents if isinstance(c, str))
