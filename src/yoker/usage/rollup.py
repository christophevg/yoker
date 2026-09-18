"""Stats rollup: scope/delta aggregation over the telemetry log.

Pure functions over usage-log records (see :mod:`yoker.usage.logger`) —
no tool or session machinery. The Session-injected ``stats`` tool
(:mod:`yoker.session.tools`) loads the log and calls :func:`rollup`.

Scopes (R2):
  - ``self``: records of the calling agent only.
  - ``subtree``: the calling agent plus every agent whose parent chain
    reaches it (spawn tree, resolved from spawn records AND the live
    session map).
  - ``session``: all records of the session.

All token/duration/cost-free aggregates come from record kinds:
  - llm_call rows carry tokens and per-call duration (token invariant —
    these are the ONLY rows summed for tokens).
  - turn rows carry completed-turn wall-clock and call counts.
  - tool_call rows carry success/failure and bytes.
  - error rows count operational errors; compaction rows carry the run
    report (dropped counts) in ``detail``.
  - spawn/release rows define the spawn tree and concurrency timeline.
"""

from typing import Any

from yoker.usage.logger import (
  KIND_COMPACTION,
  KIND_ERROR,
  KIND_LLM_CALL,
  KIND_RELEASE,
  KIND_SPAWN,
  KIND_TOOL_CALL,
  KIND_TURN,
)

SCOPE_SELF = "self"
SCOPE_SUBTREE = "subtree"
SCOPE_SESSION = "session"
SCOPES = (SCOPE_SELF, SCOPE_SUBTREE, SCOPE_SESSION)


def subtree_ids(
  caller_id: str,
  records: list[dict[str, Any]],
  live_parents: dict[str, str | None] | None = None,
) -> set[str]:
  """Return the caller id plus every descendant id (transitive).

  The parent relation is derived from spawn records; ``live_parents``
  (agent_id -> parent_agent_id from the session's active map) is unioned
  in so agents spawned before the earliest available log record still
  resolve. Unknown parents (None / caller not in map) contribute nothing.

  Args:
    caller_id: The calling agent's session-assigned id.
    records: Telemetry records (spawn records define the tree).
    live_parents: Optional live agent_id -> parent_agent_id mapping.
  """
  parents: dict[str, str | None] = {}
  for r in records:
    if r.get("kind") == KIND_SPAWN:
      agent_id = r.get("agent_id")
      if agent_id:
        parents[agent_id] = r.get("parent_agent_id")
  if live_parents:
    for agent_id, parent in live_parents.items():
      parents.setdefault(agent_id, parent)

  subtree = {caller_id}
  # BFS over children-of-subtree; bounded by the parent table size.
  changed = True
  while changed:
    changed = False
    for agent_id, parent in parents.items():
      if agent_id in subtree:
        continue
      if parent in subtree:
        subtree.add(agent_id)
        changed = True
  return subtree


def peak_concurrency(records: list[dict[str, Any]], session_id: str) -> int | None:
  """Maximum number of simultaneously active agents in a session.

  Replays spawn (+1) / release (-1) events in timestamp order. Agents
  spawned but never released (session-teardown releases are not logged —
  owner decision) count as active until the end, which is correct for a
  peak. Returns None when the session has no spawn records (single-agent
  sessions: concurrency is 1 but it is not a *spawned* team).
  """
  deltas: list[tuple[str, int]] = []
  for r in records:
    if r.get("session_id") != session_id:
      continue
    kind = r.get("kind")
    if kind == KIND_SPAWN:
      deltas.append((str(r.get("ts", "")), 1))
    elif kind == KIND_RELEASE:
      deltas.append((str(r.get("ts", "")), -1))
  if not deltas:
    return None

  deltas.sort(key=lambda d: d[0])
  active = 0
  peak = 0
  for _, delta in deltas:
    active += delta
    peak = max(peak, active)
  return peak


