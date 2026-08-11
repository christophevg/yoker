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
from time import localtime, strftime
from typing import Any

from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from pyfiglet import Figlet
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.status import Status
from rich.style import Style
from rich.text import Text
from rich.theme import Theme

from yoker import __version__
from yoker.config import ContentDisplayConfig
from yoker.core import Agent
from yoker.exceptions import NetworkError, ToolError
from yoker.markdown import MarkdownStreamer
from yoker.ui.formatting import format_tool_args, truncate_content_preview
from yoker.ui.handler import UIHandler

# Styles for console output
PROMPT_STYLE = Style(color="black", bgcolor="grey93")
THINKING_STYLE = Style(color="grey66")
RESPONSE_STYLE = Style(color="black")
TOOL_STYLE = Style(color="cyan")
TOOL_RESULT_STYLE = Style(color="bright_black")
STATS_STYLE = Style(color="bright_blue", dim=True)
ERROR_STYLE = Style(color="red", bold=True)
STEP_TITLE_STYLE = Style(bold=True, underline=True)

RESPONSE_THEME = Theme({"markdown.code": Style(color="dodger_blue1")})

THINKING_THEME = Theme(
  {
    "markdown.code": "bold",
    "markdown.code_block": "none",
    "markdown.block_quote": "none",
    "markdown.list": "none",
    "markdown.item.number": "none",
    "markdown.h2": "underline",
    "markdown.h3": "bold",
    "markdown.h4": "italic",
    "markdown.link": "underline",
    "markdown.link_url": "underline",
    "markdown.table.border": "none",
    "markdown.table.header": "bold",
    "markdown.kbd": "bold",
  }
)


_BANNER_TOOL_LIMIT = 8

BULLET = "⏺ "


