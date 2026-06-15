"""Tests for LiveDisplay in the UI layer."""

from rich.console import Console

from yoker.ui.spinner import LiveDisplay, live_display


class TestUILiveDisplay:
  """Tests for LiveDisplay imported from UI layer."""

  def test_import_from_ui_layer(self):
    """LiveDisplay should be importable from yoker.ui.spinner."""
    from yoker.ui import LiveDisplay as UILiveDisplay

    assert UILiveDisplay is LiveDisplay

  def test_init_default_values(self):
    """Test default initialization."""
    display = LiveDisplay()
    assert display.refresh_per_second == 4
    assert display._live is None
    assert display._spinner_active is False

  def test_init_custom_values(self):
    """Test custom initialization."""
    console = Console()
    display = LiveDisplay(console=console, refresh_per_second=10)
    assert display.console is console
    assert display.refresh_per_second == 10

  def test_context_manager(self):
    """Test LiveDisplay context manager."""
    with LiveDisplay() as display:
      display.append_thinking("thinking")
      display.append_response("response")
      assert display._thinking_text.plain == "thinking"
      assert display._response_text.plain == "response"

  def test_live_display_context_manager_function(self):
    """Test the live_display context manager function."""
    console = Console()
    with live_display(console=console) as display:
      assert display.console is console
      display.append_response("test")

  def test_show_stats(self):
    """Test showing turn statistics."""
    with LiveDisplay() as display:
      display.show_stats(prompt_tokens=50, eval_tokens=100, duration_ms=1500)
      assert display._stats_text is not None
      assert "50+100=150" in display._stats_text.plain
      assert "tok/s" in display._stats_text.plain
