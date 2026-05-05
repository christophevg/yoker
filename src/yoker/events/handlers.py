"""Event handlers for the Yoker event system."""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rich.console import Console
from rich.style import Style

from yoker.events.spinner import LiveDisplay
from yoker.events.types import (
  CommandEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  ErrorEvent,
  Event,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolContentEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)

# Styles for console output
THINKING_STYLE = Style(color="bright_black", dim=True)
ERROR_STYLE = Style(color="red", bold=True)
TOOL_STYLE = Style(color="cyan")


@runtime_checkable
class EventHandler(Protocol):
  """Protocol for event handlers."""

  def __call__(self, event: Event) -> None:
    """Handle an event."""
    ...


class ConsoleEventHandler:
  """Handles events by rendering to Rich console."""

  def __init__(
    self,
    console: Console | None = None,
    show_thinking: bool = True,
    show_tool_calls: bool = True,
    wrap_width: int | None = None,
    version: str = "0.1.0",
  ) -> None:
    """Initialize the console handler.

    Args:
      console: Rich console (default: new Console).
      show_thinking: Whether to display thinking output.
      show_tool_calls: Whether to display tool call info.
      wrap_width: Optional width for wrapping streaming output.
      version: Version string to display in session start.
    """
    self.console = console if console is not None else Console()
    self.show_thinking = show_thinking
    self.show_tool_calls = show_tool_calls
    self.wrap_width = wrap_width
    self.version = version

    # Live display - managed internally, not passed from outside
    self._live_display: LiveDisplay | None = None

    # State for wrapping and thinking tracking
    self._column = 0
    self._thinking_shown = False  # Track if thinking was displayed
    self._content_shown = False  # Track if any content was shown this turn

  def __call__(self, event: Event) -> None:
    """Handle an event by dispatching to the appropriate handler method."""
    match event.type:
      case EventType.SESSION_START:
        self._handle_session_start(event)  # type: ignore[arg-type]
      case EventType.SESSION_END:
        self._handle_session_end(event)  # type: ignore[arg-type]
      case EventType.TURN_START:
        self._handle_turn_start(event)  # type: ignore[arg-type]
      case EventType.TURN_END:
        self._handle_turn_end(event)  # type: ignore[arg-type]
      case EventType.THINKING_START:
        self._handle_thinking_start(event)  # type: ignore[arg-type]
      case EventType.THINKING_CHUNK:
        self._handle_thinking_chunk(event)  # type: ignore[arg-type]
      case EventType.THINKING_END:
        self._handle_thinking_end(event)  # type: ignore[arg-type]
      case EventType.CONTENT_START:
        self._handle_content_start(event)  # type: ignore[arg-type]
      case EventType.CONTENT_CHUNK:
        self._handle_content_chunk(event)  # type: ignore[arg-type]
      case EventType.CONTENT_END:
        self._handle_content_end(event)  # type: ignore[arg-type]
      case EventType.TOOL_CALL:
        self._handle_tool_call(event)  # type: ignore[arg-type]
      case EventType.TOOL_RESULT:
        self._handle_tool_result(event)  # type: ignore[arg-type]
      case EventType.TOOL_CONTENT:
        self._handle_tool_content(event)  # type: ignore[arg-type]
      case EventType.ERROR:
        self._handle_error(event)  # type: ignore[arg-type]
      case EventType.COMMAND:
        self._handle_command(event)  # type: ignore[arg-type]

  def _handle_session_start(self, event: SessionStartEvent) -> None:
    """Handle session start event."""
    self.console.print(f"Yoker v{self.version} - Using model: {event.model}")
    thinking_status = "enabled" if event.thinking_enabled else "disabled"
    self.console.print(f"Thinking mode: {thinking_status} (use /think on|off to toggle)")
    self.console.print("Type /help for available commands.")
    self.console.print("Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")

  def _handle_session_end(self, event: SessionEndEvent) -> None:
    """Handle session end event."""
    self.console.print("\nGoodbye!")

  def _handle_turn_start(self, event: TurnStartEvent) -> None:
    """Handle turn start event."""
    # Reset flags for new turn
    self._thinking_shown = False
    self._content_shown = False
    # Create LiveDisplay for this turn (spinner is active)
    if self._live_display is None:
      self._live_display = LiveDisplay(console=self.console)
      self._live_display.__enter__()
      self._spinner_active = True  # Track spinner state

  def _handle_turn_end(self, event: TurnEndEvent) -> None:
    """Handle turn end event."""
    # Show stats and exit LiveDisplay if active
    if self._live_display:
      # Stop the spinner and exit Live display
      self._live_display.stop_spinner()
      self._live_display.__exit__(None, None, None)
      self._live_display = None
      self._spinner_active = False
      # Print stats directly to console (outside Live, ensures SVG capture)
      duration_s = event.total_duration_ms / 1000.0
      total_tokens = event.prompt_eval_count + event.eval_count
      if total_tokens > 0:
        tokens_per_sec = total_tokens / duration_s if duration_s > 0 else 0
        stats = f"⏱ {duration_s:.1f}s | {event.prompt_eval_count}+{event.eval_count}={total_tokens} tokens | {tokens_per_sec:.0f} tok/s"
      else:
        stats = f"⏱ {duration_s:.1f}s"
      self.console.print(stats, style="dim")
    else:
      # Without live display, add blank line after response
      self.console.print()

  def _handle_thinking_start(self, event: ThinkingStartEvent) -> None:
    """Handle thinking start event."""
    if self.show_thinking:
      # Add separator if there was previous content (e.g., tool calls)
      # Check BEFORE setting the flag
      needs_separator = self._content_shown and self._live_display is None

      self._thinking_shown = True
      self._content_shown = True  # Content was shown this turn

      # Create LiveDisplay if not already active
      if self._live_display is None:
        if needs_separator:
          self.console.print()
        self._live_display = LiveDisplay(console=self.console)
        self._live_display.__enter__()
        self._spinner_active = True  # Spinner is now active
      # Without live display, add newline before thinking
      else:
        self._print_wrapped("\n", style=THINKING_STYLE)

  def _handle_thinking_chunk(self, event: ThinkingChunkEvent) -> None:
    """Handle thinking chunk event."""
    if self.show_thinking:
      if self._live_display:
        self._live_display.append_thinking(event.text)
      else:
        self._print_wrapped(event.text, style=THINKING_STYLE)

  def _handle_thinking_end(self, event: ThinkingEndEvent) -> None:
    """Handle thinking end event."""
    if self.show_thinking:
      if not self._live_display:
        # Without live display, add newlines after thinking
        self._print_wrapped("\n\n")

  def _handle_content_start(self, event: ContentStartEvent) -> None:
    """Handle content start event."""
    # Add separator before response if there was previous content
    # This includes thinking shown, tool calls, or spinner activity
    if self._thinking_shown:
      # Thinking was shown - add separator in LiveDisplay
      if self._live_display:
        self._live_display.append_response("\n")
      else:
        self.console.print()
      self._thinking_shown = False  # Reset for next turn
    elif self._content_shown or self._spinner_active:
      # Tool calls were shown or spinner was active - add separator
      if self._live_display:
        self._live_display.append_response("\n")
      else:
        self.console.print()

    # Create new LiveDisplay if not active (e.g., after tool calls)
    if self._live_display is None:
      self._live_display = LiveDisplay(console=self.console)
      self._live_display.__enter__()

  def _handle_content_chunk(self, event: ContentChunkEvent) -> None:
    """Handle content chunk event."""
    if self._live_display:
      self._live_display.append_response(event.text)
    else:
      self._print_wrapped(event.text)

  def _handle_content_end(self, event: ContentEndEvent) -> None:
    """Handle content end event."""
    # Final newline - only needed without live display
    if not self._live_display:
      self.console.print()

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

  @staticmethod
  def _capitalize(name: str) -> str:
    """Capitalize first letter of name for display.

    Args:
      name: Tool name to capitalize.

    Returns:
      Name with first letter capitalized.
    """
    if name:
      return name[0].upper() + name[1:]
    return name

  def _handle_tool_call(self, event: ToolCallEvent) -> None:
    """Handle tool call event."""
    if self.show_tool_calls:
      # Exit current LiveDisplay to freeze buffered content
      # The content is already visible on screen, we just stop live updating
      if self._live_display:
        self._live_display.stop_spinner()  # Remove spinner before exiting
        self._live_display.__exit__(None, None, None)
        self._live_display = None
        self._spinner_active = False  # Spinner is no longer active

      self._content_shown = True  # Content was shown this turn
      tool_name = self._capitalize(event.tool_name)
      details = self._format_tool_details(event.tool_name, event.arguments)
      # Print tool call with newline separator from previous segment
      self.console.print(f"\n⏺ {tool_name} tool: {details}")

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
      parts = [operation]
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

  def _handle_tool_result(self, event: ToolResultEvent) -> None:
    """Handle tool result event."""
    if self.show_tool_calls:
      # Show success/failure indicator (outside Live context)
      # LiveDisplay was already exited in _handle_tool_call
      if event.success:
        self.console.print("  ✓ Success")
      else:
        # Show first 50 chars of result (error message)
        error_msg = event.result[:50] if event.result else "Failed"
        self.console.print(f"  ✗ {error_msg}")

      # Create LiveDisplay with spinner for subsequent processing
      # This ensures spinner is visible between tool calls and next segment
      if self._live_display is None:
        self._live_display = LiveDisplay(console=self.console)
        self._live_display.__enter__()
        self._spinner_active = True

  def _handle_tool_content(self, event: ToolContentEvent) -> None:
    """Handle tool content event.

    Displays content based on content_type:
    - 'full': Show full content with line numbers
    - 'diff': Show unified diff with colors
    - 'summary': Show operation summary only
    """
    if not self.show_tool_calls:
      return

    # Exit LiveDisplay (created in ToolResult) to print content
    if self._live_display:
      self._live_display.stop_spinner()
      self._live_display.__exit__(None, None, None)
      self._live_display = None
      self._spinner_active = False

    # Tool content is printed outside Live context
    # (Live was exited in _handle_tool_call or above)

    # Get operation details
    operation = event.operation
    filename = Path(event.path).name

    # Dispatch based on content_type
    if event.content_type == "summary":
      self._show_summary(event, filename)
    elif event.content_type == "diff":
      self._show_diff_content(event, filename)
    else:  # content_type == "full"
      self._show_full_content(event, filename)

    # Create LiveDisplay with spinner for subsequent processing
    if self._live_display is None:
      self._live_display = LiveDisplay(console=self.console)
      self._live_display.__enter__()
      self._spinner_active = True

  def _show_summary(self, event: ToolContentEvent, filename: str) -> None:
    """Show operation summary.

    Args:
      event: ToolContentEvent with summary metadata.
      filename: Basename of file.
    """
    operation = event.operation
    metadata = event.metadata

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
      self.console.print(f"  Insert at line {line_number}: {inserted_lines} line(s)")

    elif operation == "replace":
      self.console.print(f"  Replace in {filename}")

    elif operation == "delete":
      line_number = metadata.get("line_number")
      if line_number:
        self.console.print(f"  Delete line {line_number} in {filename}")
      else:
        self.console.print(f"  Delete in {filename}")

  def _show_full_content(self, event: ToolContentEvent, filename: str) -> None:
    """Show full content with line numbers.

    Args:
      event: ToolContentEvent with content.
      filename: Basename of file.
    """
    content = event.content
    metadata = event.metadata

    if content is None:
      # Fall back to summary
      self._show_summary(event, filename)
      return

    # Show header
    operation = event.operation
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

  def _show_diff_content(self, event: ToolContentEvent, filename: str) -> None:
    """Show unified diff with colors.

    Args:
      event: ToolContentEvent with diff content.
      filename: Basename of file.
    """
    content = event.content
    metadata = event.metadata

    if content is None:
      # Fall back to summary
      self._show_summary(event, filename)
      return

    # Show header
    self.console.print(f"  {filename}")

    # Show diff with colors (using ANSI codes)
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
        self.console.print(f"  [cyan]{escaped_line}[/]")  # Cyan
      elif line.startswith("-"):
        self.console.print(f"  [red]{escaped_line}[/]")  # Red
      elif line.startswith("+"):
        self.console.print(f"  [green]{escaped_line}[/]")  # Green
      else:
        self.console.print(f"  {escaped_line}")

    # Show truncation indicator if needed
    if metadata.get("truncated"):
      original_lines = metadata.get("original_diff_lines", 0)
      remaining = original_lines - len(lines)
      self.console.print(f"  ... ({remaining} more lines)")

  def _handle_error(self, event: ErrorEvent) -> None:
    """Handle error event."""
    self.console.print(
      f"\n[Error] {event.error_type}: {event.message}",
      style=ERROR_STYLE,
    )

  def _handle_command(self, event: CommandEvent) -> None:
    """Handle command event."""
    if event.result:
      self.console.print(f"{event.result}\n")

  def _print_wrapped(
    self,
    text: str,
    style: Style | None = None,
    end: str = "",
  ) -> None:
    """Print text with optional wrapping at wrap_width.

    Uses word-aware wrapping - breaks at word boundaries when possible,
    only breaking mid-word when a single word exceeds the wrap width.

    Args:
      text: Text to print.
      style: Optional Rich style.
      end: String to append at the end (default: "").
    """
    if self.wrap_width is None:
      # No wrapping, use standard print
      self.console.print(text, style=style, end=end)
      return

    # Track current position in line
    current_line: list[str] = []

    def flush_line() -> None:
      """Print current line and reset."""
      nonlocal current_line
      if current_line:
        self.console.print("".join(current_line), style=style, end="")
        current_line = []

    for char in text:
      if char == "\n":
        flush_line()
        self.console.print(style=style)
        self._column = 0
      elif char == "\r":
        flush_line()
        self._column = 0
      elif char == " ":
        # Space: check if adding it would exceed width
        if self._column + 1 > self.wrap_width:
          # Line break at word boundary
          flush_line()
          self.console.print(style=style)
          self._column = 0
        else:
          current_line.append(char)
          self._column += 1
      else:
        # Regular character
        if self._column >= self.wrap_width:
          # Break before this character if line is full
          flush_line()
          self.console.print(style=style)
          self._column = 0
        current_line.append(char)
        self._column += 1

    # Flush remaining content
    flush_line()

    if end:
      self.console.print(end, style=style, end="")