def _extract_usage_pct(limits: dict[str, Any], period: str) -> float | None:
  """Extract the usage percentage for a given period from usage limits.

  Args:
    limits: The ``limits`` dict from the Ollama usage API.
    period: The period key — ``"session"`` or ``"weekly"``.

  Returns:
    Usage as a 0–1 float, or None when unavailable.
  """
  entry = limits.get(period)
  if not isinstance(entry, dict):
    return None
  usage = entry.get("usage")
  if not isinstance(usage, int | float):
    return None
  return float(usage)


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
    show_time: bool = True,
    console: Console | None = None,
    content_display: ContentDisplayConfig | None = None,
    show_spinners: bool = True,
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
      show_time: Whether to display timing info
      console: Optional Rich console (default: new Console).
      content_display: Content display config for argument rendering and
        content preview truncation. Defaults to ``ContentDisplayConfig()``.
      show_spinners: Whether to display Rich status spinners ("Processing..."
        and tool-execution feedback). Set to False for scripted/recording
        scenarios where the spinner output interferes with captured output.
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
    self._content_display = (
      content_display if content_display is not None else ContentDisplayConfig()
    )

    # When False, suppress Rich status spinners (for scripted/recording use).
    self._show_spinners = show_spinners

    # Lazy prompt session — created on first input/approval call.
    self._session: PromptSession[str] | None = None

    # Single "Processing..." status line, replaced on first chunk.
    self._processing_status: Status | None = None
    # Tool-execution spinner — started after tool call is rendered,
    # stopped when the tool result arrives.
    self._tool_execution_status: Status | None = None

    # Optional predefined input source for scripted/demo usage.
    self._input_source: list[str] | None = None
    self._input_index = 0

    # Session id for the resume hint printed on shutdown.
    self._session_id: str | None = None

    # setup markdown streamers (consoles created lazily to use the handler's console)
    self._thinking_streamer: MarkdownStreamer | None = None
    self._response_streamer: MarkdownStreamer | None = None

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
    if not self._show_spinners:
      return
    if self._processing_status is None:
      self._processing_status = self.console.status("Processing...", spinner="dots")
      self._processing_status.start()

  def _stop_processing_status(self) -> None:
    """Stop the "Processing..." status line if active."""
    if self._processing_status is not None:
      self._processing_status.stop()
      self._processing_status = None

  def _start_tool_execution_status(self, tool_name: str) -> None:
    """Start a spinner indicating a tool is executing."""
    if not self._show_spinners:
      return
    # Stop any existing processing or tool-execution spinner first.
    self._stop_processing_status()
    self._stop_tool_execution_status()
    self._tool_execution_status = self.console.status(f"Running {tool_name}...", spinner="dots")
    self._tool_execution_status.start()

  def _stop_tool_execution_status(self) -> None:
    """Stop the tool-execution spinner if active."""
    if self._tool_execution_status is not None:
      self._tool_execution_status.stop()
      self._tool_execution_status = None

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
    title: str | None = None,
    version: str | None = None,
    **_kwargs: Any,
  ) -> None:
    """Start interactive UI session.

    Args:
      agent: The Agent instance this UI session is serving.
      title: Banner title
      version: Banner version (defaults to Yoker's __version)
      **_kwargs: Ignored (backward compatibility for external callers).
    """
    version = version or agent.config.motd.version or __version__
    title = title or agent.config.motd.title or "Yoker"
    font = agent.config.motd.font or "standard"
    banner = str(Figlet(font=font).renderText(title)).rstrip()
    max_width = self.console.width - 4
    banner = "\n".join([line[:max_width] for line in banner.split("\n")])
    banner = f"[blue bold]{banner} {version}[/blue bold]"

    harness = agent.config.harness
    harness_line = f"[blue]Harness[/blue]: {harness.name}"
    if harness.version:
      harness_line += f" v{harness.version}"
    if harness.author:
      harness_line += f" by {harness.author}"

    # Session id is stamped onto config.context.session_id by Session.__init__.
    # Show "resumed" when the session was loaded from disk (fresh=False),
    # otherwise "started" (fresh=True or auto-generated).
    session_id = agent.config.context.session_id
    self._session_id = session_id
    is_resume = not agent.config.context.fresh and session_id != "auto"
    session_label = "Resumed" if is_resume else "Started"
    motd_lines = banner.split("\n") + [
      f"[blue]Model[/blue]: {agent.model} (provider: {agent.config.backend.provider})",
      harness_line,
      f"[blue]Session[/blue]: {session_label} '{session_id}'",
      f"[blue]Agent[/blue]: {agent.definition.name}",
      f"[dim italic]{agent.definition.description.strip()}[/dim italic]",
    ]
    if agent.definition.source_path:
      source_path = agent.definition.source_path
      if len(source_path) > self.console.width - len(" Source: "):
        showing = int((self.console.width - len("...") - len(" Source: ") - 2) / 2)
        source_path = source_path[:showing] + "..." + source_path[-showing:]
      motd_lines.append(f"[blue]Source[/blue]: {source_path}")

    if agent.tools:
      tool_names = [name.split(":", 1)[1] if ":" in name else name for name in agent.tools.keys()]
      if len(tool_names) > _BANNER_TOOL_LIMIT:
        shown = ", ".join(tool_names[:_BANNER_TOOL_LIMIT])
        extra = len(tool_names) - _BANNER_TOOL_LIMIT
        motd_lines.append(f"[blue]Tools[/blue]: {shown} +{extra} more (use /tools for full list)")
      else:
        motd_lines.append(f"[blue]Tools[/blue]: {', '.join(tool_names)}")

    if agent.skills:
      skill_names = [name.split(":", 1)[1] if ":" in name else name for name in agent.skills.keys()]
      if len(skill_names) > _BANNER_TOOL_LIMIT:
        shown = ", ".join(skill_names[:_BANNER_TOOL_LIMIT])
        extra = len(skill_names) - _BANNER_TOOL_LIMIT
        motd_lines.append(f"[blue]Skills[/blue]: {shown} +{extra} more (use /skills for full list)")
      else:
        motd_lines.append(f"[blue]Skills[/blue]: {', '.join(skill_names)}")

    motd_lines.append(
      f"[blue]Thinking[/blue]: {agent.thinking_mode.value} (use /think on|off|silent to toggle)"
    )
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
    if self._session_id and self._session_id != "auto":
      self.console.print(f"[dim]Resume this session with:[/dim] yoker --resume {self._session_id}")

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
    escaped = text.replace("[", "\\[").replace("]", "\\]")
    self.console.print(Panel(escaped, style=PROMPT_STYLE, box=box.SIMPLE_HEAD))

  # === Info / step / command output ===

  def output_info(self, text: str) -> None:
    """Output a discrete informational text block.

    Args:
      text: Informational text (may contain newlines).
    """
    self._stop_processing_status()
    self.console.print(text, markup=False)

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
    self.console.print(result, markup=False)
    self.console.print()

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
    self._stop_tool_execution_status()
    self._stop_processing_status()
    self.response_streamer.append(f"{BULLET}{self._ts()}")

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream a content chunk.

    Args:
      chunk: Content chunk (may contain ANSI from LLM).
      content_type: MIME type of content. (Should be Markdown? ;-))
    """
    self._stop_processing_status()
    self.response_streamer.append(chunk)

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    self._stop_processing_status()
    self.response_streamer.flush()
    self.console.print()  # final newline

  # === Thinking Output ===

  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    if not self.show_thinking:
      return
    self._stop_tool_execution_status()
    self._stop_processing_status()
    self.thinking_streamer.append(f"{BULLET}{self._ts()}")

  def stream_thinking(self, chunk: str) -> None:
    """Stream a thinking chunk.

    Args:
      chunk: Thinking chunk (may contain ANSI from LLM).
    """
    if not self.show_thinking:
      return
    self._stop_processing_status()
    self.thinking_streamer.append(chunk)

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    if not self.show_thinking:
      return
    self._stop_processing_status()
    self.thinking_streamer.flush()
    self.console.print()

  # === Multi-agent lifecycle ===

  def agent_spawned(self, name: str) -> None:
    """Surface that a sub-agent has been spawned into the session.

    Args:
      name: The session-assigned id of the spawned agent.
    """
    self._stop_tool_execution_status()
    self._stop_processing_status()
    self.console.print(f"[cyan]↳ {self._ts()}Agent spawned:[/cyan] {name}")

  def agent_finished(self, name: str) -> None:
    """Surface that a sub-agent has finished and been removed.

    Args:
      name: The session-assigned id of the finished agent.
    """
    self._stop_tool_execution_status()
    self._stop_processing_status()
    self.console.print(f"[dim]↳ {self._ts()}Agent finished:[/dim] {name}")

  # === Protected-file / git-operation approval (MBI-009 T12) ===

  async def confirm_approval(self, label: str, preview: str, kind: str = "file") -> bool:
    """Ask the user to approve a protected operation.

    Renders a single Rich Panel containing the operation header and preview
    (unified diff for file writes, command preview for git operations) with
    colored diff lines, then prompts y/N below the panel.
    An empty response (Enter) or EOF counts as denial (fail-safe).
    ``Ctrl+C`` is caught and treated as denial so the turn resumes instead
    of crashing the session. The y/N prompt is NOT erased after submit
    (audit trail); uses the lazy session.

    Args:
      label: For ``kind="file"``, the file path being written/updated.
        For ``kind="git"``, the operation label (e.g. ``"git commit"``).
      preview: Unified diff (file) or command preview text (git).
      kind: Approval context — ``"file"`` or ``"git"``.

    Returns:
      True if the user explicitly approved, False otherwise.
    """
    self._stop_tool_execution_status()
    self._stop_processing_status()
    if kind == "git":
      title = "Git operation"
      prompt_label = label
      header_text = f"Agent wants to run [bold]{label}[/bold]"
    else:
      title = "Protected file"
      prompt_label = Path(label).name
      header_text = f"Agent wants to modify [bold]{label}[/bold]"
    # Build a single Panel containing the header and the preview content so
    # the user sees the full approval context as one visual unit.
    preview_renderable = self._build_preview_text(preview, prompt_label)
    self.console.print(
      Panel(
        Group(Text.from_markup(header_text), Text(""), preview_renderable),
        title=title,
        style=TOOL_STYLE,
      )
    )
    session = self._get_or_create_session()
    try:
      answer = await session.prompt_async(
        f"Approve {prompt_label}? [y/N] ",
        is_password=False,
      )
    except (EOFError, KeyboardInterrupt):
      self.console.print()
      return False
    return answer.strip().lower() in ("y", "yes")

  # === Tool Output ===

  def output_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
    """Output tool call information.

    Renders as a tool call line using the shared formatting module.
    When arguments are few and short, they appear inline as ``key=value``.
    When there are many keys or long/multi-line values, a multi-line
    indented block is rendered instead.

    After rendering the call line, starts a spinner indicating the tool
    is executing. The spinner is stopped by ``output_tool_result``.

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments (may be truncated for display).
    """
    if not self.show_tool_calls:
      return
    self._stop_processing_status()
    details = format_tool_args(tool_name, args, self._content_display)
    if "\n" in details:
      self.console.print(f"{BULLET}{self._ts()}{tool_name}(", style=TOOL_STYLE)
      for line in details.splitlines():
        self.console.print(f"    {line}", style=TOOL_STYLE)
      self.console.print("  )", style=TOOL_STYLE)
    else:
      self.console.print(f"{BULLET}{self._ts()}{tool_name}", end="", style=TOOL_STYLE)
      self.console.print(f"({details})")
    self._start_tool_execution_status(tool_name)

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Output tool result status.

    Stops the tool-execution spinner if active before rendering the result.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
    """
    if not self.show_tool_calls:
      return
    self._stop_tool_execution_status()
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
    self._stop_tool_execution_status()
    self._stop_processing_status()
    filename = Path(path).name
    if content_type == "application/x-summary":
      self._show_summary(operation, filename, metadata)
    elif content_type in ("diff", "text/x-diff"):
      self._show_diff_content(content, filename, operation, metadata)
    else:
      self._show_full_content(content, filename, operation, metadata)

  # === Stats Output ===

  def output_stats(
    self,
    duration_ms: int,
    prompt_tokens: int,
    eval_tokens: int,
    usage_limits: dict[str, Any] | None = None,
  ) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
      usage_limits: Optional backend API usage limits with session/weekly
        usage percentages.
    """
    self._stop_processing_status()
    if self.show_stats:
      total = prompt_tokens + eval_tokens
      duration_s = duration_ms / 1000.0
      parts = [f"📊 {self._ts()}{duration_s:.1f}s, {total} tokens"]
      if usage_limits:
        session_pct = _extract_usage_pct(usage_limits, "session")
        weekly_pct = _extract_usage_pct(usage_limits, "weekly")
        if session_pct is not None:
          parts.append(f"session {session_pct:.0%}")
        if weekly_pct is not None:
          parts.append(f"weekly {weekly_pct:.0%}")
      self.console.print(" | ".join(parts), style=STATS_STYLE)

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

  @property
  def thinking_streamer(self) -> MarkdownStreamer:
    if self._thinking_streamer is None:
      self._thinking_streamer = MarkdownStreamer(
        Console(theme=THINKING_THEME, file=self.console.file), THINKING_STYLE, "algol"
      )
    return self._thinking_streamer

  @property
  def response_streamer(self) -> MarkdownStreamer:
    if self._response_streamer is None:
      self._response_streamer = MarkdownStreamer(
        Console(theme=RESPONSE_THEME, file=self.console.file), RESPONSE_STYLE, "default"
      )
    return self._response_streamer

  def _ts(self) -> str:
    ts = strftime("%H:%M:%S", localtime())
    if self.show_time:
      return f"[{ts}] "
    return ""

  def _print_error(self, msg: str, exc: Exception | None = None) -> None:
    if exc:
      if isinstance(exc, NetworkError):
        msg += f"\n\n[dim]{exc.get_debug_message()}[/dim]"
      else:
        tb = "".join(traceback.TracebackException.from_exception(exc).format())
        msg += "\n\n[black]" + tb

    self.console.print(Panel(msg, title="ERROR", style=ERROR_STYLE))
    self.console.print()

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

    elif operation in ("insert", "append"):
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
    """Show full content with middle-collapse truncation.

    When the content exceeds ``max_content_lines``, a head/tail preview is
    shown with a marker in between.

    Args:
      content: Content text (may be None for summary fallback).
      filename: Basename of file.
      operation: Operation type.
      metadata: Additional metadata.
    """
    if content is None:
      self._show_summary(operation, filename, metadata)
      return

    cd = self._content_display
    previewed, was_truncated, total = truncate_content_preview(
      content, cd.max_content_lines, cd.preview_head_lines, cd.preview_tail_lines
    )

    if was_truncated:
      shown = cd.preview_head_lines + cd.preview_tail_lines
      self.console.print(f"\n  {filename}  ({total} lines, showing {shown} of {total})")
    else:
      self.console.print(f"\n  {filename}")

    for line in previewed.splitlines():
      escaped_line = line.replace("[", "\\[").replace("]", "\\]")
      if line.startswith("... ") and "lines hidden" in line:
        self.console.print(f"  [dim]{escaped_line}[/dim]")
      else:
        self.console.print(f"  {escaped_line}")

  def _build_preview_text(self, content: str | None, filename: str) -> Text:
    """Build a Rich Text renderable from preview content with diff coloring.

    Applies the same line-by-line coloring as ``_show_diff_content`` but
    returns a :class:`rich.text.Text` instead of printing directly, so the
    result can be composed inside a :class:`rich.panel.Panel`.

    Args:
      content: Preview text (unified diff for file writes, plain text for
        git operations). ``None`` produces a minimal placeholder.
      filename: Basename shown as a leading label line.

    Returns:
      A ``Text`` renderable with colored diff/preview lines.
    """
    text = Text()
    text.append(f"  {filename}\n")

    if content is None:
      return text

    for line in content.splitlines():
      if line.startswith("--- ") or line.startswith("+++ "):
        continue
      if line.startswith("diff --"):
        continue

      if line.startswith("@@"):
        text.append(f"  {line}\n", style="cyan")
      elif line.startswith("-"):
        text.append(f"  {line}\n", style="red")
      elif line.startswith("+"):
        text.append(f"  {line}\n", style="green")
      else:
        text.append(f"  {line}\n")

    return text

  def _show_diff_content(
    self,
    content: str | None,
    filename: str,
    operation: str,
    metadata: dict[str, Any],
  ) -> None:
    """Show unified diff with colors and middle-collapse truncation.

    When the diff exceeds ``max_diff_lines``, a head/tail preview is shown
    with a marker in between.

    Args:
      content: Diff content text (may be None for summary fallback).
      filename: Basename of file.
      operation: Operation type.
      metadata: Additional metadata.
    """
    if content is None:
      self._show_summary(operation, filename, metadata)
      return

    cd = self._content_display
    previewed, was_truncated, total = truncate_content_preview(
      content, cd.max_diff_lines, cd.preview_head_lines, cd.preview_tail_lines
    )

    if was_truncated:
      shown = cd.preview_head_lines + cd.preview_tail_lines
      self.console.print(f"  {filename}  (diff: {total} lines, showing {shown} of {total})")
    else:
      self.console.print(f"  {filename}")

    for line in previewed.splitlines():
      if line.startswith("--- ") or line.startswith("+++ "):
        continue
      if line.startswith("diff --"):
        continue

      escaped_line = line.replace("[", "\\[").replace("]", "\\]")

      if line.startswith("... ") and "lines hidden" in line:
        self.console.print(f"  [dim]{escaped_line}[/dim]")
      elif line.startswith("@@"):
        self.console.print(f"  [cyan]{escaped_line}[/]")
      elif line.startswith("-"):
        self.console.print(f"  [red]{escaped_line}[/]")
      elif line.startswith("+"):
        self.console.print(f"  [green]{escaped_line}[/]")
      else:
        self.console.print(f"  {escaped_line}")
