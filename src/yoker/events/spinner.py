"""Streaming display for Yoker CLI using Rich Live.

Provides a live-updating display that shows thinking content, response content,
and a status spinner during LLM streaming.

This module is part of the Event System (presentation layer), providing
visual feedback for interactive sessions only.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

from rich.console import Console
from rich.live import Live
from rich.padding import Padding
from rich.status import Status
from rich.table import Table
from rich.text import Text

# Default refresh rate for Live display
DEFAULT_REFRESH_RATE = 4  # times per second


class LiveDisplay:
  """Live-updating display for streaming content with spinner.

  Uses Rich's Live to manage a continuously refreshing display that shows:
  - Thinking content (dimmed style)
  - Response content
  - Status spinner (during streaming)
  - Turn statistics (after completion)

  Example:
    with LiveDisplay() as display:
        display.append_thinking("Thinking...")
        display.append_response("Hello")
        display.show_stats(tokens=100, duration_ms=1500)
  """

  def __init__(
    self,
    console: Console | None = None,
    refresh_per_second: int = DEFAULT_REFRESH_RATE,
  ) -> None:
    """Initialize the live display.

    Args:
      console: Rich console (default: new Console).
      refresh_per_second: Refresh rate for Live display.
    """
    self.console = console if console is not None else Console()
    self.refresh_per_second = refresh_per_second

    # Text objects for content
    self._thinking_text = Text("", style="dim")
    self._response_text = Text("")

    # Spinner status
    self._spinner: Status | None = None
    self._spinner_active = False

    # Timing
    self._start_time: float = 0.0

    # Stats (shown after spinner stops)
    self._stats_text: Text | None = None

    # Live display (created on enter)
    self._live: Live | None = None

  def __enter__(self) -> "LiveDisplay":
    """Enter the live display context.

    Creates and starts the Live display with empty content.
    """
    self._start_time = time.time()
    self._spinner = self.console.status("Processing...")
    self._spinner_active = True
    self._stats_text = None
    self._live = Live(
      self._build_renderable(),
      console=self.console,
      refresh_per_second=self.refresh_per_second,
      vertical_overflow="visible",
    )
    self._live.__enter__()
    return self

  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    """Exit the live display context."""
    if self._live:
      self._live.__exit__(exc_type, exc_val, exc_tb)

  def stop_spinner(self) -> None:
    """Remove the spinner from the display.

    Called before exiting the Live context to prevent the spinner
    from showing in the final output.
    """
    if self._spinner:
      self._spinner_active = False
      self._spinner = None
      self._update()

  def _build_renderable(self) -> Table:
    """Build the renderable for Live display.

    Returns:
      A Table.grid with thinking, response, and optional spinner/stats.
    """
    grid = Table.grid(expand=True)

    # Add thinking content if present (with left padding for indentation)
    if self._thinking_text.plain:
      grid.add_row(Padding(self._thinking_text, (0, 0, 0, 2)))

    # Add response content
    if self._response_text.plain:
      grid.add_row(Padding(self._response_text, (0, 0, 0, 2)))

    # Add spinner or stats (mutually exclusive)
    if self._spinner_active and self._spinner:
      grid.add_row(self._spinner)
    elif self._stats_text:
      grid.add_row(self._stats_text)

    return grid

  def _update(self) -> None:
    """Trigger a Live display refresh."""
    if self._live:
      self._live.update(self._build_renderable())

  def _update_spinner_time(self) -> None:
    """Update spinner with current elapsed time."""
    if self._spinner and self._spinner_active:
      elapsed = time.time() - self._start_time
      self._spinner.update(f"Processing... {elapsed:.1f}s")

  def start_spinner(self) -> None:
    """Show the spinner (called automatically on context enter)."""
    self._spinner_active = True
    self._update()

  def show_stats(
    self,
    prompt_tokens: int = 0,
    eval_tokens: int = 0,
    duration_ms: int = 0,
  ) -> None:
    """Show turn statistics instead of spinner.

    Args:
      prompt_tokens: Number of prompt/input tokens.
      eval_tokens: Number of generated/output tokens.
      duration_ms: Total duration in milliseconds.
    """
    self._spinner_active = False
    self._spinner = None

    # Build stats text
    duration_s = duration_ms / 1000.0
    total_tokens = prompt_tokens + eval_tokens

    if total_tokens > 0:
      # Calculate tokens per second
      tokens_per_sec = total_tokens / duration_s if duration_s > 0 else 0
      stats = f"⏱ {duration_s:.1f}s | {prompt_tokens}+{eval_tokens}={total_tokens} tokens | {tokens_per_sec:.0f} tok/s\n"
    else:
      # Fallback if no token info available
      stats = f"⏱ {duration_s:.1f}s\n"

    self._stats_text = Text(stats, style="dim")
    self._update()

  def append_thinking(self, text: str) -> None:
    """Append text to the thinking content area.

    Args:
      text: Text to append (displayed dimmed).
    """
    self._thinking_text.append(text)
    self._update_spinner_time()
    self._update()

  def append_response(self, text: str) -> None:
    """Append text to the response content area.

    Args:
      text: Text to append (normal style).
    """
    self._response_text.append(text)
    self._update_spinner_time()
    self._update()

  def clear(self) -> None:
    """Clear all content and reset for next turn."""
    self._thinking_text = Text("", style="dim")
    self._response_text = Text("")
    self._spinner_active = False
    self._spinner = None
    self._stats_text = None


@contextmanager
def live_display(
  console: Console | None = None,
  refresh_per_second: int = DEFAULT_REFRESH_RATE,
) -> Iterator[LiveDisplay]:
  """Context manager for live display.

  Args:
    console: Rich console (default: new Console).
    refresh_per_second: Refresh rate for Live display.

  Yields:
    LiveDisplay instance for content updates.
  """
  display = LiveDisplay(console=console, refresh_per_second=refresh_per_second)
  with display:
    yield display


__all__ = [
  "LiveDisplay",
  "live_display",
]
