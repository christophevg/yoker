"""Token usage logger: atomic JSONL appends for per-API-call token usage."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from structlog import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class UsageRecord:
  """One LLM API call's token usage.

  Attributes:
    ts: ISO 8601 UTC timestamp with timezone.
    session_id: Context session identifier.
    model: Resolved model name.
    agent: Agent definition name.
    input_tokens: Prompt tokens as reported by the backend (0 when unknown).
    output_tokens: Completion tokens as reported by the backend (0 when unknown).
    duration_ms: API call duration in milliseconds.
    thinking_chars: Client-side char count of the thinking stream. Used with a
      calibrated chars-per-token ratio to estimate the thinking-token share;
      reported token counts are untouched.
    content_chars: Client-side char count of the visible content stream.
      Calibration baseline for the ratio above.
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

    Never raises on I/O failure — failures are logged as warnings.
    """
    try:
      self._path.parent.mkdir(parents=True, exist_ok=True)
      line = json.dumps(asdict(record), separators=(",", ":")) + "\n"
      # O_APPEND + single write: atomic on POSIX (see class docstring).
      fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
      try:
        os.write(fd, line.encode())
      finally:
        os.close(fd)
    except OSError as e:
      logger.warning("usage_log_write_failed", path=str(self._path), error=str(e))


def log_call_usage(agent: Any, stats: dict[str, int]) -> None:
  """Log one usage record for an LLM API call. Best-effort, never raises.

  ``agent`` is the core Agent — typed as ``Any`` to avoid a circular
  import with ``yoker.core``.

  Skipped under pytest (``PYTEST_CURRENT_TEST`` set): tests exercise the
  processing loop with mock backends whose stats would otherwise pollute
  the real usage log. Mirrors the dev/test bypass pattern in
  ``Agent.__init__``. Unit tests for logging clear the env var explicitly.
  """
  if os.environ.get("PYTEST_CURRENT_TEST"):
    return

  usage_config = agent.config.usage
  if not usage_config.enabled:
    return

  # Backends fill one pair: Ollama (prompt_eval_count/eval_count) or
  # LiteLLM (input_tokens/output_tokens). Normalize to the common names.
  input_tokens = stats.get("input_tokens") or stats.get("prompt_eval_count") or 0
  output_tokens = stats.get("output_tokens") or stats.get("eval_count") or 0
  if not input_tokens and not output_tokens:
    return

  try:
    session_id = agent.context.get_session_id()
  except Exception:
    session_id = "unknown"

  record = UsageRecord(
    ts=datetime.now(timezone.utc).isoformat(),
    session_id=session_id,
    model=agent.model,
    agent=agent.definition.name,
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    duration_ms=stats.get("total_duration_ms") or 0,
    thinking_chars=stats.get("thinking_chars") or 0,
    content_chars=stats.get("content_chars") or 0,
  )
  UsageLogger(usage_config.path).log(record)


__all__ = ["UsageLogger", "UsageRecord", "log_call_usage"]
