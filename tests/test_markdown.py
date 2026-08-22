"""Tests for the MarkdownStreamer class."""

from io import StringIO

from rich.console import Console

from yoker.markdown import MarkdownStreamer


def make_streamer(output: StringIO | None = None) -> tuple[MarkdownStreamer, StringIO]:
  """Create a MarkdownStreamer with a capture console."""
  out = output or StringIO()
  console = Console(file=out, force_terminal=False, color_system=None, highlight=False)
  streamer = MarkdownStreamer(console=console, output=console)
  return streamer, out


class TestFlushNewlinePreservation:
  """Tests for the flush() method ensuring newlines between buffer and accumulator."""

  def test_flush_list_last_line_without_newline(self):
    """The last line of a list arrives without a trailing newline.

    The accumulator holds it, and flush() must insert a newline between
    the buffered lines and the remaining accumulator content.
    """
    streamer, out = make_streamer()

    # Simulate streaming: lines with newlines, then final line without newline
    streamer.append("Would you like to:\n")
    streamer.append("1. **Proceed with P2.5** — start the next task\n")
    streamer.append("2. **Prepare a release** — publish current state to PyPI\n")
    streamer.append("3. **Something else**")  # no trailing newline

    streamer.flush()

    rendered = out.getvalue()
    # The three list items must be on separate lines, not concatenated
    assert "PyPI" in rendered
    assert "Something else" in rendered
    # "PyPI" and "Something else" must not be on the same rendered line
    # (the bug concatenated them as "PyPI3. Something else")
    for line in rendered.splitlines():
      assert "PyPI3" not in line, (
        f"Expected items on separate lines, but got concatenation: {line!r}"
      )
      assert "PyDISomething" not in line, (
        f"Expected items on separate lines, but got concatenation: {line!r}"
      )

  def test_flush_paragraph_last_line_without_newline(self):
    """A paragraph block where the last line has no trailing newline."""
    streamer, out = make_streamer()

    streamer.append("First paragraph line.\n")
    streamer.append("Second paragraph line without newline")  # no trailing \n

    streamer.flush()

    rendered = out.getvalue()
    # Both lines should be present and not concatenated
    assert "First paragraph line." in rendered
    assert "Second paragraph line without newline" in rendered
    for line in rendered.splitlines():
      assert "line.Second" not in line, (
        f"Expected lines separated, but got: {line!r}"
      )

  def test_flush_only_accumulator_no_buffer(self):
    """Flush with only accumulator content (no buffered block)."""
    streamer, out = make_streamer()

    streamer.append("Just a line without newline")

    streamer.flush()

    rendered = out.getvalue()
    assert "Just a line without newline" in rendered

  def test_flush_only_buffer_no_accumulator(self):
    """Flush with only buffered content (accumulator empty)."""
    streamer, out = make_streamer()

    streamer.append("A line with newline\n")

    streamer.flush()

    rendered = out.getvalue()
    assert "A line with newline" in rendered

  def test_flush_empty(self):
    """Flush with no content at all should not raise."""
    streamer, out = make_streamer()

    streamer.flush()

    assert out.getvalue() == ""