"""Interactive UI handler implementation.

Uses prompt_toolkit for input and Rich for output. Supports streaming via
Live display, command history, and multiline input.
"""

from pathlib import Path
from typing import Any

from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.shortcuts import PromptSession
from rich.console import Console
from rich.style import Style

from yoker.ui.base import BaseUIHandler
from yoker.ui.spinner import LiveDisplay

# Styles for console output
THINKING_STYLE = Style(color="bright_black", dim=True)
TOOL_STYLE = Style(color="cyan")
ERROR_STYLE = Style(color="red", bold=True)


class InteractiveUIHandler(BaseUIHandler):
  """Interactive UI with prompt_toolkit input and Rich output.

  Features:
    - Multiline input (Esc+Enter for newline)
    - Command history persisted to file
    - Rich console formatting
    - Live streaming display for thinking and content
  """

  def __init__(
    self,
    history_file: Path | None = None,
    show_thinking: bool = True,
    show_tool_calls: bool = True,
    show_stats: bool = True,
    wrap_width: int | None = None,
  ) -> None:
    """Initialize the interactive UI handler.

    Args:
      history_file: Path to command history file.
      show_thinking: Whether to display thinking output.
      show_tool_calls: Whether to display tool call info.
      show_stats: Whether to display turn statistics.
      wrap_width: Optional width for wrapping streamed output.
    """
    super().__init__()
    self.console = Console()
    self.history_file = history_file or Path.home() / ".yoker_history"
    self.show_thinking = show_thinking
    self.show_tool_calls = show_tool_calls
    self.show_stats = show_stats
    self.wrap_width = wrap_width

    # Live display managed across streams within a turn
    self._live: LiveDisplay | None = None

    # Track display state for separators
    self._thinking_shown = False
    self._content_shown = False

    # Create prompt session with custom key bindings
    self._session = self._create_session()

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

    # Ensure history directory exists
    self.history_file.parent.mkdir(parents=True, exist_ok=True)

    return PromptSession(
      history=FileHistory(str(self.history_file)),
      multiline=True,
      mouse_support=False,
      key_bindings=kb,
    )

  def _ensure_live(self) -> None:
    """Create LiveDisplay if not already active."""
    if self._live is None:
      self._live = LiveDisplay(console=self.console)
      self._live.__enter__()
      self._live.start_spinner()

  def _exit_live(self) -> None:
    """Exit and clear the current LiveDisplay if active."""
    if self._live:
      self._live.stop_spinner()
      self._live.__exit__(None, None, None)
      self._live = None

  # === Lifecycle ===

  async def start(self, model: str, version: str, config: dict[str, Any]) -> None:
    """Start interactive UI session.

    Args:
      model: Model name being used.
      version: Yoker version.
      config: Configuration summary.
    """
    self.console.print(f"Yoker v{version} - Using model: {model}")
    thinking_status = "enabled" if config.get("thinking_enabled", True) else "disabled"
    self.console.print(f"Thinking mode: {thinking_status} (use /think on|off to toggle)")
    self.console.print("Type /help for available commands.")
    self.console.print("Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")

  async def shutdown(self, reason: str) -> None:
    """End interactive UI session.

    Args:
      reason: Reason for ending ("quit", "error", "interrupt").
    """
    self._exit_live()
    self.console.print("\nGoodbye!")

  # === Input ===

  async def get_input(self, prompt: str = "> ") -> str | None:
    """Get user input from prompt_toolkit.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF) or interrupt.
    """
    try:
      result: str = await self._session.prompt_async(prompt)
      return result
    except EOFError:
      return None
    except KeyboardInterrupt:
      self.console.print()  # Newline after ^C
      return None

  # === Content Output ===

  def start_content_stream(self) -> None:
    """Start streaming content."""
    self._streaming_content = True
    self._ensure_live()
    if self._thinking_shown and self._live:
      self._live.append_response("\n")
      self._thinking_shown = False

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream a content chunk.

    Args:
      chunk: Content chunk (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    if self._live:
      self._live.append_response(chunk)

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    self._streaming_content = False
    if self._live:
      self._live.stop_spinner()

  # === Thinking Output ===

  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    if not self.show_thinking:
      return
    self._streaming_thinking = True
    self._thinking_shown = True
    self._ensure_live()

  def stream_thinking(self, chunk: str) -> None:
    """Stream a thinking chunk.

    Args:
      chunk: Thinking chunk (may contain ANSI from LLM).
    """
    if not self.show_thinking:
      return
    if self._live:
      self._live.append_thinking(chunk)
    else:
      self.console.print(chunk, style=THINKING_STYLE, end="")

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    self._streaming_thinking = False
    if self.show_thinking and self._live:
      self._live.stop_spinner()

  # === Command Output ===

  def output_command_result(self, result: str) -> None:
    """Output command result.

    Args:
      result: Command output text.
    """
    self._exit_live()
    self.console.print(f"{result}\n")

  # === Tool Output ===

  def output_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
    """Output tool call information.

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments (may be truncated for display).
    """
    if not self.show_tool_calls:
      return

    self._content_shown = True
    self._exit_live()

    details = self._format_tool_details(tool_name, args)
    self.console.print(f"\n⏺ {self._capitalize(tool_name)} tool: {details}")

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Output tool result status.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
    """
    if not self.show_tool_calls:
      return

    if success:
      self.console.print("  ✓ Success")
    else:
      error_msg = result[:50] if result else "Failed"
      self.console.print(f"  ✗ {error_msg}")

    # Create LiveDisplay with spinner for subsequent processing
    self._ensure_live()

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

    self._exit_live()
    filename = Path(path).name

    # Dispatch based on content_type
    if content_type == "application/x-summary":
      self._show_summary(operation, filename, metadata)
    elif content_type in ("diff", "text/x-diff"):
      self._show_diff_content(content, filename, operation, metadata)
    else:
      self._show_full_content(content, filename, operation, metadata)

    # Create LiveDisplay with spinner for subsequent processing
    self._ensure_live()

  # === Stats Output ===

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
    """
    if self._live:
      self._exit_live()

    if self.show_stats:
      total_tokens = prompt_tokens + eval_tokens
      duration_s = duration_ms / 1000.0
      if duration_ms > 0 or total_tokens > 0:
        if total_tokens > 0:
          tokens_per_sec = total_tokens / duration_s if duration_s > 0 else 0
          stats = (
            f"⏱ {duration_s:.1f}s | {prompt_tokens}+{eval_tokens}={total_tokens} tokens | "
            f"{tokens_per_sec:.0f} tok/s"
          )
        else:
          stats = f"⏱ {duration_s:.1f}s"
        self.console.print(stats, style="dim")
      else:
        self.console.print()

    self._end_turn()
    self._thinking_shown = False
    self._content_shown = False

  # === Error Output ===

  def output_error(self, error: Exception) -> None:
    """Output error message with Rich formatting.

    Args:
      error: Exception that occurred.
    """
    self._exit_live()

    from yoker.exceptions import NetworkError, ToolError

    if isinstance(error, NetworkError):
      if error.recoverable:
        msg = (
          f"Network Error: {error}\nYour message was preserved. Try again or type a new message."
        )
      else:
        msg = f"Fatal Network Error: {error}\nUnable to recover. Please restart the session."
    elif isinstance(error, ToolError):
      msg = f"Tool Error ({error.tool_name}): {error}"
    else:
      msg = f"Error: {error}"

    self.console.print(msg, style=ERROR_STYLE)

  # === Tool Formatting Helpers ===

  @staticmethod
  def _capitalize(name: str) -> str:
    """Capitalize first letter of name for display.

    Args:
      name: Name to capitalize.

    Returns:
      Name with first letter capitalized.
    """
    if name:
      return name[0].upper() + name[1:]
    return name

  @staticmethod
  def _extract_filename(arguments: dict[str, Any]) -> str:
    """Extract filename from tool arguments.

    Args:
      arguments: Tool arguments dictionary.

    Returns:
      Filename (basename) of the path argument, or first arg value if no path.
    """
    # Special case: git tool shows operation, not path
    if "operation" in arguments:
      return str(arguments["operation"])

    # Look for common path argument names
    for key in ("file_path", "path", "filepath"):
      if key in arguments:
        return Path(arguments[key]).name

    # Fallback: use first argument value
    if arguments:
      first_value = next(iter(arguments.values()))
      return str(first_value)

    return ""

  def _format_tool_details(self, tool_name: str, arguments: dict[str, Any]) -> str:
    """Format tool arguments for display.

    Args:
      tool_name: Name of the tool.
      arguments: Tool arguments dictionary.

    Returns:
      Formatted string showing relevant arguments.
    """
    # Special formatting for git tool: show operation, path, and args
    if tool_name == "git":
      operation = arguments.get("operation", "")
      path = arguments.get("path", "")
      args = arguments.get("args", {})

      # Build details string
      parts = [str(operation)] if operation else []
      if path:
        parts.append(f"on {path}")
      if args:
        # Show key args (first 2 to keep it concise)
        args_str = ", ".join(f"{k}={v}" for k, v in list(args.items())[:2])
        if len(args) > 2:
          args_str += ", ..."
        parts.append(f"({args_str})")

      return " ".join(parts) if parts else str(arguments)

    # Special formatting for web_search: show query
    if tool_name == "web_search":
      query = arguments.get("query", "")
      if query:
        return str(query)
      return str(arguments)

    # For other tools: show filename/path
    return self._extract_filename(arguments)

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
      # Fall back to summary
      self._show_summary(operation, filename, metadata)
      return

    # Show header
    self.console.print(f"\n  {filename}")

    # Show content with line numbers
    lines = content.splitlines()
    for i, line in enumerate(lines, start=1):
      # Escape brackets in user content to prevent Rich markup
      escaped_line = line.replace("[", "\\[").replace("]", "\\]")
      self.console.print(f"  {i:4d}│{escaped_line}")

    # Show truncation indicator if needed
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
      # Fall back to summary
      self._show_summary(operation, filename, metadata)
      return

    # Show header
    self.console.print(f"  {filename}")

    # Show diff with colors (using Rich styles)
    lines = content.splitlines()
    for line in lines:
      # Skip file header lines
      if line.startswith("--- ") or line.startswith("+++ "):
        continue
      # Skip diff header
      if line.startswith("diff --"):
        continue

      # Escape brackets in user content
      escaped_line = line.replace("[", "\\[").replace("]", "\\]")

      # Color based on prefix (using Rich styles)
      if line.startswith("@@"):
        self.console.print(f"  [cyan]{escaped_line}[/]")
      elif line.startswith("-"):
        self.console.print(f"  [red]{escaped_line}[/]")
      elif line.startswith("+"):
        self.console.print(f"  [green]{escaped_line}[/]")
      else:
        self.console.print(f"  {escaped_line}")

    # Show truncation indicator if needed
    if metadata.get("truncated"):
      original_lines = metadata.get("original_diff_lines", 0)
      remaining = original_lines - len(lines)
      self.console.print(f"  ... ({remaining} more lines)")

  def _print_wrapped(
    self,
    text: str,
    style: Style | None = None,
    end: str = "",
  ) -> None:
    """Print text with optional wrapping at wrap_width.

    Args:
      text: Text to print.
      style: Optional Rich style.
      end: String to append at the end (default: "").
    """
    if self.wrap_width is None:
      self.console.print(text, style=style, end=end)
      return

    # Track current position in line
    current_line: list[str] = []
    column = 0

    def flush_line() -> None:
      """Print current line and reset."""
      nonlocal current_line, column
      if current_line:
        self.console.print("".join(current_line), style=style, end="")
        current_line = []
        column = 0

    for char in text:
      if char == "\n":
        flush_line()
        self.console.print(style=style)
        column = 0
      elif char == "\r":
        flush_line()
        column = 0
      elif char == " ":
        # Space: check if adding it would exceed width
        if column + 1 > self.wrap_width:
          # Line break at word boundary
          flush_line()
          self.console.print(style=style)
          column = 0
        else:
          current_line.append(char)
          column += 1
      else:
        # Regular character
        if column >= self.wrap_width:
          # Break before this character if line is full
          flush_line()
          self.console.print(style=style)
          column = 0
        current_line.append(char)
        column += 1

    # Flush remaining content
    flush_line()

    if end:
      self.console.print(end, style=style, end="")
