"""Sleep tool implementation for Yoker.

Provides the ``sleep`` async function for pausing agent execution for a
specified duration. Useful for waiting between polls (e.g. CI status checks).
"""

import asyncio

from structlog import get_logger

from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

MIN_SLEEP_SECONDS = 1
MAX_SLEEP_SECONDS = 300


async def sleep(
  seconds: int,
  reason: str = "",
) -> ToolResult:
  """Pause execution for the given number of seconds.

  Useful for waiting between polls (e.g. CI status checks, long-running
  external processes). The agent retains full conversation context after
  the sleep — no memory is lost.

  Args:
    seconds: Duration to sleep (1–300 seconds). Values above 300 are
      clamped to 300; values below 1 are rejected.
    reason: Optional note explaining why the wait is needed (for logging
      and observability).

  Returns:
    ToolResult confirming the sleep duration.
  """
  if not isinstance(seconds, int):
    return ToolResult(success=False, error="seconds must be an integer")

  if seconds < MIN_SLEEP_SECONDS:
    return ToolResult(
      success=False,
      error=f"seconds must be >= {MIN_SLEEP_SECONDS}",
    )

  clamped = False
  if seconds > MAX_SLEEP_SECONDS:
    seconds = MAX_SLEEP_SECONDS
    clamped = True

  logger.info("sleep_start", seconds=seconds, reason=reason, clamped=clamped)
  await asyncio.sleep(seconds)
  logger.info("sleep_done", seconds=seconds, reason=reason, clamped=clamped)

  return ToolResult(
    success=True,
    result={
      "slept_seconds": seconds,
      "reason": reason or None,
      "clamped": clamped,
    },
  )


__all__ = ["sleep"]