def rollup(
  records: list[dict[str, Any]],
  *,
  session_id: str,
  scope: str,
  agent_ids: set[str] | None = None,
) -> dict[str, Any]:
  """Aggregate telemetry records for one scope.

  Args:
    records: All telemetry records (any session) — filtered here.
    session_id: The session's id (session scope filter).
    scope: One of SCOPES.
    agent_ids: For self/subtree scopes: the set of agent ids whose
      records belong to the scope (caller alone, or caller + subtree).

  Returns:
    Dict with per-scope aggregates. Token counts come exclusively from
    llm_call rows (the log's token invariant) — sums are exact.
  """
  if scope == SCOPE_SESSION:
    selected = [r for r in records if r.get("session_id") == session_id]
  elif scope in (SCOPE_SELF, SCOPE_SUBTREE):
    if agent_ids is None:
      raise ValueError(f"scope={scope} requires agent_ids")
    selected = [
      r for r in records if r.get("session_id") == session_id and r.get("agent_id") in agent_ids
    ]
  else:
    raise ValueError(f"Unknown scope: {scope!r} (expected one of {SCOPES})")

  turns = 0
  turn_wall_ms = 0
  llm_calls = 0
  llm_wall_ms = 0
  input_tokens = 0
  output_tokens = 0
  tool_calls = 0
  tool_failures = 0
  tool_bytes_in = 0
  tool_bytes_out = 0
  errors = 0
  compactions = 0
  compaction_dropped = 0
  spawns = 0
  releases = 0

  for r in selected:
    kind = r.get("kind")
    if kind == KIND_LLM_CALL:
      llm_calls += 1
      llm_wall_ms += r.get("duration_ms") or 0
      input_tokens += r.get("input_tokens") or 0
      output_tokens += r.get("output_tokens") or 0
    elif kind == KIND_TURN:
      turns += 1
      turn_wall_ms += r.get("duration_ms") or 0
    elif kind == KIND_TOOL_CALL:
      tool_calls += 1
      if r.get("success") is False:
        tool_failures += 1
      tool_bytes_in += r.get("bytes_in") or 0
      tool_bytes_out += r.get("bytes_out") or 0
    elif kind == KIND_ERROR:
      errors += 1
    elif kind == KIND_COMPACTION:
      compactions += 1
      # Fully defensive: detail or run may be None / non-dict in corrupt
      # records — drop the contribution rather than crash the rollup.
      detail = r.get("detail")
      run = detail.get("run") if isinstance(detail, dict) else None
      if isinstance(run, dict):
        compaction_dropped += run.get("dropped_count") or 0
    elif kind == KIND_SPAWN:
      spawns += 1
    elif kind == KIND_RELEASE:
      releases += 1

  result: dict[str, Any] = {
    "scope": scope,
    "turns": turns,
    "turn_wall_ms": turn_wall_ms,
    "llm_calls": llm_calls,
    "llm_wall_ms": llm_wall_ms,
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "tool_calls": tool_calls,
    "tool_failures": tool_failures,
    "tool_bytes_in": tool_bytes_in,
    "tool_bytes_out": tool_bytes_out,
    "errors": errors,
    "compactions": compactions,
    "compaction_dropped_messages": compaction_dropped,
  }
  # Lifecycle metrics only make sense above agent level.
  if scope == SCOPE_SESSION:
    result["spawns"] = spawns
    result["releases"] = releases
    peak = peak_concurrency(records, session_id)
    if peak is not None:
      result["peak_concurrency"] = peak
  return result


def render_stats(scope_results: dict[str, dict[str, Any]]) -> str:
  """Render rollup results as compact text for the calling agent.

  ``scope_results`` maps scope name -> rollup dict (session scope may be
  absent when the caller requested only a narrower scope). One block per
  scope; the ``since`` watermark note is the caller's business.
  """
  blocks: list[str] = []
  for scope, stats in scope_results.items():
    lines = [f"[{scope}]"]
    for key, value in stats.items():
      if key == "scope":  # echoed inside the header already
        continue
      lines.append(f"{key}: {value}")
    blocks.append("\n".join(lines))
  return "\n\n".join(blocks)


__all__ = [
  "SCOPES",
  "SCOPE_SELF",
  "SCOPE_SESSION",
  "SCOPE_SUBTREE",
  "peak_concurrency",
  "render_stats",
  "rollup",
  "subtree_ids",
]
