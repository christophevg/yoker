#!/usr/bin/env python3
"""Analyze yoker session JSONL files: tool errors, bad-edit flows, recovery.

Fact-based analysis of tool usage across session files: how often each
error class occurs, when edits follow failures without re-reads (the
corruption surface), and what recovery behavior looks like. Built to
replace anecdote (incident reports) with data.

Stdlib-only on purpose: must parse session files produced by ANY yoker
version, including older ones — importing yoker would couple the analysis
to the running checkout (same rationale as context_report.py).

Record shapes (see src/yoker/context/persisted.py):
  message            {role, content, [pruned]}
  tool_call_message  {tool_calls: [{id, name, arguments}], content, [thinking], [pruned]}
  tool_result        {tool_name, tool_id, result, success, [pruned]}
  compaction         {run_id, stages, dropped_count, ...}
  session_start / turn_start / turn_end / session_end

Method (locked decisions 2026-09-29):
  Layer 1  failed tool results classified by error taxonomy (works without
           call/result pairing — classification is on the result text).
  Layer 2  per-path state machine, session-wide (cross-agent): file truth
           is session-wide, so the last state on a path is global.
           Each write is classified by the state BEFORE it:
             fail after write_ok   → c2-benefit   (strict read-after-write
                                     guard would have prevented a failed edit)
             ok   after write_ok   → c2-harmless  (same guard = pure overhead)
             fail after write_fail → blind-retry (Issue 3: same-path writes
                                     pre-constructed on the belief the first
                                     edit worked)
             ok   after write_fail → blind-recovery (Issue 1/2: editing on a
                                     stale mental model)
             *    after stub_read  → stub-edit   (Issue 1: edit after a
                                     force-stubbed read)
             fail after read_ok    → failed-even-after-reread (tool UX)
             ok   after read_ok    → guard-satisfied baseline (no counter)
             *    first touch      → first-touch (neutral)
  Layer 3  same mechanism from the recovery viewpoint + fail-streak depths
           per path (consecutive failures without a re-read between).

Pairing is by tool_id; unpaired results (legacy files) classify on Layer 1
only and are counted separately. Files are included whole when their mtime
is ≥ the cutoff ("process all files max N days old" — file-level criterion;
sessions are append-only, so old lines belong to recently active sessions).
Exit 0 always — analysis tool, not validator; malformed lines are counted,
shown, and skipped.

Usage:
  python scripts/tool_error_analyzer.py                       # defaults: 15d, ./local/context/*.jsonl
  python scripts/tool_error_analyzer.py 30                    # last 30 days
  python scripts/tool_error_analyzer.py 30 ../basset/local/context/*.jsonl
  python scripts/tool_error_analyzer.py --json                # machine-readable

Read the census section before trusting the analysis sections — it is the
review gate: unexpected record shapes mean the parsing rules need a look.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ============================================================================
# Configuration / constants
# ============================================================================

DEFAULT_CONTEXT_FILES = "./local/context/*.jsonl"
DEFAULT_SINCE_DAYS = 15
_MAX_EXAMPLES = 3          # condensed report: ≤3 examples per category
_RESULT_PREVIEW = 120      # example excerpt width
_STREAK_TOP = 5            # fail-streak table rows
_PATH_TOP = 5              # top failing paths per tool

# Category → regexes (case-insensitive) matched against the tool_result
# text. Patterns mirror the real error strings the tools emit
# (src/yoker/builtin/update.py et al.). Unmatched errors → "other", kept
# visible so patterns can be tightened next iteration.
ERROR_TAXONOMY: dict[str, tuple[str, ...]] = {
  "search-not-found": (
    r"search text not found",
  ),
  "ambiguous-match": (
    r"appears multiple times",
    r"ambiguous anchor",
  ),
  "no-op-edit": (
    r"no-op: old_string equals new_string",
    r"applied, but file content is identical",
  ),
  "anchor-duplication": (
    r"doesn't need to be repeated",
  ),
  "invalid-arguments": (
    r"invalid arguments",
    r"unknown argument",
  ),
  "path/validation": (
    r"invalid path",
    r"path is not a file",
    r"file not found",
    r"permission denied",
    r"invalid operation",
    r"invalid .* parameter",
    r"invalid line_number",
    r"diff size exceeds limit",
    r"symlink",
    r"must be a \[start, end\] pair",
    r"out of range",
    r"line numbers are 1-indexed",
    r"line_range end .* must be >= start",
    r"line_range values must be integers",
    r"line_range start .* must be >= 1",
    r"parameter 'operation' is required",
    r"error reading file",
    r"error updating file",
  ),
  "guardrail-protected": (
    r"write-protected",
    r"blocked.*write",
    r"denied by .*guardrail",
  ),
  "out-of-scope": (
    r"unknown tool",
    r"tool .* not found",
    r"no such (tool|command)",
  ),
  "other": (),  # unmatched failures land here — classified below explicitly
}

STUB_MARKER_SUBSTR = "pruned by force_stub_tool_results"

# Tools whose success falsifies file state (chain/recovery analysis domain).
WRITE_TOOLS = {"update", "write"}
READ_TOOLS = {"read"}

# ============================================================================
# Per-file parsing
# ============================================================================


def _parse_file(path: Path) -> tuple[list[tuple[int, dict[str, Any] | None, str | None]], dict[str, Any]]:
  """Read a JSONL file into (line_number, record | None, error | None) entries.

  Malformed lines are kept as errors so the report can point at them and
  continue (exit 0 always). Meta (session_id/agent_id/start_time) is read
  from the session_start record; legacy combined ids are split on the first
  dash (all current session ids are dash-free UUIDs).
  """
  entries: list[tuple[int, dict[str, Any] | None, str | None]] = []
  meta: dict[str, Any] = {"session_id": None, "agent_id": None, "start_time": None}
  with open(path, encoding="utf-8") as f:
    for line_num, line in enumerate(f, start=1):
      line = line.strip()
      if not line:
        continue
      try:
        record = json.loads(line)
      except json.JSONDecodeError as e:
        entries.append((line_num, None, f"invalid JSON: {e.msg}"))
        continue
      entries.append((line_num, record, None))
      if record.get("type") == "session_start" and not meta["session_id"]:
        data = record.get("data") or {}
        meta["session_id"] = data.get("session_id")
        meta["agent_id"] = data.get("agent_id")
        meta["start_time"] = data.get("start_time") or record.get("timestamp")
  return entries, meta


def _parse_arguments(raw: Any) -> dict | None:
  """tool_calls[].arguments: dict or JSON string; malformed → None."""
  if isinstance(raw, dict):
    return raw
  if isinstance(raw, str):
    try:
      parsed = json.loads(raw)
      return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
      return None
  return None


def _classify_error(text: Any) -> str:
  """Classify a failed tool-result text by the taxonomy; fallback "other"."""
  s = text if isinstance(text, str) else ("" if text is None else str(text))
  s = s.lower()
  for category, patterns in ERROR_TAXONOMY.items():
    for pattern in patterns:
      if re.search(pattern, s):
        return category
  return "other"


# ============================================================================
# Phase 0: schema census (the review gate)
# ============================================================================


def _census(files: list[Path]) -> dict[str, Any]:
  """Record-type / field census across the corpus.

  Purpose: validate the parse assumptions BEFORE the analysis is trusted —
  record-type coverage, data keys per type, call↔result pairing coverage,
  call argument shapes per tool, update operation values, stub markers,
  compaction stage names.
  """
  types: Counter = Counter()
  keys_by_type: dict[str, Counter] = {}
  result_fields: Counter = Counter()
  pairing: Counter = Counter()
  arg_keys: dict[str, Counter] = {}
  update_ops: Counter = Counter()
  agent_attributed_results: Counter = Counter()
  files_with_stubs: set[str] = set()
  files_with_computed: set[str] = set()
  files_with_tool_records: set[str] = set()
  stage_counts: Counter = Counter()

  for path in files:
    entries, meta = _parse_file(path)
    sid = str(meta.get("session_id") or path.name)
    for _, record, error in entries:
      if record is None or error is not None:
        continue
      rtype = record.get("type")
      if not isinstance(rtype, str):
        continue
      types[rtype] += 1
      data = record.get("data") or {}
      if isinstance(data, dict):
        keys_by_type.setdefault(rtype, Counter()).update(data.keys())

      if rtype == "tool_result":
        files_with_tool_records.add(sid)
        result_fields.update(data.keys())
        pairing["with tool_id"] += 1 if isinstance(data.get("tool_id"), str) else 0
        if not data.get("tool_id"):
          pairing["without tool_id"] += 1
        # Stub detection (Issue 1 raw material): stub marker text OR a
        # pruned flag naming the force_stub stage.
        result_text = data.get("result")
        pruned = data.get("pruned")
        is_stub = (
          isinstance(result_text, str) and STUB_MARKER_SUBSTR in result_text
        ) or (
          isinstance(pruned, dict) and "force_stub" in json.dumps(pruned)
        )
        if is_stub:
          files_with_stubs.add(sid)
      elif rtype == "tool_call_message":
        files_with_tool_records.add(sid)
        calls = data.get("tool_calls")
        if isinstance(calls, list):
          files_with_computed.add(sid)
          files_with_stub_records_placeholder = None  # placeholder removed
          for call in calls:
            if not isinstance(call, dict):
              continue
            name = call.get("name")
            args = _parse_arguments(call.get("arguments"))
            if isinstance(name, str):
              arg_keys.setdefault(name, Counter()).update((args or {}).keys())
            if name == "update" and isinstance(args, dict):
              op = args.get("operation")
              update_ops[op if isinstance(op, str) and op else "(inferred)"] += 1
      elif rtype == "compaction":
        for stage in data.get("stages", []) if isinstance(data.get("stages"), list) else []:
          if isinstance(stage, dict):
            stage_counts[str(stage.get("name", "?"))] += 1

  total_results = sum(types.get(t, 0) for t in ("tool_result",))
  return {
    "files": len(files),
    "files_with_tool_records": len(files_with_tool_records),
    "record_types": dict(sorted(types.items())),
    "keys_by_type": {k: dict(v) for k, v in sorted(keys_by_type.items())},
    "result_fields": dict(sorted(result_fields.items())),
    "pairing": dict(pairing),
    "pairing_coverage": (
      f"{pairing['with tool_id']}/{total_results} results carry tool_id"
      if total_results else "no tool_result records in corpus"
    ),
    "arg_keys_per_tool": {k: dict(v) for k, v in sorted(arg_keys.items())},
    "update_operation_values": dict(sorted(update_ops.items(), key=lambda kv: -kv[1])),
    "agent_attributed_results": dict(agent_attributed_results),
    "files_with_stubbed_reads": len(files_with_stubs),
    "compaction_stage_counts": dict(sorted(stage_counts.items())),
    "review_gate": (
      "REVIEW this census before trusting the analysis sections — "
      "unexpected record shapes mean the parsing rules need a look."
    ),
  }


# ============================================================================
# Per-file analysis (Layers 1–3)
# ============================================================================


def _analyze_file(path: Path) -> dict[str, Any]:
  """All three layers for one file, driven by one interleaved event pass.

  Calls are registered by tool_id when their frame is seen; results are
  paired via that registry and drive a session-wide per-path state machine.
  Each write result is classified by the state before it (one mechanism
  covering C2 pricing, recovery, Issue-1 stub edits, and tool-UX signals).
  """
  entries, meta = _parse_file(path)

  failures: list[dict[str, Any]] = []       # Layer 1: {line, tool, category, excerpt}
  transition_counts: Counter = Counter()    # {(prev, outcome): n}
  stub_reads: Counter = Counter()           # per path: stubbed-read events
  stub_edits: list[dict[str, Any]] = []
  fail_streaks: list[dict[str, Any]] = []   # closed streaks: {path, depth, first_category}
  unpaired_results: list[dict[str, Any]] = []
  write_char_reads: list[int] = []          # read-result sizes (C2 overhead proxy)
  read_count = 0
  write_count = 0
  malformed: list[tuple[int, str]] = []

  calls_by_id: dict[str, dict[str, Any]] = {}
  state: dict[str, str] = {}                # normalized path → last state
  streak: dict[str, int] = {}               # normalized path → current fail streak
  streak_first_cat: dict[str, str] = {}

  def norm(raw_path: str) -> str:
    return os.path.normpath(raw_path)

  for line_num, record, error in entries:
    if record is None or error is not None:
      malformed.append((line_num, error or "unparseable"))
      continue
    rtype = record.get("type")
    data = record.get("data")

    if rtype == "tool_call_message" and isinstance(data, dict):
      calls = data.get("tool_calls")
      if isinstance(calls, list):
        for call in calls:
          if not isinstance(call, dict):
            continue
          tool_id = call.get("id")
          args = _parse_arguments(call.get("arguments"))
          if isinstance(tool_id, str):
            calls_by_id[tool_id] = {
              "name": call.get("name"),
              "path": _path_from_call_args(args),
              "operation": args.get("operation") if isinstance(args, dict) else None,
            }

    elif rtype == "tool_result" and isinstance(data, dict):
      tool_id = data.get("tool_id")
      tool_name = data.get("tool_name")
      call = calls_by_id.get(tool_id) if isinstance(tool_id, str) else None
      call_path = call["path"] if call else None

      # -- Layer 1: classification (works without pairing) ------------------
      if data.get("success") is False:
        catalog = _classify_error(data.get("result"))
        failures.append({
          "line": line_num,
          "tool": tool_name,
          "category": catalog,
          "excerpt": (data.get("result") or "")[:_RESULT_PREVIEW],
        })
        if call_path:
          key = norm(call_path)
          if streak.get(key):
            streak[key] += 1
          else:
            streak[key] = 1
          streak_first_cat.setdefault(key, catalog)

      # -- Stub reads (Issue 1 raw material) --------------------------------
      pruned = data.get("pruned")
      is_stub = (
        isinstance(data.get("result"), str) and STUB_MARKER_SUBSTR in data["result"]
      ) or (
        isinstance(pruned, dict) and "force_stub" in json.dumps(pruned)
      )

      if call_path and tool_name in READ_TOOLS:
        read_count += 1
        if is_stub:
          stub_reads[norm(call_path)] += 1
          state[norm(call_path)] = "stub_read"   # stub ≠ valid truth
        else:
          write_char_reads.append(len(data.get("result") or ""))
          state[norm(call_path)] = "read_ok"
        continue

      # -- Writes (update/write): classify by prev state -------------------
      if call_path and tool_name in WRITE_TOOLS:
        key = norm(call_path)
        prev = state.get(key)
        success = data.get("success") is not False
        outcome = "ok" if success else "fail"
        transition_counts[(prev, outcome)] += 1
        write_count += 1
        if prev == "stub_read":
          stub_edits.append({"path": call_path, "line": line_num, "tool": tool_name})
        if success:
          streak.pop(key, None)
          streak_first_cat.pop(key, None)
        # state = own outcome (failures leave the machine in write_fail)
        state[key] = "write_ok" if success else "write_fail"
        continue

    elif rtype == "compaction" and isinstance(data, dict):
      # Last-timestamp tracking not needed — mtime gates file inclusion.
      del data  # compaction records parsed in census only

  # Close open streaks (EOF with path still failing).
  for key, depth in streak.items():
    if depth > 0:
      fail_streaks.append({
        "depth": depth,
        "first_category": streak_first_cat.get(key, "?"),
        "path": key,
      })

  return {
    "file": str(path),
    "session_id": meta.get("session_id"),
    "agent_id": meta.get("agent_id"),
    "start_time": meta.get("start_time"),
    "failures": failures,
    "unpaired_results": unpaired_results,
    "transitions": transition_counts,
    "stub_reads": stub_reads,
    "stub_edits": stub_edits,
    "fail_streaks": fail_streaks,
    "read_sizes": write_char_reads,
    "read_count": read_count,
    "write_count": write_count,
    "malformed": malformed,
    "tools": Counter(),
  }


# ============================================================================
# Aggregation across files
# ============================================================================


def build_report(files: list[Path], since: datetime, skipped: list[tuple[str, str]]) -> dict[str, Any]:
  """Aggregate per-file models into the corpus report model."""
  failures: list[dict[str, Any]] = []
  failures_by_tool_cat: Counter = Counter()
  failures_by_tool: Counter = Counter()
  tool_calls: Counter = Counter()
  transitions: Counter = Counter()
  stub_edits: list[dict[str, Any]] = []
  stub_read_events = 0
  malformed: list[tuple[str, int, str]] = []
  read_sizes: list[int] = []
  write_events_total = 0
  file_summaries: list[dict[str, Any]] = []
  unpaired_total = 0

  for path in files:
    f = _analyze_file(path)
    tool_results = sum(n for _, n in f["tools"].items())
    file_summaries.append({
      "file": f["file"],
      "session_id": f["session_id"],
      "agent_id": f["agent_id"],
      "start_time": f["start_time"],
      "tool_events": tool_results,
      "writes": f["write_count"],
      "reads": f["read_count"],
      "failures": len(f["failures"]),
    })
    for failure in f["failures"]:
        failure = dict(failure)
        failure["file"] = f["file"]
        failure["session_id"] = f["session_id"]
        failures.append(failure)
        failures_by_tool_cat[(failure["tool"], failure["category"])] += 1
        failures_by_tool[failure["tool"]] += 1
    for tool_result in f["tools"]:
      pass
    transitions.update(f["transitions"])
    stub_edits.extend(f["stub_edits"])
    stub_read_events += sum(f["stub_reads"].values())
    unpaired_total += len(f["unpaired_results"])
    read_sizes.extend(f["read_sizes"])
    write_events_total += f["write_count"]
    for line_num, error_text in f["malformed"]:
      malformed.append((f["file"], line_num, error_text))

  # C2 pricing: overhead estimate from read-result sizes (chars//4 ≈ tokens,
  # same rough convention as context_report.py).
  avg_read_tokens = (sum(read_sizes) // 4 // len(read_sizes)) if read_sizes else 0

  c2 = {
    "chain_links": transitions.get(("write_ok", "ok"), 0)
                  + transitions.get(("write_ok", "fail"), 0),
    "links_resolved_harmless": transitions.get(("write_ok", "ok"), 0),
    "links_resolved_benefit": transitions.get(("write_ok", "fail"), 0),
    "overhead_estimate_tokens": transitions.get(("write_ok", "ok"), 0) * avg_read_tokens,
    "overhead_note": "harmless links × avg read size in chars//4 ≈ tokens — rough",
  }

  streak_buckets = Counter(
    "3+" if s["depth"] >= 3 else str(s["depth"]) for s in []
  )

  return {
    "corpus": {
      "files": len(files),
      "since": since.isoformat(),
      "skipped": skipped,
      "malformed_lines": len(malformed),
      "malformed_detail": [
        {"file": f, "line": ln, "error": e} for f, ln, e in malformed[:20]
      ],
      "tool_result_records": sum(tool_calls.values()),
      "unpaired_results": unpaired_total,
      "busiest": sorted(
        (s for s in file_summaries if s["tool_events"] > 0),
        key=lambda s: -s["tool_events"],
      )[:5],
    },
    "census": _census(files) if files else {"files": 0},
    "layer1": {
      "total_failures": len(failures),
      "by_tool_and_category": {f"{t} :: {c}": n for (t, c), n in failures_by_tool_cat.most_common()},
      "by_tool": {
        t: {"calls": n, "failures": failures_by_tool.get(t, 0)}
        for t, n in tool_calls.most_common()
      },
      "examples": _examples(failures),
    },
    "layer2": {
      "c2": c2,
      "transitions": {f"{p}->{o}": n for (p, o), n in transitions.most_common()},
    },
    "layer3": {
      "fail_streaks": sorted(
        streak_buckets.items(), key=lambda kv: -kv[1]
      ),
      "streak_detail": sorted(
        (s for s in local_streaks),
        key=lambda s: -s["depth"],
      )[:_STREAK_TOP],
      "stub_reads": stub_read_events,
      "stub_edits": stub_edits[:_STREAK_TOP],
      "stub_edit_count": len(stub_edits),
    },
  }


def _examples(failures: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
  """Group failures by category; ≤3 examples each, condensed fields."""
  grouped: dict[str, list[dict[str, Any]]] = {}
  for failure in failures:
    grouped.setdefault(failure["category"], []).append({
      "tool": failure["tool"],
      "path_or_line": failure.get("path") or failure.get("line"),
      "file": failure["file"],
      "excerpt": failure["excerpt"],
    })
  return {cat: items[:_MAX_EXAMPLES] for cat, items in grouped.items()}


# ============================================================================
# Rendering
# ============================================================================


def _render_census_lines(census: dict[str, Any], lines: list[str]) -> None:
  add = lines.append
  add(f"--- Phase 0 census ({census['files']} files) ---")
  add(f"  files with tool records: {census.get('files_with_tool_records', 0)}")
  add("  record types:")
  for rtype, count in census.get("record_types", {}).items():
    add(f"    {rtype:<22} {count}")
  add(f"  result pairing: {census.get('pairing_coverage', 'n/a')}")
  add("  update operation values:")
  for op, count in census.get("update_operation_values", {}).items():
    add(f"    {op:<14} {count}")
  add(f"  files with stubbed reads: {census.get('files_with_stubbed_reads', 0)}")
  stages = census.get("compaction_stage_counts", {})
  if stages:
    add("  compaction stages:")
    for stage, count in stages.items():
      add(f"    {stage:<34} {count}")
  add(f"  >> {census.get('review_gate', '')}")


def render_text(report: dict[str, Any]) -> str:
  """Render the report model as the human-readable condensed report."""
  lines: list[str] = []
  add = lines.append
  corpus = report["corpus"]

  add("=== Yoker Tool Error Analyzer ===")
  add(f"files:      {corpus['files']} (since {corpus['since']})")
  add(f"tool records: {corpus['tool_result_records']}  "
      f"unpaired (legacy): {corpus['unpaired_results']}  "
      f"malformed lines skipped: {corpus['malformed_lines']}")
  if corpus["skipped"]:
    for skipped_file, reason in corpus["skipped"]:
      add(f"  SKIPPED {skipped_file}: {reason}")
  if corpus["busiest"]:
    add("  busiest sessions:")
    for s in corpus["busiest"]:
      add(f"    {s['tool_events']:>5} events  {s['session_id']}  {s['file']}")
  add("")

  _render_census_lines(report["census"], lines)
  add("")

  l1 = report["layer1"]
  add(f"--- Layer 1: tool failures ({l1['total_failures']}) ---")
  add("  by tool :: category:")
  for key, count in l1["by_tool_and_category"].items():
    add(f"    {count:>5}  {key}")
  add("")
  add("  examples (≤3 per category):")
  for category, items in l1["examples"].items():
    add(f"    [{category}]")
    for item in items:
      add(f"      {item['file']} · {item['tool']} · {item['path_or_line']}")
      add(f"        {item['excerpt']}")
  add("")

  l2 = report["layer2"]
  c2 = l2["c2"]
  add("--- Layer 2: strict read-after-write (C2) simulation on edit chains ---")
  add(f"  chain links (edit after edit, no read between): {c2['chain_links']}")
  add(f"    harm (failed edit after clean edit):         {c2['links_resolved_benefit']}")
  add(f"    overhead (clean edit after clean edit):      {c2['links_resolved_harmless']}")
  add(f"    est. strict-C2 token overhead:               ~{c2['overhead_estimate_tokens']}")
  add(f"      ({c2['overhead_note']})")
  add(f"  all transitions: {l2['transitions']}")
  add("")

  l3 = report["layer3"]
  add("--- Layer 3: recovery & corruption-flow signals ---")
  add(f"  fail-streak depth distribution: {dict(l3['fail_streaks']) or '(none)'}")
  for s in l3["streak_detail"]:
    add(f"    depth {s['depth']}  [{s['first_category']}] {s['path']}")
  add(f"  stubbed reads: {l3['stub_reads']}   edits after stubbed reads: {l3['stub_edit_count']}")
  for s in l3["stub_edits"]:
    add(f"    {s['path']} ({s['tool']})")
  add("")

  add("limitations: exception-level vs graceful failures both surface as "
      "success=false (not distinguishable in this corpus); cross-session "
      "path identity is best-effort (cwd may change mid-session); argument"
      "-level malformed calls may not be recorded (census checks).")
  return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================


def _expand_files(patterns: list[str], since: datetime) -> tuple[list[Path], list[tuple[str, str]]]:
  """Expand glob patterns; include files with mtime ≥ since; skip vanished.

  Each pattern is a glob (default: ./local/context/*.jsonl). Files failing
  stat (vanished between glob and stat) are skipped and reported.
  """
  found: set[Path] = set()
  for pattern in patterns:
    for match in glob.glob(os.path.expanduser(pattern)):
      found.add(Path(match))
  files: list[Path] = []
  skipped: list[tuple[str, str]] = []
  for path in sorted(found):
    try:
      if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) >= since:
        files.append(path)
    except OSError as e:
      skipped.append((str(path), f"stat failed: {e}"))
  return files, skipped


def main(argv: list[str] | None = None) -> int:
  """Parse [since_days] [glob-patterns...] [--json]; render report; exit 0."""
  parser = argparse.ArgumentParser(
    description="Analyze yoker session JSONL files for tool-error patterns.",
  )
  parser.add_argument("positionals", nargs="*", help=(
    "first digit-lead positional = days window (default 15); "
    "remaining positionals = glob patterns (default ./local/context/*.jsonl)",
  ))
  parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
  args = parser.parse_args(argv)

  since_days = DEFAULT_SINCE_DAYS
  patterns: list[str] = []
  for i, pos in enumerate(args.positionals):
    if i == 0 and pos.isdigit():
      since_days = int(pos)
    else:
      patterns.append(pos)

  since = datetime.now(timezone.utc) - timedelta(days=since_days)
  files, skipped = _expand_files(patterns or [DEFAULT_CONTEXT_FILES], since)

  report = build_report(files, since, skipped)
  if args.json:
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
  else:
    print(render_text(report))
  return 0


if __name__ == "__main__":
  sys.exit(main())