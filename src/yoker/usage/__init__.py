"""Token usage logging — one JSONL record per LLM API call.

Records are appended with ``O_APPEND`` + a single ``os.write``, which is
atomic on POSIX: parallel sessions/processes never interleave lines.
(Windows does not provide this guarantee.)

Also hosts the stats rollup (:mod:`yoker.usage.rollup`) — scope/delta
aggregation over the telemetry log for the Session-injected ``stats``
tool.
"""

from .logger import (
  KIND_COMPACTION,
  KIND_ERROR,
  KIND_LLM_CALL,
  KIND_RELEASE,
  KIND_SPAWN,
  KIND_TOOL_CALL,
  KIND_TURN,
  UsageLogger,
  UsageRecord,
  log_call_usage,
  log_compaction_usage,
  log_error_usage,
  log_session_usage,
  log_tool_call_usage,
  log_turn_usage,
  log_usage_record,
)
from .rollup import (
  SCOPE_SELF,
  SCOPE_SESSION,
  SCOPE_SUBTREE,
  SCOPES,
  peak_concurrency,
  render_stats,
  rollup,
  subtree_ids,
)

__all__ = [
  "KIND_COMPACTION",
  "KIND_ERROR",
  "KIND_LLM_CALL",
  "KIND_RELEASE",
  "KIND_SPAWN",
  "KIND_TOOL_CALL",
  "KIND_TURN",
  "UsageLogger",
  "UsageRecord",
  "log_call_usage",
  "log_compaction_usage",
  "log_error_usage",
  "log_session_usage",
  "log_tool_call_usage",
  "log_turn_usage",
  "log_usage_record",
  "SCOPES",
  "SCOPE_SELF",
  "SCOPE_SESSION",
  "SCOPE_SUBTREE",
  "peak_concurrency",
  "render_stats",
  "rollup",
  "subtree_ids",
]
