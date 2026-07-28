"""Interactive UI handler implementation.

Uses prompt_toolkit for input and Rich for append-only output. The
``PromptSession`` is created lazily on first ``get_input`` /
``get_secret_input`` / ``confirm_approval`` call so that construction never
requires a TTY (the bootstrap wizard and scripted flows can drive a handler
without ever prompting). A single ``rich.status.Status`` line provides
"Processing..." feedback during the latency between stream start and the
first chunk; it is replaced (not Live-managed) as soon as real output
arrives.
"""

from __future__ import annotations

import asyncio
import traceback
from functools import partial
from pathlib import Path
from typing import Any

from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from pyfiglet import Figlet
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.style import Style

from yoker import __version__
from yoker.core import Agent
from yoker.exceptions import NetworkError, ToolError
from yoker.ui.handler import UIHandler

# Styles for console output
PROMPT_STYLE = Style(color="black", bgcolor="grey93")
THINKING_STYLE = Style(color="grey66")
CONTENT_STYLE = Style(color="black")
TOOL_STYLE = Style(color="cyan")
TOOL_RESULT_STYLE = Style(color="bright_black")
STATS_STYLE = Style(color="bright_blue", dim=True)
ERROR_STYLE = Style(color="red", bold=True)
STEP_TITLE_STYLE = Style(bold=True, underline=True)

# Inline tool-arg display caps.
_TOOL_ARG_MAX_CHARS = 60
_TOOL_LARGE_FIELDS = ("content", "old_string", "new_string")
_TOOL_SUPPRESS_LARGE_FIELDS = ("write", "update")
_BANNER_TOOL_LIMIT = 8


