"""Token usage logger: atomic JSONL appends for per-API-call token usage.

This module is the harness telemetry log (run-statistics R1/R4): one
append-only JSONL channel carrying per-event records — LLM API calls,
tool calls, turn boundaries, agent spawn/release, compaction runs,
errors and the run lifecycle bracket (run_start/run_end, R3) — each
attributable per ``agent_id`` with parent linkage where applicable.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)

# Record kinds for UsageRecord.kind. Kept as plain strings (not an Enum)
# so the JSONL stays plain-data and forward compatible.
KIND_LLM_CALL = "llm_call"
KIND_TOOL_CALL = "tool_call"
KIND_TURN = "turn"
KIND_SPAWN = "spawn"
KIND_RELEASE = "release"
KIND_COMPACTION = "compaction"
KIND_ERROR = "error"
# Run lifecycle (R3): one pair per Session context. run_start without a
# matching run_end in the log = the process crashed or was killed — the
# basis for crash detection and run accounting.
KIND_RUN_START = "run_start"
KIND_RUN_END = "run_end"


@dataclass(frozen=True)
class UsageRecord:
  """One telemetry event in the usage log.

  The record is the per-API-call token usage record it always was
  (``kind="llm_call"``) plus lifecycle events for the run-statistics
  feature. Token counts are populated ONLY on ``llm_call`` records —
  every token is counted exactly once, so summing llm_call rows
  reconciles with any rollup. Other kinds carry ``0`` there and put
  their kind-specific payload in ``detail``.

  Attributes:
    ts: ISO 8601 UTC timestamp with timezone.
    session_id: Context session identifier.
    model: Resolved model name.
    agent: Agent definition name.
    input_tokens: Prompt tokens as reported by the backend (0 when unknown).
    output_tokens: Completion tokens as reported by the backend (0 when unknown).
    duration_ms: API call duration in milliseconds (llm_call), tool
      execution wall-clock (tool_call), turn wall-clock (turn), or 0.
      run_end records keep the flat field at 0 and carry the run
      duration in ``detail["duration_ms"]`` instead.
    thinking_chars: Client-side char count of the thinking stream. Used with a
      calibrated chars-per-token ratio to estimate the thinking-token share;
      reported token counts are untouched.
    content_chars: Client-side char count of the visible content stream.
      Calibration baseline for the ratio above.
    agent_id: Session-assigned runtime id of the agent (None for
      standalone agents outside a session).
    parent_agent_id: Session-assigned id of the spawning agent (None for
      primary/standalone agents) — spawn-tree linkage for per-agent
      attribution.
    kind: Event kind — one of the KIND_* constants. Lifecycle kinds
      (spawn/release/run_start/run_end) differ in identity: spawn/release
      carry agent identity (agent_id + parent_agent_id); run_start/run_end
      carry none — there the run is the subject.
    tool: Tool name (tool_call records) or error source label (error
      records, e.g. ``idle_watchdog``); None for other kinds.
    success: Tool outcome (tool_call records — False for parse errors,
      guardrail blocks and unknown tools; None is never written for
      tool_call); error records write success=False. None for other kinds.
    cached_tokens: Provider-reported cached-input tokens when the backend
      exposes them; always None today (no backend exposes them yet).
    bytes_in: UTF-8 size of the tool-call arguments (tool_call records);
      None for other kinds. Backend payload bytes are not portably
      available and are intentionally not recorded.
    bytes_out: UTF-8 size of the tool result string (tool_call records);
      None for other kinds.
    detail: Kind-specific payload (e.g. turn tool_calls_count, compaction
      run report excerpt, error description). Never a substitute for the
      flat fields — only supplementary data. On ``llm_call`` records:
      ``{"images": n}`` when the submitted view carried send-once image
      refs (n > 0) — image tokens inflate the server count but are
      invisible to the char/4 estimate, so an image sawtooth in the
      gauge/usage log is diagnosable from this key (TODO.md M.8).
  """

  ts: str
  session_id: str
  model: str
  agent: str
  input_tokens: int
  output_tokens: int
  duration_ms: int
  # Defaults keep old call sites and pre-existing log records compatible.
  thinking_chars: int = 0
  content_chars: int = 0
  agent_id: str | None = None
  parent_agent_id: str | None = None
  kind: str = KIND_LLM_CALL
  tool: str | None = None
  success: bool | None = None
  cached_tokens: int | None = None
  bytes_in: int | None = None
  bytes_out: int | None = None
  detail: dict[str, Any] | None = field(default=None)


class UsageLogger:
  """Appends :class:`UsageRecord` entries to a JSONL file.

  Each record is written as a single line via one ``os.write`` on an
  ``O_APPEND`` descriptor — atomic on POSIX, so parallel sessions sharing
  the same file never interleave lines. Windows lacks this guarantee.
  Logging failures are swallowed with a warning; usage logging must never
  break an agent turn.
  """

  def __init__(self, path: str) -> None:
    self._path = Path(path).expanduser()

  def log(self, record: UsageRecord) -> None:
    """Append one record as a compact single-line JSON object.

    Never raises — ALL failures (I/O and serialization alike) are
    logged as warnings and swallowed. Telemetry must never break a
    turn.
    """
    try:
      self._path.parent.mkdir(parents=True, exist_ok=True)
      line = json.dumps(asdict(record), separators=(",", ":"), default=str) + "\n"
      # O_APPEND + single write: atomic on POSIX (see class docstring).
      fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
      try:
        os.write(fd, line.encode())
      finally:
        os.close(fd)
    except Exception as e:
      # json.dumps with default=str handles the common escapes, but a
      # pathological detail (e.g. a raising __str__) can still raise —
      # catch broadly to honor the never-raises contract.
      logger.warning("usage_log_write_failed", path=str(self._path), error=str(e))


def _now_iso() -> str:
  return datetime.now(UTC).isoformat()


def _agent_ids(agent: Any) -> tuple[str | None, str | None]:
  """Read (agent_id, parent_agent_id) from an agent, tolerating stand-ins."""
  return (
    getattr(agent, "_agent_id", None),
    getattr(agent, "_parent_agent_id", None),
  )


def _session_id_of(agent: Any) -> str:
  session_id: str = "unknown"
  try:
    session_id = agent.context.get_session_id()
  except Exception:
    pass
  return str(session_id)


def log_usage_record(usage_config: Any, record: UsageRecord) -> None:
  """Append one telemetry record. Best-effort, never raises.

  Shared gate for ALL log writers: skipped under pytest (mock runs must
  not pollute the real log — mirrors the dev/test bypass in
  ``Agent.__init__``) and when usage logging is disabled.
  """
  if os.environ.get("PYTEST_CURRENT_TEST"):
    return
  if not usage_config.enabled:
    return
  UsageLogger(usage_config.path).log(record)


def log_call_usage(agent: Any, stats: dict[str, int]) -> None:
  """Log one usage record for an LLM API call (kind="llm_call").

  Best-effort, never raises. ``agent`` is the core Agent — typed as
  ``Any`` to avoid a circular import with ``yoker.core``.

  Skipped under pytest (``PYTEST_CURRENT_TEST`` set): tests exercise the
  processing loop with mock backends whose stats would otherwise pollute
  the real usage log. Mirrors the dev/test bypass pattern in
  ``Agent.__init__``. Unit tests for logging clear the env var explicitly.
  """
  usage_config = agent.config.usage
  if not usage_config.enabled:
    return

  # Backends fill one pair: Ollama (prompt_eval_count/eval_count) or
  # LiteLLM (input_tokens/output_tokens). Normalize to the common names.
  input_tokens = stats.get("input_tokens") or stats.get("prompt_eval_count") or 0
  output_tokens = stats.get("output_tokens") or stats.get("eval_count") or 0
  if not input_tokens and not output_tokens:
    return

  agent_id, parent_agent_id = _agent_ids(agent)

  record = UsageRecord(
    ts=_now_iso(),
    session_id=_session_id_of(agent),
    model=agent.model,
    agent=agent.definition.name,
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    duration_ms=stats.get("total_duration_ms") or 0,
    thinking_chars=stats.get("thinking_chars") or 0,
    content_chars=stats.get("content_chars") or 0,
    agent_id=agent_id,
    parent_agent_id=parent_agent_id,
    kind=KIND_LLM_CALL,
    # Image refs riding the submitted view (send-once) inflate the server
    # token count but are invisible to the estimate — recorded so a
    # gauge/token sawtooth is diagnosable as image-caused (TODO.md M.8).
    detail=(
      {"images": agent._context_submission_image_count}
      if getattr(agent, "_context_submission_image_count", 0)
      else None
    ),
  )
  log_usage_record(usage_config, record)


def log_tool_call_usage(
  agent: Any,
  tool_name: str,
  *,
  success: bool,
  duration_ms: int,
  bytes_in: int,
  bytes_out: int,
) -> None:
  """Log one tool-call record (kind="tool_call"). Best-effort, never raises.

  Args:
    agent: The executing agent (identity + config source).
    tool_name: The (namespaced) tool name as dispatched.
    success: Whether the tool reported success (parse/guardrail/unknown
      tool failures included — anything that returned an error to the LLM).
    duration_ms: Tool execution wall-clock in milliseconds.
    bytes_in: UTF-8 size of the serialized call arguments.
    bytes_out: UTF-8 size of the result string returned to the LLM.
  """
  agent_id, parent_agent_id = _agent_ids(agent)
  record = UsageRecord(
    ts=_now_iso(),
    session_id=_session_id_of(agent),
    model=agent.model,
    agent=agent.definition.name,
    input_tokens=0,
    output_tokens=0,
    duration_ms=duration_ms,
    agent_id=agent_id,
    parent_agent_id=parent_agent_id,
    kind=KIND_TOOL_CALL,
    tool=tool_name,
    success=success,
    bytes_in=bytes_in,
    bytes_out=bytes_out,
  )
  log_usage_record(agent.config.usage, record)


def log_turn_usage(
  agent: Any,
  *,
  duration_ms: int,
  tool_calls_count: int,
  llm_calls: int,
) -> None:
  """Log one turn boundary record (kind="turn"). Best-effort, never raises.

  Carries the turn's WALL-CLOCK duration (all LLM calls + tool execution)
  — deliberately WITHOUT token counts: tokens live on the per-call
  llm_call records so summing the log never double-counts.
  """
  agent_id, parent_agent_id = _agent_ids(agent)
  record = UsageRecord(
    ts=_now_iso(),
    session_id=_session_id_of(agent),
    model=agent.model,
    agent=agent.definition.name,
    input_tokens=0,
    output_tokens=0,
    duration_ms=duration_ms,
    agent_id=agent_id,
    parent_agent_id=parent_agent_id,
    kind=KIND_TURN,
    detail={"tool_calls_count": tool_calls_count, "llm_calls": llm_calls},
  )
  log_usage_record(agent.config.usage, record)


def log_compaction_usage(agent: Any, run: dict[str, Any]) -> None:
  """Log one compaction record (kind="compaction"). Best-effort, never raises.

  ``run`` is the compaction run report already recorded in the context
  (run_id, trigger estimate, stages, dropped_count, ...). The tokens the
  pipeline removed from the VIEW are derivable from the stage list; the
  report is embedded verbatim in ``detail``.
  """
  agent_id, parent_agent_id = _agent_ids(agent)
  record = UsageRecord(
    ts=_now_iso(),
    session_id=_session_id_of(agent),
    model=agent.model,
    agent=agent.definition.name,
    input_tokens=0,
    output_tokens=0,
    duration_ms=0,
    agent_id=agent_id,
    parent_agent_id=parent_agent_id,
    kind=KIND_COMPACTION,
    detail={"run": run},
  )
  log_usage_record(agent.config.usage, record)


def log_error_usage(
  agent: Any, *, source: str, message: str, detail: dict[str, Any] | None = None
) -> None:
  """Log one error record (kind="error"). Best-effort, never raises.

  Used for operational errors the run-statistics rollup should count:
  idle-watchdog timeouts, retry-limit escalations. Tool execution
  failures are NOT logged here — they are tool_call records with
  ``success=False``.
  """
  agent_id, parent_agent_id = _agent_ids(agent)
  record = UsageRecord(
    ts=_now_iso(),
    session_id=_session_id_of(agent),
    model=agent.model,
    agent=agent.definition.name,
    input_tokens=0,
    output_tokens=0,
    duration_ms=0,
    agent_id=agent_id,
    parent_agent_id=parent_agent_id,
    kind=KIND_ERROR,
    tool=source,
    success=False,
    detail={"message": message, **(detail or {})},
  )
  log_usage_record(agent.config.usage, record)


def log_run_usage(
  usage_config: Any,
  *,
  session_id: str,
  kind: str,
  detail: dict[str, Any] | None = None,
) -> None:
  """Log a run-lifecycle record (run_start/run_end). Best-effort.

  Used by Session.__aenter__/__aexit__ to bracket one session context in
  the log. Crash detection: a run_start whose run_end is missing means
  the process died before clean teardown. No agent identity is attached
  — the run is the subject, not any single agent.
  """
  record = UsageRecord(
    ts=_now_iso(),
    session_id=session_id,
    model="unknown",
    agent="session",
    input_tokens=0,
    output_tokens=0,
    duration_ms=0,
    agent_id=None,
    parent_agent_id=None,
    kind=kind,
    detail=detail,
  )
  log_usage_record(usage_config, record)


def log_session_usage(
  usage_config: Any,
  *,
  session_id: str,
  kind: str,
  agent: str,
  agent_id: str,
  parent_agent_id: str | None = None,
  model: str | None = None,
  detail: dict[str, Any] | None = None,
) -> None:
  """Log a session-level lifecycle record (spawn/release). Best-effort.

  Used by the Session layer for spawn/release events — the session knows
  the ids directly (no agent instance needed) and must not depend on an
  agent's config object.
  """
  record = UsageRecord(
    ts=_now_iso(),
    session_id=session_id,
    model=model or "unknown",
    agent=agent,
    input_tokens=0,
    output_tokens=0,
    duration_ms=0,
    agent_id=agent_id,
    parent_agent_id=parent_agent_id,
    kind=kind,
    detail=detail,
  )
  log_usage_record(usage_config, record)


__all__ = [
  "KIND_COMPACTION",
  "KIND_ERROR",
  "KIND_LLM_CALL",
  "KIND_RELEASE",
  "KIND_RUN_END",
  "KIND_RUN_START",
  "KIND_SPAWN",
  "KIND_TOOL_CALL",
  "KIND_TURN",
  "UsageLogger",
  "UsageRecord",
  "log_call_usage",
  "log_compaction_usage",
  "log_error_usage",
  "log_run_usage",
  "log_session_usage",
  "log_tool_call_usage",
  "log_turn_usage",
  "log_usage_record",
]
