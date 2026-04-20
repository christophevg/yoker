"""Event handlers for the Yoker event system."""

from typing import Protocol, runtime_checkable

from rich.console import Console
from rich.style import Style

from yoker.events.types import (
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
TOOL_STYLE = Style(color="yellow")


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

    # State for wrapping
    self._column = 0

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
    # User input is already displayed by the input function
    pass

  def _handle_turn_end(self, event: TurnEndEvent) -> None:
    """Handle turn end event."""
    # Add blank line after response
    self.console.print()

  def _handle_thinking_start(self, event: ThinkingStartEvent) -> None:
    """Handle thinking start event."""
    if self.show_thinking:
      self._print_wrapped("\n", style=THINKING_STYLE)

  def _handle_thinking_chunk(self, event: ThinkingChunkEvent) -> None:
    """Handle thinking chunk event."""
    if self.show_thinking:
      self._print_wrapped(event.text, style=THINKING_STYLE)

  def _handle_thinking_end(self, event: ThinkingEndEvent) -> None:
    """Handle thinking end event."""
    if self.show_thinking:
      self._print_wrapped("\n\n")

  def _handle_content_start(self, event: ContentStartEvent) -> None:
    """Handle content start event."""
    # Content starts immediately
    pass

  def _handle_content_chunk(self, event: ContentChunkEvent) -> None:
    """Handle content chunk event."""
    self._print_wrapped(event.text)

  def _handle_content_end(self, event: ContentEndEvent) -> None:
    """Handle content end event."""
    self.console.print()  # Final newline

  def _handle_tool_call(self, event: ToolCallEvent) -> None:
    """Handle tool call event."""
    if self.show_tool_calls:
      args_str = ", ".join(f"{k}={v!r}" for k, v in event.arguments.items())
      self.console.print(f"\n[Tool Call] {event.tool_name}({args_str})", style=TOOL_STYLE)

  def _handle_tool_result(self, event: ToolResultEvent) -> None:
    """Handle tool result event."""
    # Don't show tool result output - only show tool calls
    pass

  def _handle_error(self, event: ErrorEvent) -> None:
    """Handle error event."""
    self.console.print(
      f"\n[Error] {event.error_type}: {event.message}",
      style=ERROR_STYLE,
    )

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
      # No wrapping, use standard print
      self.console.print(text, style=style, end=end)
      return

    # Wrap at width boundary
    for char in text:
      if char == "\n":
        self._column = 0
      elif char == "\r":
        self._column = 0
      elif self._column >= self.wrap_width:
        self.console.print()
        self._column = 0

      self.console.print(char, style=style, end="")
      self._column += 1

    if end:
      self.console.print(end, style=style, end="")
