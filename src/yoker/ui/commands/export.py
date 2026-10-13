"""/export command implementation in the UI layer.

Exports the agent's most recent assistant response to a file. Writing
assistant response text to disk is presentation-adjacent functionality and
therefore belongs in the UI layer, like the other slash-commands.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "Export the last response to a file (usage: /export [path])"


def _last_response(agent: "Agent") -> str | None:
  """Return the content of the agent's last assistant message, if any."""
  messages = agent.context.get_messages()
  last = next((m for m in reversed(messages) if m.get("role") == "assistant"), None)
  return last.get("content") if last else None


def _target_path(args: str) -> Path:
  """Return the export destination: the given path or a timestamped default.

  The default filename is timestamped so repeated exports never clobber
  each other.
  """
  if args.strip():
    return Path(args.strip())
  return Path.cwd() / f"yoker-response-{datetime.now():%H%M%S}.md"


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """Export the last assistant response to a file.

  Args:
    args: Optional target file path. When empty, a timestamped
      ``yoker-response-<HHMMSS>.md`` file is written to the current
      directory.
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Confirmation text naming the written file, or an error message when
    there is no response to export.
  """
  content = _last_response(agent)
  if content is None:
    return "Error: nothing to export — no assistant response in this conversation yet."

  path = _target_path(args)
  path.write_text(content, encoding="utf-8")
  return f"Exported last response to {path} ({len(content)} chars)"


def create_command() -> "Command":
  """Create the /export command.

  Returns:
    A Command object for /export.
  """
  from yoker.ui.commands.base import Command

  return Command(name="export", description=DESCRIPTION, handler=handle)
