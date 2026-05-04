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
    live_display: LiveDisplay | None = None,
  ) -> None:
    """Initialize the console handler.

    Args:
      console: Rich console (default: new Console).
      show_thinking: Whether to display thinking output.
      show_tool_calls: Whether to display tool call info.
      wrap_width: Optional width for wrapping streaming output.
      version: Version string to display in session start.
      live_display: Optional live display for interactive sessions.
    """
    self.console = console if console is not None else Console()
    self.show_thinking = show_thinking
    self.show_tool_calls = show_tool_calls
    self.wrap_width = wrap_width
    self.version = version
    self.live_display = live_display

    # State for wrapping and thinking tracking
    self._column = 0
    self._thinking_shown = False  # Track if thinking was displayed

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
    # Reset thinking flag for new turn
    self._thinking_shown = False

  def _handle_turn_end(self, event: TurnEndEvent) -> None:
    """Handle turn end event."""
    # Show stats and stop live display if active
    if self.live_display:
      self.live_display.show_stats(
        prompt_tokens=event.prompt_eval_count,
        eval_tokens=event.eval_count,
        duration_ms=event.total_duration_ms,
      )
      self.live_display = None
      # Note: Don't print anything inside Live context - it will be handled
      # by the Live context exiting and printing the final renderable
    else:
      # Without live display, add blank line after response
      self.console.print()

  def _handle_thinking_start(self, event: ThinkingStartEvent) -> None:
    """Handle thinking start event."""
    if self.show_thinking:
      self._thinking_shown = True
      if not self.live_display:
        # Without live display, add newline before thinking
        self._print_wrapped("\n", style=THINKING_STYLE)

  def _handle_thinking_chunk(self, event: ThinkingChunkEvent) -> None:
    """Handle thinking chunk event."""
    if self.show_thinking:
      if self.live_display:
        self.live_display.append_thinking(event.text)
      else:
        self._print_wrapped(event.text, style=THINKING_STYLE)

  def _handle_thinking_end(self, event: ThinkingEndEvent) -> None:
    """Handle thinking end event."""
    if self.show_thinking:
      if not self.live_display:
        # Without live display, add newlines after thinking
        self._print_wrapped("\n\n")

  def _handle_content_start(self, event: ContentStartEvent) -> None:
    """Handle content start event."""
    # Add blank line between thinking and response if thinking was shown
    if self._thinking_shown:
      if self.live_display:
        self.live_display.append_response("\n")
      else:
        self.console.print()
      self._thinking_shown = False  # Reset for next turn

  def _handle_content_chunk(self, event: ContentChunkEvent) -> None:
    """Handle content chunk event."""
    if self.live_display:
      self.live_display.append_response(event.text)
    else:
      self._print_wrapped(event.text)

  def _handle_content_end(self, event: ContentEndEvent) -> None:
    """Handle content end event."""
    # Final newline - only needed without live display
    if not self.live_display:
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
      tool_name = self._capitalize(event.tool_name)
      details = self._format_tool_details(event.tool_name, event.arguments)
      self.console.print(f"\n{tool_name} tool: {details}", style=TOOL_STYLE)

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
      # Show success/failure indicator
      if event.success:
        self.console.print("  ✓ Success", style="dim green")
      else:
        # Show first 50 chars of result (error message)
        error_msg = event.result[:50] if event.result else "Failed"
        self.console.print(f"  ✗ {error_msg}", style="dim red")

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
