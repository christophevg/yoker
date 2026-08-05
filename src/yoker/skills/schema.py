"""Skill definition schema for Yoker.

Provides dataclass for skill definitions loaded from Markdown files.
Skills are prompts that can be invoked via slash commands or natural language.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yoker.schema import NameSpaced

# Maximum resource file size in KB (same limit as skill definitions).
MAX_RESOURCE_SIZE_KB = 100


@dataclass
class Skill(NameSpaced):
  """Skill definition loaded from a Markdown file.

  Skills are reusable prompts that guide agent behavior for specific tasks.
  They can be invoked via slash commands (e.g., /commit) or natural language.

  Attributes:
    name: Skill identifier (unique, used in slash commands).
    description: Short description for system reminder discovery block.
    content: Full skill content (body after frontmatter).
    triggers: Optional list of trigger phrases for natural language invocation.
    tools: Optional list of tool names this skill uses.
    source_path: Path to the source Markdown file.
    namespace: Optional namespace prefix (e.g., 'pkg' for 'pkg:skill').
    _base_dir: Private base directory for resolving resource files. Set by
      the loader to the skill's containing directory (a ``pathlib.Path`` or
      ``importlib.resources`` ``Traversable``). ``None`` for inline skills
      constructed in code.
  """

  description: str = ""
  content: str = ""
  triggers: tuple[str, ...] = ()
  tools: tuple[str, ...] = ()
  source_path: str = ""
  _base_dir: Any = field(default=None, repr=False, compare=False)

  def __post_init__(self) -> None:
    if not self.description:
      raise ValueError("A skill needs a description.")
    if not self.content:
      raise ValueError("A skill needs content")

  def get_resource(self, resource_path: str) -> str:
    """Read a resource file relative to this skill's base directory.

    The resource is loaded lazily — only when requested — to avoid
    loading files that may never be needed. Works with both filesystem
    paths (``pathlib.Path``) and package resources (``Traversable``),
    since both support ``/`` (joinpath) and ``read_text()``.

    Args:
      resource_path: Relative path to the resource file (e.g.,
        ``"references/info.md"`` or ``"patterns/atomic-commits.md"``).

    Returns:
      The text content of the resource file.

    Raises:
      FileNotFoundError: If the skill has no base directory (inline skill)
        or the resource file does not exist.
      ValueError: If the resource path attempts path traversal (``..``).
      ConfigurationError: If the resource exceeds the size limit.
    """
    from yoker.exceptions import ConfigurationError

    if self._base_dir is None:
      raise FileNotFoundError(
        f"Skill '{self.name}' has no base directory; cannot load resource '{resource_path}'."
      )

    # Reject path traversal attempts
    if ".." in Path(resource_path).parts:
      raise ValueError(f"Resource path '{resource_path}' must not contain '..'.")

    try:
      resource = self._base_dir / resource_path
    except Exception as e:
      raise FileNotFoundError(
        f"Failed to resolve resource '{resource_path}' for skill '{self.name}': {e}"
      ) from None

    # For filesystem paths, check existence explicitly for a clean error.
    # Traversable raises on read if not found, which we catch below.
    if isinstance(resource, Path) and not resource.is_file():
      raise FileNotFoundError(f"Resource '{resource_path}' not found for skill '{self.name}'.")

    try:
      content: str = resource.read_text(encoding="utf-8")
    except FileNotFoundError:
      raise FileNotFoundError(
        f"Resource '{resource_path}' not found for skill '{self.name}'."
      ) from None
    except Exception as e:
      raise FileNotFoundError(
        f"Failed to read resource '{resource_path}' for skill '{self.name}': {e}"
      ) from None

    # Enforce size limit
    size_kb = len(content.encode("utf-8")) / 1024
    if size_kb > MAX_RESOURCE_SIZE_KB:
      raise ConfigurationError(
        setting=f"resource.{resource_path}",
        message=(
          f"Resource '{resource_path}' for skill '{self.name}' "
          f"exceeds maximum size ({size_kb:.1f}KB > {MAX_RESOURCE_SIZE_KB}KB)"
        ),
      )

    return content


__all__ = ["Skill", "MAX_RESOURCE_SIZE_KB"]
