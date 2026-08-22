from rich.console import Console
from rich.markdown import Markdown
from rich.style import Style
from rich.text import Text

LIST = "list"
CODE_BLOCK = "code_block"
TABLE = "table"
BLOCK_QUOTE = "block_quote"
PARAGRAPH = "paragraph"
HORIZONTAL_RULE = "horizontal_rule"


class MarkdownStreamer:
  """
  Simple Markdown Streaming class. Accepts char/token stream, buffering until a complete block is identified, then renders that as separate piece of Markdown.
  """

  def __init__(
    self,
    console: Console | None = None,
    style: Style | None = None,
    code_theme: str | None = None,
    output: Console | None = None,
  ) -> None:
    self.console = console or Console()
    self.output = output or self.console
    self.style = style
    self.code_theme = code_theme or "default"

    # accumulate chars/tokens. we'll process full lines from it.
    self.accumulator = ""

    # buffer for all lines of a block
    self._buffer: list[str] = []
    self.buffering: str | None = None  # what are we buffering?

    # keep track if we previously rendered a block
    self.previous = False

    # Tracking active formatting states across lines
    self.in_bold = False
    self.in_inline_code = False

  def append(self, token: str) -> None:
    """
    Processes streaming text. Buffers lines when inline styles span across
    newline boundaries, renders complete blocks.
    TODO: when buffering paragraph and not in inline formatting, output simple chars to simulate actual streaming even more.
    """
    self.accumulator += token

    # process full lines of accumulated content
    while "\n" in self.accumulator:
      line, self.accumulator = self.accumulator.split("\n", 1)
      stripped = line.strip()

      # 1. detect end of code block, while in code block don't detect anything else
      if self.buffering is CODE_BLOCK:
        self.buffer(line, CODE_BLOCK)
        if stripped.startswith("```"):
          self.render()
        continue

      # detect start of code block
      if stripped.startswith("```"):
        self.buffer(line, CODE_BLOCK)
        continue

      # 2. Empty line ends any previous block.
      if stripped == "":
        self.render()
        continue

      # 3. horizontal rule
      if stripped == "---":
        self.buffer(line, HORIZONTAL_RULE)
        continue

      # 4. detect list item
      if stripped[0] in ("-", "*", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        self.buffer(line, LIST)
        continue

      # 5. detect heading -> direct rendering of single line "block"
      if stripped.startswith("#"):
        self.render(line)
        continue

      # 6. detect tables
      if stripped.startswith("|"):
        self.buffer(line, TABLE)
        continue

      # 7. detect block quotes
      if stripped.startswith(">"):
        self.buffer(line, BLOCK_QUOTE)
        continue

      # 8. all other content is added to paragraphs
      # TODO: print not formatted content directly, simulating streaming more visually
      #       when inline formatting (bold, italic, links,...) are detected, buffer
      #       until complete, then format and print.
      self.buffer(line, PARAGRAPH)

  def buffer(self, line: str, kind: str) -> None:
    # add content of kind to buffer
    # if not the same as currently buffering, first render the current buffer
    if self.buffering is not kind:
      self.render()
    self.buffering = kind
    self._buffer.append(line)

  def _unbuffer(self) -> str:
    combined = "\n".join(self._buffer)
    self._buffer.clear()
    self.buffering = None
    return combined

  def render(self, block: str | None = None) -> None:
    # renders currently buffered markdown block, keeping control of whitespace,
    # because since we're dealing with individual consecutive blocks instead of giving
    #  the entire content at once
    block = block or self._unbuffer()
    block = block.strip()
    if not block:
      return  # ignore, keep state
    if self.previous:
      self.output.print()  # whitespace between blocks
    # use capture to strip newline whitespace from output
    with self.console.capture() as capture:
      self.console.print(Markdown(block, code_theme=self.code_theme), style=self.style)
    # strip leading newlines and all trailing whitespace
    rendered_output = capture.get().lstrip("\n").rstrip()
    if rendered_output:
      # Convert ANSI-coded text to a styled Text so the output console
      # records proper Segments (no double formatting, SVG export works).
      self.output.print(Text.from_ansi(rendered_output), soft_wrap=True, end="")
      self.previous = True
    else:
      self.previous = False
      self.buffering = None

  def flush(self) -> None:
    # clean up remaining accumulated chars/tokens
    remaining = self._unbuffer()
    if self.accumulator:
      if remaining:
        remaining += "\n"
      remaining += self.accumulator
      self.accumulator = ""
    self.render(remaining)
