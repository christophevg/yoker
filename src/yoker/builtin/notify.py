"""Notify tool implementation for Yoker.

Provides the ``notify`` async function for triggering macOS notifications.
Useful for alerting the user when the agent is waiting for input or has
completed a long-running task.
"""

import asyncio
import platform

from structlog import get_logger

from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

MAX_MESSAGE_LENGTH = 500
MAX_TITLE_LENGTH = 100
MAX_SUBTITLE_LENGTH = 100


async def notify(
  message: str,
  title: str = "Yoker",
  subtitle: str = "",
) -> ToolResult:
  """Send a macOS notification to alert the user.

  Triggers a native macOS notification using ``osascript``. Useful when
  the agent is waiting for user input or has completed a long-running task.

  On non-macOS platforms, the notification is logged but no system
  notification is shown — the tool still returns success.

  Args:
    message: The notification body text (max 500 characters).
    title: The notification title (max 100 characters, default "Yoker").
    subtitle: Optional subtitle shown below the title (max 100 characters).

  Returns:
    ToolResult confirming the notification was sent (or logged on non-macOS).
  """
  if not isinstance(message, str):
    return ToolResult(success=False, error="message must be a string")

  if not message.strip():
    return ToolResult(success=False, error="message cannot be empty")

  if len(message) > MAX_MESSAGE_LENGTH:
    return ToolResult(
      success=False,
      error=f"message exceeds {MAX_MESSAGE_LENGTH} characters",
    )

  if len(title) > MAX_TITLE_LENGTH:
    return ToolResult(
      success=False,
      error=f"title exceeds {MAX_TITLE_LENGTH} characters",
    )

  if len(subtitle) > MAX_SUBTITLE_LENGTH:
    return ToolResult(
      success=False,
      error=f"subtitle exceeds {MAX_SUBTITLE_LENGTH} characters",
    )

  if platform.system() != "Darwin":
    logger.info(
      "notify_non_macos",
      title=title,
      subtitle=subtitle,
      message=message,
    )
    return ToolResult(
      success=True,
      result={
        "sent": False,
        "platform": platform.system(),
        "message": f"Notification logged (no native support on {platform.system()})",
      },
    )

  # Build the AppleScript display notification command.
  # Escape double quotes in all string components to prevent script injection.
  safe_message = message.replace('"', '\\"')
  safe_title = title.replace('"', '\\"')
  safe_subtitle = subtitle.replace('"', '\\"')

  script = f'display notification "{safe_message}"'
  if title:
    script += f' with title "{safe_title}"'
  if subtitle:
    script += f' subtitle "{safe_subtitle}"'

  logger.info("notify_send", title=title, subtitle=subtitle, message=message)

  try:
    proc = await asyncio.create_subprocess_exec(
      "osascript",
      "-e",
      script,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
      error_msg = stderr.decode().strip() if stderr else "unknown error"
      logger.warning("notify_osascript_failed", error=error_msg, returncode=proc.returncode)
      return ToolResult(
        success=False,
        error=f"osascript failed: {error_msg}",
      )
  except FileNotFoundError:
    logger.warning("notify_osascript_not_found")
    return ToolResult(
      success=False,
      error="osascript not found — this tool requires macOS",
    )
  except Exception as e:
    logger.error("notify_error", error=str(e))
    return ToolResult(success=False, error=f"Failed to send notification: {e}")

  logger.info("notify_sent", title=title, subtitle=subtitle, message=message)
  return ToolResult(
    success=True,
    result={
      "sent": True,
      "title": title,
      "subtitle": subtitle or None,
      "message": message,
    },
  )


__all__ = ["notify"]
