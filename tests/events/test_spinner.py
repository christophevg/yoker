"""Tests for LiveDisplay."""

from rich.console import Console

from yoker.events.spinner import LiveDisplay, live_display


class TestLiveDisplay:
  """Test cases for LiveDisplay class."""

  def test_init_default_values(self) -> None:
    """Test default initialization."""
    display = LiveDisplay()
    assert display.refresh_per_second == 4
    assert display._live is None
    assert display._spinner_active is False

  def test_init_custom_values(self) -> None:
    """Test custom initialization."""
    console = Console()
    display = LiveDisplay(console=console, refresh_per_second=10)
    assert display.console is console
    assert display.refresh_per_second == 10

  def test_context_manager_creates_live(self) -> None:
    """Test that __enter__ creates Live display."""
    display = LiveDisplay()
    with display:
      assert display._live is not None
      assert display._spinner_active is True

  def test_context_manager_exits_cleanly(self) -> None:
    """Test that __exit__ cleans up."""
    display = LiveDisplay()
    with display:
      pass  # Just enter and exit
    assert display._live is not None  # Live object still exists

  def test_append_thinking(self) -> None:
    """Test appending thinking content."""
    display = LiveDisplay()
    with display:
      display.append_thinking("thinking...")
      assert display._thinking_text.plain == "thinking..."

  def test_append_response(self) -> None:
    """Test appending response content."""
    display = LiveDisplay()
    with display:
      display.append_response("response")
      assert display._response_text.plain == "response"

  def test_append_multiple_chunks(self) -> None:
    """Test appending multiple chunks."""
    display = LiveDisplay()
    with display:
      display.append_thinking("think1 ")
      display.append_thinking("think2")
      display.append_response("resp1 ")
      display.append_response("resp2")
      assert display._thinking_text.plain == "think1 think2"
      assert display._response_text.plain == "resp1 resp2"

  def test_stop_spinner(self) -> None:
    """Test stopping spinner."""
    display = LiveDisplay()
    with display:
      assert display._spinner_active is True
      display.stop_spinner()
      assert display._spinner_active is False
      assert display._spinner is None

  def test_clear(self) -> None:
    """Test clearing content."""
    display = LiveDisplay()
    with display:
      display.append_thinking("thinking")
      display.append_response("response")
      display.clear()
      assert display._thinking_text.plain == ""
      assert display._response_text.plain == ""
      assert display._spinner_active is False

  def test_build_renderable_with_content(self) -> None:
    """Test building renderable with content."""
    display = LiveDisplay()
    with display:
      display.append_thinking("thinking")
      display.append_response("response")
      renderable = display._build_renderable()
      # The renderable should be a Table.grid with rows
      assert renderable is not None

  def test_build_renderable_empty(self) -> None:
    """Test building renderable with no content."""
    display = LiveDisplay()
    with display:
      renderable = display._build_renderable()
      # Even empty, the spinner should be there
      assert renderable is not None


class TestLiveDisplayContext:
  """Test the live_display context manager function."""

  def test_context_manager_function(self) -> None:
    """Test the live_display context manager function."""
    with live_display() as display:
      assert display._live is not None
      display.append_response("test")

  def test_context_manager_with_console(self) -> None:
    """Test context manager with custom console."""
    console = Console()
    with live_display(console=console) as display:
      assert display.console is console


class TestLiveDisplayIntegration:
  """Integration tests for LiveDisplay."""

  def test_full_workflow(self) -> None:
    """Test a typical workflow."""
    display = LiveDisplay()
    with display:
      # Simulate thinking
      display.append_thinking("Let me think...\n")
      display.append_thinking("Processing request.\n")

      # Simulate response
      display.append_response("Hello ")
      display.append_response("World!")

      # Stop spinner
      display.stop_spinner()

      assert display._thinking_text.plain == "Let me think...\nProcessing request.\n"
      assert display._response_text.plain == "Hello World!"
      assert display._spinner_active is False

  def test_newlines_in_content(self) -> None:
    """Test that newlines are handled correctly."""
    display = LiveDisplay()
    with display:
      display.append_response("Line 1\n")
      display.append_response("Line 2\n")
      display.append_response("Line 3")
      display.stop_spinner()

      assert display._response_text.plain == "Line 1\nLine 2\nLine 3"

  def test_show_stats(self) -> None:
    """Test showing turn statistics."""
    display = LiveDisplay()
    with display:
      display.append_response("Response")
      display.show_stats(prompt_tokens=50, eval_tokens=100, duration_ms=1500)

      assert display._spinner_active is False
      assert display._spinner is None
      assert display._stats_text is not None
      assert "50+100=150" in display._stats_text.plain
      assert "tok/s" in display._stats_text.plain

  def test_show_stats_no_tokens(self) -> None:
    """Test showing stats when no token info available."""
    display = LiveDisplay()
    with display:
      display.append_response("Response")
      display.show_stats(prompt_tokens=0, eval_tokens=0, duration_ms=2000)

      assert display._stats_text is not None
      assert "2.0s" in display._stats_text.plain
      # Should not have token info
      assert "tok/s" not in display._stats_text.plain

  def test_show_stats_replaces_spinner(self) -> None:
    """Test that show_stats replaces the spinner."""
    display = LiveDisplay()
    with display:
      # Initially spinner should be active
      assert display._spinner_active is True

      display.show_stats(prompt_tokens=10, eval_tokens=20, duration_ms=500)

      # Spinner should be replaced by stats
      assert display._spinner_active is False
      assert display._spinner is None
      assert display._stats_text is not None
