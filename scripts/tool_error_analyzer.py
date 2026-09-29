"""tool_error_analyzer.py — mine yoker session JSONLs for tool-usage errors.

Investigation instrument (not product): fact-based analysis of the update-
tool problem — failure taxonomy, edit-chain C2 pricing, recovery behavior,
misuse forensics. Reads ./local/context/*.jsonl (cwd glob pattern
overridable); see _parse_file for the record schema.
"""

import argparse
import difflib
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_CONTEXT_FILES = "./local/context/*.jsonl"
DEFAULT_SINCE_DAYS = 15
_EXAMPLES_PER_CATEGORY = 3
_DETAIL_ROWS = 5
_STREAK_TOP = 5
_BIG_PATCH_LINES = 20
_RETRY_SIM_THRESHOLD = 0.9
_RESULT_PREVIEW = 120

ERROR_CATEGORIES = {
  "search-not-found": (
    r"search text not found",
  ),
  "ambiguous-match": (
    r"appears multiple times",
  ),
  "anchor-duplication": (
    r"doesn't need to be repeated",
  ),
  "no-op-edit": (
    r"no-op: old_string equals new_string",
  ),
  "invalid-arguments": (
    r"invalid arguments",
    r"unknown argument",
    r"missing required argument",
  ),
  "guardrail-protected": (
    r"write-protected",
    r"invalid path",
    r"path outside allowed",
    r"file is write-protected",
  ),
  "not-found": (
    r"file not found",
  ),
  "other": (),  # fallback — never matches, receives unmatched errors
}

_STUB_MARKER = "pruned by force_stub_tool_results"
_WRITE_TOOLS = ("update", "write", "update2")
_READ_TOOLS = ("read",)

# ============================================================================
# Parsing + per-file analysis
# ============================================================================


