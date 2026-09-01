"""Token usage logging — one JSONL record per LLM API call.

Records are appended with ``O_APPEND`` + a single ``os.write``, which is
atomic on POSIX: parallel sessions/processes never interleave lines.
(Windows does not provide this guarantee.)
"""

from .logger import UsageLogger, UsageRecord, log_call_usage

__all__ = ["UsageLogger", "UsageRecord", "log_call_usage"]
