"""Demo script loader for Yoker.

Parses Markdown files with YAML frontmatter into DemoScript objects.
Follows the same patterns as AgentDefinition loader.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from yoker.exceptions import ConfigurationError, FileNotFoundError


@dataclass(frozen=True)
class DemoScript:
  """Demo script definition.

  Attributes:
    title: Human-readable title for the demo.
    description: Brief description of what the demo illustrates.
    output: Default output path for the generated SVG.
    events: Default path for event log (JSONL) used for replay.
    messages: List of user messages to send during the demo.
    source_path: Path to the source Markdown file.
  """

  title: str
  description: str
  output: str
  events: str
  messages: tuple[str, ...]
  source_path: str


def _extract_messages(body: str) -> tuple[str, ...]:
  """Extract messages from the ## Messages section.

  Parses Markdown bullet lists, supporting multiline messages
  via indented continuation lines.

  Args:
    body: Markdown body content after frontmatter.

  Returns:
    Tuple of message strings.
  """
  lines = body.split("\n")
  messages: list[str] = []
  in_messages_section = False
  current_message: list[str] = []

  for line in lines:
    stripped = line.strip()

    # Detect Messages section header
    if stripped.lower() == "## messages":
      in_messages_section = True
      continue

    # End of Messages section (next header)
    if in_messages_section and stripped.startswith("##"):
      if current_message:
        messages.append("\n".join(current_message).strip())
      break

    if not in_messages_section:
      continue

    # Bullet list item
    if stripped.startswith("- "):
      # Save previous message if any
      if current_message:
        messages.append("\n".join(current_message).strip())
      current_message = [stripped[2:].strip()]
    elif stripped.startswith("* "):
      if current_message:
        messages.append("\n".join(current_message).strip())
      current_message = [stripped[2:].strip()]
    elif in_messages_section and current_message and not stripped:
      # Blank line between messages - save current
      messages.append("\n".join(current_message).strip())
      current_message = []
    elif in_messages_section and current_message:
      # Continuation line (indented or not)
      current_message.append(stripped)

  # Don't forget the last message
  if current_message:
    messages.append("\n".join(current_message).strip())

  return tuple(m for m in messages if m)


def load_demo_script(path: Path | str) -> DemoScript:
  """Load a demo script from a Markdown file.

  Args:
    path: Path to the Markdown file.

  Returns:
    DemoScript object with parsed frontmatter and messages.

  Raises:
    FileNotFoundError: If the file doesn't exist.
    ConfigurationError: If frontmatter is invalid or missing required fields.
  """
  file_path = Path(path)

  if not file_path.exists():
    raise FileNotFoundError(str(file_path), "demo script")

  try:
    content = file_path.read_text(encoding="utf-8")
  except OSError as e:
    raise ConfigurationError(
      setting=str(file_path),
      message=f"Failed to read file: {e}",
    ) from None

  # Parse frontmatter using yaml.safe_load on the --- delimited block
  lines = content.strip().split("\n")
  if lines and lines[0] == "---":
    try:
      end_index = lines.index("---", 1)
    except ValueError:
      raise ConfigurationError(
        setting="frontmatter",
        message="Frontmatter opening '---' found but no closing '---'",
      ) from None

    frontmatter_lines = lines[1:end_index]
    body_lines = lines[end_index + 1 :]

    try:
      frontmatter = yaml.safe_load("\n".join(frontmatter_lines))
      if frontmatter is None:
        frontmatter = {}
      if not isinstance(frontmatter, dict):
        raise ConfigurationError(
          setting="frontmatter",
          message=f"Frontmatter must be a YAML dictionary, got {type(frontmatter).__name__}",
        )
    except yaml.YAMLError as e:
      raise ConfigurationError(
        setting="frontmatter",
        message=f"Invalid YAML in frontmatter: {e}",
      ) from None

    body = "\n".join(body_lines)
  else:
    frontmatter = {}
    body = content

  # Extract required fields
  title = frontmatter.get("title")
  if not title:
    raise ConfigurationError(
      setting="title",
      message="Required field 'title' is missing or empty",
    )

  description = frontmatter.get("description", "")
  output = frontmatter.get("output", "")
  events = frontmatter.get("events", "")

  # Extract messages from body
  messages = _extract_messages(body)
  if not messages:
    raise ConfigurationError(
      setting="messages",
      message="No messages found in '## Messages' section",
    )

  return DemoScript(
    title=str(title),
    description=str(description),
    output=str(output) if output else "",
    events=str(events) if events else "",
    messages=messages,
    source_path=str(file_path),
  )


def load_demo_scripts(directory: Path | str) -> dict[str, DemoScript]:
  """Load all demo scripts from a directory.

  Args:
    directory: Path to the demos directory.

  Returns:
    Dictionary mapping script titles to DemoScript objects.

  Raises:
    FileNotFoundError: If the directory doesn't exist.
    ConfigurationError: If any demo script is invalid.
  """
  dir_path = Path(directory)

  if not dir_path.exists():
    raise FileNotFoundError(str(dir_path), "demos directory")

  if not dir_path.is_dir():
    raise ConfigurationError(
      setting=str(dir_path),
      message="Demos path is not a directory",
    )

  scripts: dict[str, DemoScript] = {}

  for md_file in sorted(dir_path.glob("*.md")):
    try:
      script = load_demo_script(md_file)
      if script.title in scripts:
        raise ConfigurationError(
          setting=f"demo.{script.title}",
          message=f"Duplicate demo title '{script.title}' in {md_file}",
        )
      scripts[script.title] = script
    except ConfigurationError:
      raise
    except Exception as e:
      raise ConfigurationError(
        setting=str(md_file),
        message=f"Failed to load demo script: {e}",
      ) from None

  return scripts


__all__ = [
  "DemoScript",
  "load_demo_script",
  "load_demo_scripts",
]