def _parse_file(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  """Line-ordered stream of tool_call/tool_result records from a session file."""
  stream: list[dict[str, Any]] = []
  meta: dict[str, Any] = {}
  with open(path, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
      try:
        rec = json.loads(line)
      except json.JSONDecodeError:
        stream.append({"line": i, "record": None})
        continue
      rtype = rec.get("type")
      data = rec.get("data") or {}
      if rtype in ("tool_call_message", "tool_result", "session_start", "turn_start"):
        stream.append({"line": i, "record": rec})
      if rtype == "session_start" and isinstance(data, dict):
        meta["session_id"] = data.get("session_id") or Path(path).name
        meta["agents"] = data.get("agents") or []
  return stream, meta


def _call_args(call: dict) -> dict:
  args = call.get("arguments")
  if isinstance(args, str):
    try:
      args = json.loads(args)
    except (json.JSONDecodeError, TypeError):
      args = {}
  return args if isinstance(args, dict) else {}


def _call_meta(call: dict) -> tuple[str, dict]:
  """(tool_name, parsed_args) from a persisted call record.

  Calls persist OpenAI-style: {"id", "function": {"name", "arguments"}} —
  unwrap "function" when present; tolerate flat {"name", "arguments"}.
  """
  func = call.get("function")
  if isinstance(func, dict):
    call = func
  name = call.get("name")
  return (str(name) if name is not None else ""), _call_args(call)


def _classify(text: str) -> str:
  low = text.lower()
  for category, patterns in ERROR_CATEGORIES.items():
    for pattern in patterns:
      if re.search(pattern, low):
        return category
  return "other"


def analyze_file(path: Path) -> dict[str, Any]:
  """One session file → {meta, failures, transitions, chains,...}.

  Calls and results paired by tool_id. Write-tools update per-path state:
  read → fresh; read with stub marker → stubbed; write ok → settled;
  write fail → failing (streak + retry-chain tracking).
  """
  stream, meta = _parse_file(path)
  calls_by_id: dict[str, dict] = {}
  failures: list[dict] = []
  transitions: Counter = Counter()
  stub_reads = 0
  stub_edits: list[dict] = []
  fail_streaks: list[dict] = []
  write_walk: list[dict] = []
  parallel_same_path: list[dict] = []
  malformed: list[str] = []
  tool_results: Counter = Counter()

  state: dict[str, str] = {}      # resolved path → fresh|stubbed|settled|failing
  streak: dict[str, int] = {}
  streak_first: dict[str, str] = {}
  chain: dict[str, int] = {}      # path → same-mistake retry depth
  chain_first: dict[str, dict] = {}

  for item in stream:
    rec = item["record"]
    line = item["line"]
    if rec is None:
      malformed.append(f"{path}: {line}")
      continue
    rtype = rec.get("type")
    data = rec.get("data") or {}

    if rtype == "tool_call_message":
      for call in data.get("tool_calls") or []:
        if not isinstance(call, dict) or not call.get("id"):
          continue
        tool_id = str(call["id"])
        name, args = _call_meta(call)
        calls_by_id[tool_id] = {"name": name, "args": args, "line": line}
        base = name.split("__")[-1]
        if base in _WRITE_TOOLS:
          p = args.get("path")
          if isinstance(p, str) and p:
            # Group calls from the same message hitting the same path.
            pass
      # parallel same-path stacking (Layer 4): calls in one message that
      # touch the same file — second call was built before the first ran.
      writes_in_msg: dict[str, dict] = {}
      for call in data.get("tool_calls") or []:
        if not isinstance(call, dict):
          continue
        name = _call_meta(call)[0].split("__")[-1]
        args = _call_args(call)
        if name in _WRITE_TOOLS and isinstance(args.get("path"), str) and args["path"]:
          key = os.path.normpath(args["path"])
          if key in writes_in_msg:
            parallel_same_path.append({
              "line": line,
              "path": args["path"],
              "first": writes_in_msg[key].get("operation"),
              "second": args.get("operation"),
            })
          writes_in_msg[key] = args
      continue

    if rtype == "tool_result":
      tool_id = data.get("tool_id")
      if not isinstance(tool_id, str) or tool_id not in calls_by_id:
        continue
      call = calls_by_id[tool_id]
      tool_name = str(call["name"] or "").split("__")[-1]
      success = data.get("success") is not False
      result_text = data.get("result") or ""
      pruned = data.get("pruned")
      is_stub = isinstance(pruned, dict) and "force_stub" in json.dumps(pruned)
      is_stub = is_stub or _STUB_MARKER in result_text
      tool_results[tool_name] += 1

      base = call["name"].split("__")[-1]
      raw_path = _call_args_from_id(calls_by_id, tool_id).get("path")
      resolved = os.path.normpath(raw_path) if isinstance(raw_path, str) and raw_path else None

      if not success:
        failures.append({
          "line": line,
          "tool": tool_name,
          "category": _classify(result_text),
          "path": resolved,
          "excerpt": result_text[:_RESULT_PREVIEW],
        })
        if resolved and tool_name in _WRITE_TOOLS:
          streak[resolved] = streak.get(resolved, 0) + 1
          streak_first.setdefault(resolved, _classify(result_text))

      if resolved and tool_name in _READ_TOOLS:
        state[resolved] = "stubbed" if is_stub else "fresh"
        stub_reads += is_stub
        continue

      if resolved and tool_name in _WRITE_TOOLS:
        prev = state.get(resolved)
        outcome = "ok" if success else "fail"
        transitions[(prev, outcome)] += 1
        if prev == "stubbed" and success:
          stub_edits.append({"path": raw_path, "line": line, "tool": tool_name})
        if success:
          streak.pop(resolved, None)
        entry = {
          "line": line,
          "path": resolved,
          "raw_path": raw_path,
          "tool": tool_name,
          "success": success,
          "prev": prev,
          "category": _classify(result_text) if not success else None,
          "args": call["args"],
        }
        write_walk.append(entry)

        # same-mistake chain: consecutive same-path failures
        if not success:
          chain[resolved] = chain.get(resolved, 0) + 1
          if chain[resolved] == 1:
            chain_first[resolved] = entry
          else:
            fail_streaks.append({
              "depth": chain[resolved],
              "first_category": streak_first.get(resolved, "?"),
              "path": raw_path,
              "file": str(path),
            })
        else:
          if chain.get(resolved, 0) >= 2:
            fail_streaks.append({
              "depth": chain[resolved],
              "first_category": chain_first[resolved]["category"] or "?",
              "path": raw_path,
              "file": str(path),
            })
          chain.pop(resolved, None)
          chain_first.pop(resolved, None)
          state[resolved] = "settled"
        continue

  return {
    "meta": meta,
    "malformed": malformed,
    "failures": failures,
    "transitions": transitions,
    "tool_results": tool_results,
    "stub_reads": stub_reads,
    "stub_edits": stub_edits,
    "fail_streaks": fail_streaks,
    "write_walk": write_walk,
    "parallel_same_path": parallel_same_path,
  }


def _call_args_from_id(calls_by_id: dict[str, dict], tool_id: str) -> dict:
  return calls_by_id[tool_id].get("args") or {}


# ============================================================================
# Layer 4 helpers
# ============================================================================


def _arg_lines(args: dict, key: str) -> int:
  value = args.get(key)
  if not isinstance(value, str) or not value:
    return 0
  return value.count("\n") + 1


def _similarity(a: str, b: str) -> float:
  if not isinstance(a, str) or not isinstance(b, str):
    return 0.0
  return difflib.SequenceMatcher(None, a, b).ratio()


def analyze_write_walk(write_walk: list[dict]) -> dict:
  """Layer 4: misuse forensics from the write-walk stream."""
  patch_len_ok: list[int] = []
  patch_len_fail: list[int] = []
  retry_chains: list[dict] = []
  give_ups: list[dict] = []
  strategy_notes: Counter = Counter()

  last_by_path: dict[str, dict] = {}
  fail_repeat: dict[str, int] = {}
  ends_failing: dict[str, dict] = {}

  for w in write_walk:
    key = w["path"]
    args = w["args"] if isinstance(w.get("args"), dict) else {}
    old_lines_count = _arg_lines(args, "old_string")
    old_string = args.get("old_string") if isinstance(args.get("old_string"), str) else ""

    if w["tool"] and w["tool"].endswith("update") and old_lines_count:
      if w["success"]:
        patch_len_ok.append(old_lines_count)
      else:
        patch_len_fail.append(old_lines_count)

    prev = last_by_path.get(key)
    if not w["success"]:
      ends_failing[key] = w
      if prev and not prev["success"]:
        sim = _similarity(old_string, prev.get("old_string", ""))
        if sim >= _RETRY_SIM_THRESHOLD or (old_string and old_string == prev.get("old_string")):
          fail_repeat[key] = fail_repeat.get(key, 0) + 1
          if fail_repeat[key] == 1:
            retry_chains.append({
              "path": w["raw_path"], "file": None, "start_line": prev["line"],
            })
          retry_chains[-1]["retries"] = fail_repeat[key]
          retry_chains[-1]["last_line"] = w["line"]
        else:
          fail_repeat[key] = 0
    else:
      ends_failing.pop(key, None)
      if prev and not prev["success"]:
        changes = []
        sim = _similarity(old_string, prev.get("old_string", ""))
        if old_lines_count and old_lines_count < _arg_lines(prev.get("args"), "old_string"):
          changes.append("shorter-patch")
        if not old_lines_count or sim < _RETRY_SIM_THRESHOLD:
          changes.append("different-anchor")
        strategy_notes["+".join(changes) or "same-args-succeeded"] += 1
      fail_repeat.pop(key, None)
    last_by_path[key] = {
      "args": args, "old_string": old_string, "success": w["success"], "line": w["line"],
    }

  give_ups = sorted(ends_failing.values(), key=lambda w: w["line"])
  return {
    "patch_len_ok": patch_len_ok, "patch_len_fail": patch_len_fail,
    "retry_chains": retry_chains, "give_ups": give_ups,
    "strategy_notes": strategy_notes,
  }


# ============================================================================
# Census (review gate)
# ============================================================================


def census(files: list[Path]) -> dict:
  """Record-type/key census + pairing coverage — the parse-assumptions gate."""
  types: Counter = Counter()
  keys_by_type: dict[str, Counter] = {}
  pairing: Counter = Counter()
  arg_keys: dict[str, Counter] = {}
  update_ops: Counter = Counter()
  stub_files: set[str] = set()

  for path in files:
    _stream, meta = _parse_file(path)
    sid = str(meta.get("session_id") or path.name)
    with open(path, encoding="utf-8") as f:
      for line in f:
        try:
          rec = json.loads(line)
        except json.JSONDecodeError:
          continue
        rtype = rec.get("type")
        data = rec.get("data") or {}
        if not rtype:
          continue
        types[rtype] += 1
        if isinstance(data, dict):
          keys_by_type.setdefault(rtype, Counter()).update(data.keys())
        if rtype == "tool_result":
          pairing["with" if isinstance(data.get("tool_id"), str) else "without"] += 1
          pruned = data.get("pruned")
          if (isinstance(pruned, dict) and "force_stub" in json.dumps(pruned)) or isinstance(data.get("result"), str) and _STUB_MARKER in data["result"]:
            stub_files.add(sid)
        elif rtype == "tool_call_message":
          for call in data.get("tool_calls") or []:
            if not isinstance(call, dict):
              continue
            name = _call_meta(call)[0].split("__")[-1]
            args = _call_args(call)
            arg_keys.setdefault(name, Counter()).update(args.keys())
            if name == "update" and isinstance(args.get("operation"), str):
              update_ops[args["operation"]] += 1

  return {
    "files": len(files),
    "record_types": dict(sorted(types.items())),
    "pairing": dict(pairing),
    "arg_keys_per_tool": {k: dict(v) for k, v in sorted(arg_keys.items())},
    "update_operation_values": dict(sorted(update_ops.items(), key=lambda kv: -kv[1])),
    "files_with_stubbed_results": len(stub_files),
  }


# ============================================================================
# Aggregation + report
# ============================================================================


def build_report(files: list[Path], since: datetime, skipped: list[tuple[str, str]]) -> dict:
  """Aggregate per-file models into one report model."""
  failures: list[dict] = []
  failures_by_tool_cat: Counter = Counter()
  tool_results: Counter = Counter()
  transitions: Counter = Counter()
  stub_edits: list[dict] = []
  stub_read_events = 0
  fail_streaks: list[dict] = []
  malformed: list[tuple[str, str]] = []
  parallel_same_path: list[dict] = []
  patch_len_ok: list[int] = []
  patch_len_fail: list[int] = []
  retry_chains: list[dict] = []
  give_ups: list[dict] = []
  strategy_notes: Counter = Counter()
  file_summaries: list[dict] = []

  for path in files:
    try:
      f = analyze_file(path)
    except OSError as e:
      skipped.append((str(path), f"read failed: {e}"))
      continue

    events = sum(f["tool_results"].values())
    tool_results.update(f["tool_results"])
    file_summaries.append({
      "file": str(path),
      "session_id": f["meta"].get("session_id"),
      "tool_events": events,
    })
    for failure in f["failures"]:
      rec = dict(failure)
      rec["file"] = str(path)
      failures.append(rec)
      failures_by_tool_cat[(rec["tool"], rec["category"])] += 1
    transitions.update(f["transitions"])
    stub_edits.extend(f["stub_edits"])
    stub_read_events += f["stub_reads"]
    fail_streaks.extend(f["fail_streaks"])
    parallel_same_path.extend(f["parallel_same_path"])
    malformed.extend((str(path), m) for m in f["malformed"])

    l4 = analyze_write_walk(f["write_walk"])
    patch_len_ok.extend(l4["patch_len_ok"])
    patch_len_fail.extend(l4["patch_len_fail"])
    for c in l4["retry_chains"]:
      c["file"] = str(path)
      retry_chains.append(c)
    give_ups.extend(dict(g, file=str(path)) for g in l4["give_ups"])
    strategy_notes.update(l4["strategy_notes"])

  # C2 pricing
  chain_links = transitions.get(("settled", "ok"), 0) + transitions.get(("settled", "fail"), 0)
  harm = transitions.get(("settled", "fail"), 0)
  harmless = transitions.get(("settled", "ok"), 0)
  avg_read_tokens = 0
  c2 = {
    "chain_links": chain_links,
    "harm": harm,
    "harmless": harmless,
    "overhead": harmless * avg_read_tokens,
  }

  streak_buckets = Counter(
    "3+" if s["depth"] >= 3 else str(s["depth"]) for s in fail_streaks
  )

  return {
    "corpus": {
      "files": len(files),
      "since": since.isoformat(),
      "skipped": skipped,
      "malformed": len(malformed),
      "busiest": sorted(
        (s for s in file_summaries if s["tool_events"] > 0),
        key=lambda s: -s["tool_events"],
      )[:_DETAIL_ROWS],
    },
    "census": census(files) if files else {"files": 0},
    "layer1": {
      "total_failures": len(failures),
      "by_tool_and_category": {
        f"{t} :: {c}": n for (t, c), n in failures_by_tool_cat.most_common()
      },
      "examples": _examples(failures),
    },
    "layer2": {
      "c2": c2,
      "transitions": {f"{p}->{o}": n for (p, o), n in transitions.most_common()},
    },
    "layer3": {
      "fail_streaks": sorted(streak_buckets.items(), key=lambda kv: -kv[1]),
      "streak_detail": sorted(fail_streaks, key=lambda s: -s["depth"])[:_STREAK_TOP],
      "stub_reads": stub_read_events,
      "stub_edits": stub_edits[:_STREAK_TOP],
    },
    "layer4": {
      "patch_len_ok_avg": (sum(patch_len_ok) // len(patch_len_ok)) if patch_len_ok else 0,
      "patch_len_fail_avg": (sum(patch_len_fail) // len(patch_len_fail)) if patch_len_fail else 0,
      "patch_len_fail_over_big": sum(v >= _BIG_PATCH_LINES for v in patch_len_fail),
      "patch_len_ok_over_big": sum(v >= _BIG_PATCH_LINES for v in patch_len_ok),
      "give_ups": give_ups[:_DETAIL_ROWS],
      "give_up_count": len(give_ups),
      "retry_chains": sorted(retry_chains, key=lambda c: -c.get("retries", 0))[:_DETAIL_ROWS],
      "retry_chain_count": len(retry_chains),
      "strategy_notes": dict(strategy_notes.most_common()),
      "parallel_same_path": len(parallel_same_path),
    },
  }


def _examples(failures: list[dict]) -> dict[str, list[dict]]:
  grouped: dict[str, list[dict]] = {}
  for failure in failures:
    grouped.setdefault(failure["category"], []).append({
      "tool": failure["tool"],
      "line": failure.get("line"),
      "file": failure["file"],
      "excerpt": failure.get("excerpt", ""),
    })
  return {k: v[:_EXAMPLES_PER_CATEGORY] for k, v in grouped.items()}


# ============================================================================
# Rendering + main
# ============================================================================


def render_text(report: dict) -> str:
  """Condensed human report — census section is a review gate first."""
  lines: list[str] = []
  add = lines.append
  corpus = report["corpus"]

  add("=== Yoker Tool Error Analyzer ===")
  add(f"files: {corpus['files']} (since {corpus['since']})  "
      f"malformed lines: {corpus['malformed']}  skipped: {len(corpus['skipped'])}")
  if corpus["skipped"]:
    for skipped_file, reason in corpus["skipped"]:
      add(f"  SKIPPED {skipped_file}: {reason}")
  if corpus["busiest"]:
    add("  busiest sessions:")
    for s in corpus["busiest"]:
      add(f"    {s['tool_events']:>5} events  {s['session_id']}")
  add("")

  cen = report["census"]
  add("--- Census (review gate: unexpected shapes = parsing needs a look) ---")
  add(f"  record types: {cen['record_types']}")
  add(f"  tool_id pairing: {cen['pairing']}")
  add(f"  update2-related arg keys: {cen['arg_keys_per_tool'].get('update2', '(no update2 use yet)')}")
  add(f"  files with stubbed results: {cen['files_with_stubbed_results']}")
  add("")

  l1 = report["layer1"]
  add("--- Layer 1: failures ---")
  add(f"  total: {l1['total_failures']}")
  for key, count in l1["by_tool_and_category"].items():
    add(f"    {count:>5}  {key}")
  add("  examples:")
  for category, items in l1["examples"].items():
    add(f"    [{category}]")
    for item in items:
      add(f"      {item['file']}:{item.get('line', '?')} · {item['tool']} · {item.get('excerpt', '')[:100]}")
  add("")

  l2 = report["layer2"]
  c2 = l2["c2"]
  add("--- Layer 2: strict-C2 simulation (edit chains) ---")
  add(f"  chain links: {c2['chain_links']}   harm: {c2['harm']}   "
      f"harmless: {c2['harmless']}   est overhead: ~{c2['overhead']} tokens")
  add(f"  transitions: {l2['transitions']}")
  add("")

  l3 = report["layer3"]
  add("--- Layer 3: recovery signals ---")
  add(f"  fail-streak depths: {dict(l3['fail_streaks']) or '(none)'}")
  for s in l3["streak_detail"]:
    add(f"    depth {s['depth']} [{s['first_category']}] {s['path']} ({s['file']})")
  add(f"  stubbed reads: {l3['stub_reads']}   edits after stubbed reads: {len(l3['stub_edits'])}")
  for s in l3["stub_edits"]:
    add(f"    {s['path']} ({s['tool']})")
  add("")

  l4 = report["layer4"]
  add("--- Layer 4: misuse forensics ---")
  add(f"  avg old_string lines — failed: {l4['patch_len_fail_avg']}  ok: {l4['patch_len_ok_avg']}")
  add(f"  patches ≥{_BIG_PATCH_LINES} lines: failed {l4['patch_len_fail_over_big']} / ok {l4['patch_len_ok_over_big']}")
  add(f"  same-mistake repair chains: {l4['retry_chain_count']}")
  for c in l4["retry_chains"]:
    add(f"    {c.get('retries', '?')}x {c.get('path', '?')} ({c.get('file', '?')}:{c.get('start_line', '?')})"
        + (f" → last line {c.get('last_line', '?')}" if c.get("last_line") else ""))
  add(f"  recoveries: {l4['strategy_notes'] or '(none observed)'}")
  add(f"  give-ups: {l4['give_up_count']}")
  for g in l4["give_ups"]:
    add(f"    {g.get('raw_path', '?')} ({g.get('tool', '?')}) "
        f"({g.get('file', '?')}:{g.get('line', '?')})")
  add(f"  parallel same-path write stacking: {l4['parallel_same_path']}")
  add("")

  add("limitations: success-only corruption invisible unless a later gate "
      "fails; cross-session path identity is best-effort.")
  return "\n".join(lines)


def _expand_files(patterns: list[str], since: datetime) -> tuple[list[Path], list[tuple[str, str]]]:
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
  """Parse '[since_days] [globs...] [--json]'; render; exit 0."""
  parser = argparse.ArgumentParser(description=__doc__)  # type: ignore[arg-type]
  parser.add_argument("positionals", nargs="*")
  parser.add_argument("--json", action="store_true")
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