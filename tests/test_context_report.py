"""Tests for scripts/context_report.py — session JSONL analysis tool.

The script is stdlib-only (no yoker imports) so it can analyze files from
any yoker version; these tests import it directly from its path and drive
it against a programmatically constructed session file.
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "context_report.py"
_spec = importlib.util.spec_from_file_location("context_report", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
context_report = importlib.util.module_from_spec(_spec)
sys.modules["context_report"] = context_report
_spec.loader.exec_module(context_report)


def _record(
  record_type: str, data: dict[str, Any], timestamp: str = "2026-09-15T10:00:00"
) -> dict[str, Any]:
  return {"type": record_type, "timestamp": timestamp, "data": data}


def _flag(kind: str, stage: str, run: str) -> dict[str, Any]:
  return {"kind": kind, "stage": stage, "at": "2026-09-15T10:01:00", "chars": 123, "run": run}


def _write_session(path: Path) -> None:
  """A session file exercising every report section."""
  lines: list[dict[str, Any]] = [
    _record(
      "session_start",
      {"session_id": "sess-abc-123", "agent_id": "main", "start_time": "2026-09-15T09:00:00"},
      timestamp="2026-09-15T09:00:00",
    ),
    _record("message", {"role": "system", "content": "you are helpful"}),
    _record("message", {"role": "user", "content": "scaffold prompt"}),
    _record("message", {"role": "user", "content": "turn one: analyze the flaky test"}),
    _record(
      "tool_call_message",
      {"tool_calls": [{"name": "read", "id": "t1"}], "content": "", "thinking": None},
    ),
    _record(
      "tool_result",
      {
        "tool_name": "read",
        "tool_id": "t1",
        "result": "x" * 10_000,
        "pruned": _flag("stub", "prune_tool_results", "runaaa11"),
      },
    ),
    _record("message", {"role": "assistant", "content": "done"}),
    _record(
      "message",
      {
        "role": "user",
        "content": "turn two: now fix it",
        "pruned": _flag("dropped", "cutoff", "runbbb22"),
      },
    ),
    _record(
      "compaction",
      {
        "run_id": "runaaa11",
        "timestamp": "2026-09-15T10:05:00",
        "trigger_estimate": 90_985,
        "max_tokens": 80_000,
        "target": 40_000,
        "floor_tokens": 10_000,
        "target_clamped": False,
        "stages": [
          {"name": "prune_tool_results", "messages": 0, "tokens": 12_300},
          {"name": "cutoff", "messages": 2, "tokens": 38_500},
        ],
        "dropped_count": 2,
        "remaining_estimate": 38_400,
        "sent_count": 28,
        "first_remaining": "user: turn two: now fix it",
      },
    ),
    _record(
      "compaction",
      {
        "run_id": "runbbb22",
        "timestamp": "2026-09-15T10:20:00",
        "trigger_estimate": 84_000,
        "max_tokens": 80_000,
        "target": 42_000,
        "floor_tokens": 45_000,
        "target_clamped": True,
        "stages": [{"name": "force_stub_tool_results", "messages": 1, "tokens": 40_000}],
        "dropped_count": 0,
        "remaining_estimate": 44_000,
        "sent_count": 9,
        "first_remaining": "assistant: done",
      },
    ),
    _record("session_end", {"end_time": "2026-09-15T10:30:00"}),
  ]
  with open(path, "w") as f:
    for line in lines:
      f.write(json.dumps(line) + "\n")
    # A malformed line the report must tolerate (exit 0, counted).
    f.write("{not valid json\n")


class TestBuildReport:
  """build_report: sections, counts and cross-tab on a constructed file."""

  @pytest.fixture()
  def report(self, tmp_path: Path) -> dict[str, Any]:
    session = tmp_path / "session.jsonl"
    _write_session(session)
    return context_report.build_report(session)

  def test_header_metadata(self, report: dict[str, Any]) -> None:
    assert report["session_id"] == "sess-abc-123"
    assert report["agent_id"] == "main"
    assert report["start_time"] == "2026-09-15T09:00:00"
    assert report["record_count"] == 12  # 11 well-formed + 1 malformed
    assert report["malformed_count"] == 1
    assert report["malformed"][0]["line"] == 12
    assert report["message_count"] == 7

  def test_message_rows_and_flags(self, report: dict[str, Any]) -> None:
    tool_row = report["messages"][4]
    assert tool_row["type"] == "tool_result"
    assert tool_row["role"] == "tool"
    assert tool_row["flag"] == "stub/prune_tool_results/runaaa11"
    assert tool_row["chars"] == 10_000
    assert tool_row["preview"] == "x" * 60
    frame_row = report["messages"][3]
    assert frame_row["role"] == "assistant(frame)"
    user_rows = [r for r in report["messages"] if r["role"] == "user"]
    assert user_rows[-1]["flag"] == "dropped/cutoff/runbbb22"

  def test_scaffold_marking(self, report: dict[str, Any]) -> None:
    """Leading system + contiguous leading user run = SCAFFOLD."""
    assert [r["scaffold"] for r in report["messages"]] == [
      True,
      True,
      True,
      False,
      False,
      False,
      False,
    ]
    assert report["scaffold_count"] == 3
    # Turn boundaries exclude the scaffold user message.
    assert report["turns"] == [
      {"index": 6, "preview": "turn two: now fix it", "flagged": True},
    ]

  def test_flag_cross_tab(self, report: dict[str, Any]) -> None:
    assert report["flag_counts"] == {"dropped/cutoff": 1, "stub/prune_tool_results": 1}
    assert report["flag_run_ids"] == ["runaaa11", "runbbb22"]

  def test_compaction_runs_table(self, report: dict[str, Any]) -> None:
    assert len(report["compaction_runs"]) == 2
    first, second = report["compaction_runs"]
    assert first["run_id"] == "runaaa11"
    assert first["target_clamped"] is False
    assert first["dropped_count"] == 2
    assert second["target_clamped"] is True  # floor 45,000 > target 42,000
    assert second["sent_count"] == 9

  def test_largest_messages(self, report: dict[str, Any]) -> None:
    assert report["largest"][0]["index"] == 4
    assert report["largest"][0]["chars"] == 10_000

  def test_totals(self, report: dict[str, Any]) -> None:
    # chars: system 15 + scaffold-user 15 + user 32 + frame 0 + tool 10_000 + assistant 4 + user 20
    assert report["total_chars"] == 10_086
    assert report["estimated_tokens"] == 2_521


class TestRenderText:
  """render_text: every section appears with the expected counts."""

  @pytest.fixture()
  def text(self, tmp_path: Path) -> str:
    session = tmp_path / "session.jsonl"
    _write_session(session)
    return context_report.render_text(context_report.build_report(session))

  def test_all_sections_present(self, text: str) -> None:
    assert "=== Session Context Report ===" in text
    assert "session_id:  sess-abc-123" in text
    assert "--- Messages (7) ---" in text
    assert "--- Pruned-flag cross-tab ---" in text
    assert "stub/prune_tool_results: 1" in text
    assert "dropped/cutoff: 1" in text
    assert "runaaa11, runbbb22" in text
    assert "--- Compaction runs (2) ---" in text
    assert "runaaa11: 90985 → 38400" in text
    assert "clamped=True" in text
    assert "floor=45000" in text
    assert "force_stub_tool_results(-1 msg,-40000 tok)" in text
    assert "--- Turn boundaries (non-scaffold user messages, 1) ---" in text
    assert "[FLAGGED] turn two: now fix it" in text
    assert "--- Largest messages (top 10 by chars) ---" in text
    assert "MALFORMED line 12" in text
    assert "heuristic" in text  # footer note about protection windows

  def test_exit_zero_on_malformed_file(self, tmp_path: Path) -> None:
    """Malformed lines never crash the report — exit 0, continue."""
    session = tmp_path / "broken.jsonl"
    _write_session(session)
    assert context_report.main([str(session)]) == 0


class TestJsonMode:
  """--json: parses as JSON with the same counts as the text report."""

  def test_json_output_same_counts(
    self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
  ) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(session)
    assert context_report.main([str(session), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["message_count"] == 7
    assert len(parsed["compaction_runs"]) == 2
    assert parsed["malformed_count"] == 1
    assert parsed["session_id"] == "sess-abc-123"
    assert parsed["record_types"]["session_start"] == 1
    assert parsed["estimated_tokens"] == 2_521  # 10_086 // 4


class TestMissingFile:
  """Missing file → argparse error (exit 2)."""

  def test_missing_file_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
      context_report.main([str(Path("/nonexistent/nope.jsonl"))])
    assert exc.value.code == 2
    assert "file not found" in capsys.readouterr().err
