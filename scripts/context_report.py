#!/usr/bin/env python3
"""Analyze a yoker session JSONL: compaction flags, runs, size hot spots.

Stdlib-only on purpose: the script must analyze session files produced by
ANY yoker version, including ones older than the current package — importing
yoker would couple the analysis to the running checkout.

Usage:
  python scripts/context_report.py <session.jsonl> [--json]

Text mode prints a human report; --json prints the same data machine-readable
(a JSON object with one key per report section). Exit 0 always — this is an
analysis tool, not a validator; malformed lines are reported and skipped.
Missing file → argparse error (exit 2).

Token estimates are rough (chars // 4): real tokenizers vary per model and
per content type (code denser than prose). Counts, not estimates, are exact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Approximation factor for the rough token estimate (4 chars ≈ 1 token).
CHARS_PER_TOKEN = 4
PREVIEW_WIDTH = 60


def _preview(content: Any, width: int = PREVIEW_WIDTH) -> str:
  """Single-line content preview with newlines/escapes made visible."""
  text = content if isinstance(content, str) else "" if content is None else str(content)
  text = text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
  return text[:width]


def _flag_summary(flag: Any) -> str:
  """Render a pruned flag as kind/stage/run (or '-' when absent/malformed)."""
  if not isinstance(flag, dict):
    return "-"
  kind = flag.get("kind", "?")
  stage = flag.get("stage", "?")
  run = flag.get("run")
  return f"{kind}/{stage}/{run}" if run else f"{kind}/{stage}/-"


def _record_identity(record: dict[str, Any]) -> tuple[str, str]:
  """Record type plus a display role for the message table."""
  record_type = record.get("type", "?")
  data = record.get("data") or {}
  if record_type == "tool_call_message":
    return record_type, "assistant(frame)"
  if record_type == "tool_result":
    return record_type, "tool"
  if record_type == "message":
    return record_type, str(data.get("role", "?"))
  return record_type, "-"


def _scaffold_end(messages: list[dict[str, Any]]) -> int:
  """Number of leading records in the protected scaffold zone.

  SIMPLE heuristic (the full protection window logic lives in
  yoker.context.manager and is intentionally NOT replicated): the
  leading run of system messages plus the contiguous leading user run.
  """
  count = 0
  for record in messages:
    record_type, role = _record_identity(record)
    if record_type == "message" and role == "system":
      count += 1
    elif record_type == "message" and role == "user":
      count += 1
    else:
      break
  return count


def _parse_file(path: Path) -> tuple[list[tuple[int, dict[str, Any] | None, str | None]], dict[str, Any]]:
  """Read the JSONL; return (records, header-info).

  Each entry is (line_number, parsed-record-or-None, error-or-None).
  Malformed lines are kept as errors so the report can point at them and
  continue (exit 0 always).
  """
  entries: list[tuple[int, dict[str, Any] | None, str | None]] = []
  meta: dict[str, Any] = {"session_id": None, "agent_id": None, "start_time": None}
  with open(path, encoding="utf-8") as f:
    for line_num, line in enumerate(f, start=1):
      line = line.strip()
      if not line:
        continue
      try:
        entries.append((line_num, json.loads(line), None))
      except json.JSONDecodeError as e:
        entries.append((line_num, None, f"invalid JSON: {e.msg}"))
      if not meta.get("session_id"):
        try:
          first = json.loads(line)
        except (json.JSONDecodeError, ValueError):
          first = None
        if isinstance(first, dict) and first.get("type") == "session_start":
          data = first.get("data") or {}
          meta["session_id"] = data.get("session_id")
          meta["agent_id"] = data.get("agent_id")
          meta["start_time"] = first.get("timestamp") or data.get("start_time")
  return entries, meta


def build_report(path: Path) -> dict[str, Any]:
  """Compute the full report model (shared by text and JSON output)."""
  entries, meta = _parse_file(path)
  good = [record for _, record, error in entries if record is not None and error is None]

  message_entries: list[tuple[int, dict[str, Any]]] = []
  compaction_runs: list[dict[str, Any]] = []
  malformed: list[tuple[int, str]] = []
  record_type_counts: dict[str, int] = {}
  total_chars = 0

  for line_num, record, error in entries:
    if record is None or error is not None:
      malformed.append((line_num, error or "unparseable"))
      continue
    record_type = record.get("type", "?")
    record_type_counts[record_type] = record_type_counts.get(record_type, 0) + 1
    if record_type == "compaction":
      data = record.get("data") or {}
      if isinstance(data, dict) and "run_id" in data:
        compaction_runs.append(data)
    elif record_type in ("message", "tool_call_message", "tool_result"):
      message_entries.append((line_num, record))
      data = record.get("data") or {}
      content = data.get("content", data.get("result", ""))
      total_chars += len(content) if isinstance(content, str) else 0

  scaffold_count = _scaffold_end([record for _, record in message_entries])

  # Message table rows.
  rows: list[dict[str, Any]] = []
  flag_counts: dict[str, int] = {}
  run_ids: set[str] = set()
  for index, (line_num, record) in enumerate(message_entries):
    data = record.get("data") or {}
    record_type, role = _record_identity(record)
    flag = data.get("pruned")
    if isinstance(flag, dict):
      kind = str(flag.get("kind", "?"))
      stage = str(flag.get("stage", "?"))
      run = flag.get("run")
      flag_counts[f"{kind}/{stage}"] = flag_counts.get(f"{kind}/{stage}", 0) + 1
      if isinstance(run, str):
        run_ids.add(run)
    content = data.get("content", data.get("result", ""))
    rows.append(
      {
        "index": index,
        "line": line_num,
        "type": record_type,
        "role": role,
        "scaffold": index < scaffold_count,
        "flag": _flag_summary(flag),
        "chars": len(content) if isinstance(content, str) else 0,
        "preview": _preview(content),
      }
    )

  turn_rows: list[dict[str, Any]] = []
  for index, (line_num, record) in enumerate(message_entries):
    record_type, role = _record_identity(record)
    if record_type == "message" and role == "user" and index >= scaffold_count:
      data = record.get("data") or {}
      turn_rows.append(
        {
          "index": index,
          "preview": _preview(data.get("content", "")),
          "flagged": isinstance(data.get("pruned"), dict),
        }
      )

  largest = sorted(rows, key=lambda row: row["chars"], reverse=True)[:10]

  return {
    "file": str(path),
    "session_id": meta.get("session_id"),
    "agent_id": meta.get("agent_id"),
    "start_time": meta.get("start_time"),
    "record_count": len(entries),
    "malformed_count": len(malformed),
    "malformed": [{"line": line, "error": error} for line, error in malformed],
    "record_types": record_type_counts,
    "message_count": len(rows),
    "total_chars": total_chars,
    "estimated_tokens": total_chars // CHARS_PER_TOKEN,
    "estimate_note": f"rough chars//{CHARS_PER_TOKEN} estimate — real tokenizers vary per model/content",
    "messages": rows,
    "flag_counts": dict(sorted(flag_counts.items())),
    "flag_run_ids": sorted(run_ids),
    "compaction_runs": compaction_runs,
    "turns": turn_rows,
    "largest": largest,
    "scaffold_count": scaffold_count,
  }


def render_text(report: dict[str, Any]) -> str:
  """Render the report model as the human-readable text output."""
  lines: list[str] = []
  add = lines.append

  add("=== Session Context Report ===")
  add(f"file:        {report['file']}")
  add(f"session_id:  {report['session_id']}")
  add(f"agent_id:    {report['agent_id']}")
  add(f"start_time:  {report['start_time']}")
  add(f"records:     {report['record_count']} ({report['message_count']} messages)")
  for record_type, count in report["record_types"].items():
    add(f"  {record_type}: {count}")
  if report["malformed_count"]:
    for item in report["malformed"]:
      add(f"  MALFORMED line {item['line']}: {item['error']} (skipped)")
  add(f"total chars: {report['total_chars']}")
  add(f"est. tokens: ~{report['estimated_tokens']} (rough chars//4 — real tokenizers vary per model/content)")
  add("")

  add(f"--- Messages ({report['message_count']}) ---")
  add("idx  type               role               flag                          chars  content")
  for row in report["messages"]:
    marker = "SCAFFOLD" if row["scaffold"] else "        "
    add(
      f"{row['index']:>3}  {row['type']:<18} {row['role']:<18} {row['flag']:<28} "
      f"{row['chars']:>6}  [{marker}] {row['preview']}"
    )
    if row["chars"] > PREVIEW_WIDTH:
      add(f"    ({row['index']}: content truncated for display, {row['chars']} chars total)")
    elif len(row["preview"]) == PREVIEW_WIDTH:
      add(f"    ({row['index']}: preview truncated at {PREVIEW_WIDTH} chars)")
  add("")

  add("--- Pruned-flag cross-tab ---")
  if report["flag_counts"]:
    for key, count in report["flag_counts"].items():
      add(f"  {key}: {count}")
    run_ids = ", ".join(report["flag_run_ids"]) or "(none)"
    add(f"  distinct run ids: {run_ids}")
  else:
    add("  (no pruned flags)")
  add("")

  add(f"--- Compaction runs ({len(report['compaction_runs'])}) ---")
  if report["compaction_runs"]:
    for run in report["compaction_runs"]:
      stages = ", ".join(
        f"{s.get('name', '?')}(-{s.get('messages', 0)} msg,-{s.get('tokens', 0)} tok)"
        for s in run.get("stages", [])
      )
      add(
        f"  {run.get('run_id', '?')}: {run.get('trigger_estimate', '?')} → "
        f"{run.get('remaining_estimate', '?')} | max={run.get('max_tokens', '?')} "
        f"target={run.get('target', '?')} clamped={run.get('target_clamped', '?')} "
        f"floor={run.get('floor_tokens', '?')} | stages: {stages} | "
        f"dropped={run.get('dropped_count', '?')} sent={run.get('sent_count', '?')} | "
        f"first_remaining: {_preview(run.get('first_remaining', ''))}"
      )
  else:
    add("  (no compaction records)")
  add("")

  add(f"--- Turn boundaries (non-scaffold user messages, {len(report['turns'])}) ---")
  for row in report["turns"]:
    state = "FLAGGED" if row["flagged"] else "clean"
    add(f"  #{row['index']:>3} [{state}] {row['preview']}")
  add("")

  add("--- Largest messages (top 10 by chars) ---")
  for row in report["largest"]:
    add(f"  #{row['index']:>3} {row['role']:<18} {row['chars']:>7} chars  flag={row['flag']}")
  add("")
  add(
    "note: scaffold marking is a heuristic (leading system + contiguous leading user run);"
  )
  add("note: full cutoff protection windows are NOT replicated here (see yoker.context.manager).")
  return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
    description="Analyze a yoker session JSONL: compaction flags, runs, size hot spots.",
  )
  parser.add_argument("jsonl", type=Path, help="Path to the session .jsonl file")
  parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
  args = parser.parse_args(argv)

  if not args.jsonl.is_file():
    parser.error(f"file not found: {args.jsonl}")  # exits 2

  report = build_report(args.jsonl)
  if args.json:
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
  else:
    print(render_text(report))
  return 0


if __name__ == "__main__":
  sys.exit(main())