class InteractiveUIHandler(UIHandler):
  """Interactive UI with lazy prompt_toolkit input and Rich append-only output.

  Features:
    - Lazy ``PromptSession`` (not created in ``__init__``)
    - Multiline input (Esc+Enter for newline)
    - Command history persisted to file (or in-memory when disabled)
    - Rich console formatting with append-only ``console.print``
    - Single ``Status`` line for "Processing..." feedback, replaced on first
      chunk (no Live region, no spinner state flags)
  """

  def __init__(
    self,
    history_file: Path | None | str = None,
    show_thinking: bool = True,
    show_tool_calls: bool = True,
    show_stats: bool = True,
    show_time: bool = False,
    console: Console | None = None,
  ) -> None:
    """Initialize the interactive UI handler.

    Args:
      history_file: Path to command history file. Pass None to use the
        default path (~/.yoker_history). Pass a Path object or the string
        "none" to explicitly disable persistent history (uses in-memory
        history only). Use history_file="none" for bootstrap wizard and
        other non-conversational flows to avoid logging sensitive data
        like API keys.
      show_thinking: Whether to display thinking output.
      show_tool_calls: Whether to display tool call info.
      show_stats: Whether to display turn statistics.
      show_time: Whether to display timing info (reserved; banner always
        shows duration via output_stats when show_stats is True).
      console: Optional Rich console (default: new Console).
    """
    self.console = console if console is not None else Console()
    # If history_file is None, use default path. If it's a Path or string
    # "none", use that (allows explicit opt-out of persistent history).
    self.history_file: Path | None
    if history_file is None:
      self.history_file = Path.home() / ".yoker_history"
    elif history_file == "none":
      self.history_file = None
    elif isinstance(history_file, Path):
      self.history_file = history_file
    else:
      # history_file is a string that's not "none", treat as path
      self.history_file = Path(history_file)
    self.show_thinking = show_thinking
    self.show_tool_calls = show_tool_calls
    self.show_stats = show_stats
    self.show_time = show_time

    # Lazy prompt session — created on first input/approval call.
    self._session: PromptSession[str] | None = None

    # Single "Processing..." status line, replaced on first chunk.
    self._processing_status: Status | None = None

    # Optional predefined input source for scripted/demo usage.
    self._input_source: list[str] | None = None
    self._input_index = 0

  def set_input_messages(self, messages: list[str]) -> None:
    """Set predefined input messages for scripted sessions.

    When set, get_input returns these messages sequentially instead of
    reading from the terminal. This does NOT create a PromptSession —
    scripted flows can run without a TTY.

    Args:
      messages: List of input messages to return sequentially.
    """
    self._input_source = messages
    self._input_index = 0

  def _get_or_create_session(self) -> PromptSession[str]:
    """Lazily create and cache the PromptSession.

    Called on first ``get_input`` / ``get_secret_input`` / ``confirm_approval``.
    Builds the session with KeyBindings, FileHistory/InMemoryHistory, and
    multiline Esc+Enter support. Only builds once.

    Returns:
      The cached ``PromptSession`` instance.
    """
    if self._session is None:
      self._session = self._create_session()
    return self._session

  def _create_session(self) -> PromptSession[str]:
    """Create prompt session with multiline support.

    Returns:
      Configured PromptSession instance.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def _handle_enter(event: KeyPressEvent) -> None:
      event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _handle_meta_enter(event: KeyPressEvent) -> None:
      event.current_buffer.insert_text("\n")

    # In-memory history when history_file is None (e.g., bootstrap wizard)
    # to avoid persisting sensitive data like API keys to disk.
    history: History
    if self.history_file is None:
      history = InMemoryHistory()
    else:
      self.history_file.parent.mkdir(parents=True, exist_ok=True)
      history = FileHistory(str(self.history_file))

    return PromptSession(
      history=history,
      multiline=True,
      mouse_support=False,
      key_bindings=kb,
    )

  # === Processing feedback ===

  def _start_processing_status(self) -> None:
    """Start the single "Processing..." status line if not already active."""
    if self._processing_status is None:
      self._processing_status = self.console.status("Processing...", spinner="dots")
      self._processing_status.start()

  def _stop_processing_status(self) -> None:
    """Stop the "Processing..." status line if active."""
    if self._processing_status is not None:
      self._processing_status.stop()
      self._processing_status = None

  def start_processing(self) -> None:
    """Start the "Processing..." status spinner.

    Called by the bridge on TURN_START and after each TOOL_RESULT to
    indicate the model is working. The spinner is stopped before any
    output is rendered.
    """
    self._start_processing_status()

  def stop_processing(self) -> None:
    """Stop the "Processing..." status spinner if active."""
    self._stop_processing_status()

  # === Lifecycle ===

  async def start(
    self,
    agent: Agent,
    *,
    title: str = "Yoker",
    version: str | None = None,
    **_kwargs: Any,
  ) -> None:
    """Start interactive UI session.

    Args:
      agent: The Agent instance this UI session is serving.
      title: Banner title (defaults to "Yoker").
      version: Banner version (defaults to ``yoker.__version__``).
      **_kwargs: Ignored (backward compatibility for external callers).
    """
    if version is None:
      version = __version__
    banner = str(Figlet(font="standard").renderText(title)).rstrip()
    banner = f"[blue bold]{banner} {version}[/blue bold]"

    harness = agent.config.harness
    harness_line = f"[blue]Harness[/blue]: {harness.name}"
    if harness.version:
      harness_line += f" v{harness.version}"
    if harness.author:
      harness_line += f" by {harness.author}"

    motd_lines = banner.split("\n") + [
      f"[blue]Model[/blue]: {agent.model} (provider: {agent.config.backend.provider})",
      harness_line,
      f"[blue]Thinking[/blue]: {agent.thinking_mode.value} (use /think on|off|silent to toggle)",
      f"[blue]Agent[/blue]: {agent.definition.name}",
      f"[dim]{agent.definition.description.strip()}[/dim]",
    ]
    if agent.definition.source_path:
      motd_lines.append(f"[blue]Source[/blue]: {agent.definition.source_path}")

    if agent.tools:
      tool_names = list(agent.tools.keys())
      if len(tool_names) > _BANNER_TOOL_LIMIT:
        shown = ", ".join(tool_names[:_BANNER_TOOL_LIMIT])
        extra = len(tool_names) - _BANNER_TOOL_LIMIT
        motd_lines.append(f"[blue]Tools[/blue]: {shown} +{extra} more (use /tools for full list)")
      else:
        motd_lines.append(f"[blue]Tools[/blue]: {', '.join(tool_names)}")

    motd_lines.append("[dim]Type /help for available commands.")
    motd_lines.append("Press Ctrl+D (or Ctrl+Z on Windows) to quit.[/dim]")

    self.console.print(Panel("\n".join(motd_lines), title="👋 Welcome..."))
    self.console.print()

  async def shutdown(self, reason: str) -> None:
    """End interactive UI session.

    Args:
      reason: Reason for ending ("quit", "error", "interrupt").
    """
    self._stop_processing_status()
    self.console.print("\nGoodbye!")

  # === Input ===

  async def get_input(self, prompt: str = "> ") -> str | None:
    """Get user input from prompt_toolkit or predefined source.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF) or interrupt.
    """
    if self._input_source is not None:
      if self._input_index >= len(self._input_source):
        return None
      message = self._input_source[self._input_index]
      self._input_index += 1
      if message:
        self.output_prompt(message)
      return message

    session = self._get_or_create_session()
    # erase_when_done is a PromptSession/Application constructor flag, not
    # a prompt() kwarg. Toggle it on the cached session's app for this call
    # only, so the input line is erased after Enter and output_prompt can
    # render the input in a styled Panel. Reset afterwards so confirm_approval
    # (which shares this session) keeps its y/N audit trail. The finally
    # block guarantees the flag is reset on ANY exception path (including
    # unexpected ones like NoConsoleScreenBufferError).
    session.app.erase_when_done = True
    try:
      result: str = await asyncio.to_thread(session.prompt, prompt)
    except EOFError:
      return None
    except KeyboardInterrupt:
      self.console.print()  # Newline after ^C
      return None
    finally:
      session.app.erase_when_done = False
    if result:
      self.output_prompt(result)
    return result

  async def get_secret_input(self, prompt: str = "> ") -> str | None:
    """Get secret user input (masked) from prompt_toolkit.

    The typed characters are masked (prompt_toolkit ``is_password=True``).
    The value is never echoed or logged. Uses the predefined input source
    when one is set (for scripted/demo usage), same as :meth:`get_input`.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF) or interrupt.
    """
    if self._input_source is not None:
      if self._input_index >= len(self._input_source):
        return None
      message = self._input_source[self._input_index]
      self._input_index += 1
      return message

    session = self._get_or_create_session()
    # See get_input: erase_when_done is toggled on the cached session's app
    # for this call only. Secrets are not echoed via output_prompt. The
    # finally block also resets is_password (a session-level flag set
    # below) so a subsequent regular get_input call is not masked, even on
    # interrupt paths.
    session.app.erase_when_done = True
    session.is_password = True
    try:
      result: str = await asyncio.to_thread(partial(session.prompt, prompt, is_password=True))
    except EOFError:
      return None
    except KeyboardInterrupt:
      self.console.print()
      return None
    finally:
      session.app.erase_when_done = False
      session.is_password = False
    return result

  # === Prompt echo ===

  def output_prompt(self, text: str) -> None:
    """Render the user's submitted input as a styled Panel.

    Empty input is skipped (no Panel rendered).

    Args:
      text: The submitted input text.
    """
    if not text:
      return
    self.console.print()
    self.console.print(Panel(text, style=PROMPT_STYLE, box=box.SIMPLE_HEAD))

  # === Info / step / command output ===

  def output_info(self, text: str) -> None:
    """Output a discrete informational text block.

    Args:
      text: Informational text (may contain newlines).
    """
    self._stop_processing_status()
    self.console.print(text)

  async def output_step_title(self, step: int, total: int, title: str) -> None:
    """Output a wizard step title with emphasis (bold + underline).

    A leading blank line is emitted before the title for every step after
    the first (``step > 1``) so consecutive steps are visually separated.

    Args:
      step: 1-based step index.
      total: Total number of steps in the wizard flow.
      title: Human-readable step title.
    """
    self._stop_processing_status()
    if step > 1:
      self.console.print()
    self.console.print(f"Step {step} of {total}: {title}", style=STEP_TITLE_STYLE)

  def output_command_result(self, result: str) -> None:
    """Output slash-command result text.

    Args:
      result: Command output text.
    """
    self._stop_processing_status()
    self.console.print(f"{result}\n")

  def output_content(self, content: str, content_type: str = "text/plain") -> None:
    """Output content text directly (non-streaming).

    Args:
      content: Content text (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    self.start_content_stream()
    self.stream_content(content, content_type)
    self.end_content_stream(len(content))

  def output_thinking(self, text: str) -> None:
    """Output thinking text directly (non-streaming).

    Args:
      text: Thinking text.
    """
    self.start_thinking_stream()
    self.stream_thinking(text)
    self.end_thinking_stream(len(text))

  # === Content Output ===

  def start_content_stream(self) -> None:
    """Start streaming content."""
    self._stop_processing_status()
    self.console.print("⏺ ", end="", style=CONTENT_STYLE)

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream a content chunk.

    Args:
      chunk: Content chunk (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    self._stop_processing_status()
    self.console.print(chunk, end="", style=CONTENT_STYLE)

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    self._stop_processing_status()
    self.console.print()  # final newline

  # === Thinking Output ===

  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    if not self.show_thinking:
      return
    self._stop_processing_status()
    self.console.print("⏺ ", end="", style=THINKING_STYLE)

  def stream_thinking(self, chunk: str) -> None:
    """Stream a thinking chunk.

    Args:
      chunk: Thinking chunk (may contain ANSI from LLM).
    """
    if not self.show_thinking:
      return
    self._stop_processing_status()
    self.console.print(chunk, style=THINKING_STYLE, end="")

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    if not self.show_thinking:
      return
    self._stop_processing_status()
    self.console.print()

  # === Multi-agent lifecycle ===

  def agent_spawned(self, name: str) -> None:
    """Surface that a sub-agent has been spawned into the session.

    Args:
      name: The session-assigned id of the spawned agent.
    """
    self._stop_processing_status()
    self.console.print(f"[cyan]↳ Agent spawned:[/cyan] {name}")

  def agent_finished(self, name: str) -> None:
    """Surface that a sub-agent has finished and been removed.

    Args:
      name: The session-assigned id of the finished agent.
    """
    self._stop_processing_status()
    self.console.print(f"[dim]↳ Agent finished:[/dim] {name}")

  # === Protected-file approval (MBI-009 T12) ===

  async def confirm_approval(self, path: str, diff: str) -> bool:
    """Ask the user to approve a write to a protected file.

    Renders the unified diff with the colored diff renderer, then prompts
    y/N. An empty response (Enter) or EOF counts as denial (fail-safe).
    ``Ctrl+C`` is caught and treated as denial so the turn resumes instead
    of crashing the session. The y/N prompt is NOT erased after submit
    (audit trail); uses the lazy session.

    Args:
      path: Path being written/updated (displayed in the prompt).
      diff: Unified diff string between current and proposed content.

    Returns:
      True if the user explicitly approved, False otherwise.
    """
    self._stop_processing_status()
    filename = Path(path).name
    self.console.print(
      Panel(
        f"Agent wants to modify [bold]{path}[/bold]",
        title="Protected file",
        style=TOOL_STYLE,
      )
    )
    # Reuse the colored diff renderer. Synthesize a minimal metadata dict
    # so _show_diff_content's truncation branch is not triggered.
    self._show_diff_content(diff, filename, "approve", metadata={})
    session = self._get_or_create_session()
    try:
      answer = await session.prompt_async(
        f"Approve write to {filename}? [y/N] ",
        is_password=False,
      )
    except (EOFError, KeyboardInterrupt):
      self.console.print()
      return False
    return answer.strip().lower() in ("y", "yes")

  # === Tool Output ===

  def output_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
    """Output tool call information.

    Renders inline as ``⏺ name(key=value, ...)`` with all key=value pairs
    shown. Multi-line or long (>60 chars) values are summarized as
    ``N chars``. For ``write``/``update`` tools, ``content`` /
    ``old_string`` / ``new_string`` are suppressed (the diff is shown
    separately via ``output_tool_content``).

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments (may be truncated for display).
    """
    if not self.show_tool_calls:
      return
    self._stop_processing_status()
    self.console.print(f"⏺ {tool_name}", end="", style=TOOL_STYLE)
    details = self._format_tool_details(tool_name, args)
    self.console.print(f"({details})")

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Output tool result status.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
    """
    if not self.show_tool_calls:
      return
    self._stop_processing_status()
    if success:
      self.console.print("  [green]✓ Success[/green]", end="")
      self.console.print(f" ({len(result)} chars)", style=TOOL_RESULT_STYLE)
    else:
      self.console.print("  [red]𐄂 Fail[/red]")
      self._print_error(result if result else "Failed")

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict[str, Any],
  ) -> None:
    """Output tool content (file contents, diff, etc.).

    Args:
      tool_name: Name of tool.
      operation: Operation type (read, write, update, etc.).
      path: File path.
      content: Content text (may be None for summary).
      content_type: MIME type of content.
      metadata: Additional metadata (lines, bytes, etc.).
    """
    if not self.show_tool_calls:
      return
    self._stop_processing_status()
    filename = Path(path).name

    # Dispatch based on content_type
    if content_type == "application/x-summary":
      self._show_summary(operation, filename, metadata)
    elif content_type in ("diff", "text/x-diff"):
      self._show_diff_content(content, filename, operation, metadata)
    else:
      self._show_full_content(content, filename, operation, metadata)

  # === Stats Output ===

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
    """
    self._stop_processing_status()
    if self.show_stats:
      total = prompt_tokens + eval_tokens
      duration_s = duration_ms / 1000.0
      self.console.print(f"📊 {duration_s:.1f}s, {total} tokens", style=STATS_STYLE)

  # === Error Output ===

  def output_error(self, error: Exception, include_traceback: bool = False) -> None:
    """Output error message with Rich formatting.

    Args:
      error: Exception that occurred.
      include_traceback: Whether to include full traceback (default: False).
        For NetworkError, the debug message with exception chain is shown
        when this is True. For other errors, the full Python traceback is
        shown.
    """
    self._stop_processing_status()

    if isinstance(error, NetworkError):
      if error.recoverable:
        msg = f"{error.message}\n\nYour message was preserved. Try again or type a new message."
      else:
        msg = f"{error.message}\n\nUnable to recover. Please restart the session."
      debug_exc = error if include_traceback else None
      self._print_error(msg, debug_exc)
    elif isinstance(error, ToolError):
      msg = f"Tool Error ({error.tool_name}): {error}"
      self._print_error(msg, error if include_traceback else None)
    else:
      msg = f"Error: {error}"
      self._print_error(msg, error if include_traceback else None)

  # === Formatting Helpers ===

  def _print_error(self, msg: str, exc: Exception | None = None) -> None:
    if exc:
      if isinstance(exc, NetworkError):
        msg += f"\n\n[dim]{exc.get_debug_message()}[/dim]"
      else:
        tb = "".join(traceback.TracebackException.from_exception(exc).format())
        msg += "\n\n[black]" + tb

    self.console.print(Panel(msg, title="ERROR", style=ERROR_STYLE))
    self.console.print()

  def _format_tool_details(self, tool_name: str, arguments: dict[str, Any]) -> str:
    """Format tool arguments for inline display.

    Shows all ``key=value`` pairs. Multi-line or long (>60 chars) values are
    summarized as ``N chars``. For ``write``/``update`` tools,
    ``content``/``old_string``/``new_string`` are suppressed (the diff is
    shown separately).

    Args:
      tool_name: Name of the tool.
      arguments: Tool arguments dictionary.

    Returns:
      Formatted string showing relevant arguments.
    """
    # Special formatting for git tool: show operation, path, and args.
    if tool_name == "git":
      operation = arguments.get("operation", "")
      path = arguments.get("path", "")
      args = arguments.get("args", {})

      parts = [str(operation)] if operation else []
      if path:
        parts.append(f"on {path}")
      if args:
        args_str = ", ".join(f"{k}={v}" for k, v in list(args.items())[:2])
        if len(args) > 2:
          args_str += ", ..."
        parts.append(f"({args_str})")

      return " ".join(parts) if parts else str(arguments)

    # Special formatting for websearch: show query.
    if tool_name == "websearch":
      query = arguments.get("query", "")
      if query:
        return str(query)
      return str(arguments)

    # Suppress large content fields for write/update (diff shown separately).
    if tool_name in _TOOL_SUPPRESS_LARGE_FIELDS:
      arguments = {k: v for k, v in arguments.items() if k not in _TOOL_LARGE_FIELDS}

    def str_summary(value: Any) -> str:
      if isinstance(value, str):
        if "\n" in value or len(value) > _TOOL_ARG_MAX_CHARS:
          return f"{len(value)} chars"
        return value
      s = str(value)
      if len(s) > _TOOL_ARG_MAX_CHARS:
        return f"{len(s)} chars"
      return s

    return " ".join(key + "=" + str_summary(value) for key, value in arguments.items())

  def _show_summary(
    self,
    operation: str,
    filename: str,
    metadata: dict[str, Any],
  ) -> None:
    """Show operation summary.

    Args:
      operation: Operation type.
      filename: Basename of file.
      metadata: Summary metadata.
    """
    if operation == "write":
      lines = metadata.get("lines", 0)
      is_new_file = metadata.get("is_new_file", False)
      is_binary = metadata.get("is_binary", False)

      if is_binary:
        byte_size = metadata.get("bytes", 0)
        self.console.print(f"  {filename} ({byte_size // 1024} KB binary)")
      elif lines == 0:
        self.console.print(f"  {filename} (0 lines, empty)")
      elif is_new_file:
        self.console.print(f"  Creating new file {filename} ({lines} lines)")
      else:
        self.console.print(f"  Overwriting {filename} ({lines} lines)")

    elif operation in ("insert_before", "insert_after"):
      line_number = metadata.get("line_number", 0)
      inserted_lines = metadata.get("inserted_lines", 1)
      self.console.print(f"  Insert at line {line_number} in {filename}: {inserted_lines} line(s)")

    elif operation == "replace":
      self.console.print(f"  Replace in {filename}")

    elif operation == "delete":
      line_number = metadata.get("line_number")
      if line_number:
        self.console.print(f"  Delete line {line_number} in {filename}")
      else:
        self.console.print(f"  Delete in {filename}")

  def _show_full_content(
    self,
    content: str | None,
    filename: str,
    operation: str,
    metadata: dict[str, Any],
  ) -> None:
    """Show full content with line numbers.

    Args:
      content: Content text (may be None for summary fallback).
      filename: Basename of file.
      operation: Operation type.
      metadata: Additional metadata.
    """
    if content is None:
      self._show_summary(operation, filename, metadata)
      return

    self.console.print(f"\n  {filename}")

    lines = content.splitlines()
    for i, line in enumerate(lines, start=1):
      escaped_line = line.replace("[", "\\[").replace("]", "\\]")
      self.console.print(f"  {i:4d}│{escaped_line}")

    if metadata.get("truncated"):
      original_lines = metadata.get("original_line_count", 0)
      remaining = original_lines - len(lines)
      self.console.print(f"  ... ({remaining} more lines)")

  def _show_diff_content(
    self,
    content: str | None,
    filename: str,
    operation: str,
    metadata: dict[str, Any],
  ) -> None:
    """Show unified diff with colors.

    Args:
      content: Diff content text (may be None for summary fallback).
      filename: Basename of file.
      operation: Operation type.
      metadata: Additional metadata.
    """
    if content is None:
      self._show_summary(operation, filename, metadata)
      return

    self.console.print(f"  {filename}")

    lines = content.splitlines()
    for line in lines:
      if line.startswith("--- ") or line.startswith("+++ "):
        continue
      if line.startswith("diff --"):
        continue

      escaped_line = line.replace("[", "\\[").replace("]", "\\]")

      if line.startswith("@@"):
        self.console.print(f"  [cyan]{escaped_line}[/]")
      elif line.startswith("-"):
        self.console.print(f"  [red]{escaped_line}[/]")
      elif line.startswith("+"):
        self.console.print(f"  [green]{escaped_line}[/]")
      else:
        self.console.print(f"  {escaped_line}")

    if metadata.get("truncated"):
      original_lines = metadata.get("original_diff_lines", 0)
      remaining = original_lines - len(lines)
      self.console.print(f"  ... ({remaining} more lines)")
