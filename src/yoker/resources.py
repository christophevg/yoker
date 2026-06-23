"""
General purpose functions for resolving and accessing resources.

A "resource" is a definition file (e.g. a skill or agent Markdown file) that
can live in several places:

  - a folder on the filesystem containing multiple instances,
  - a single file referenced by a full path,
  - a folder inside an installed Python package (accessed via
    ``importlib.resources``),
  - a custom string reference such as ``plugin://package/skills/name``.

The helpers below only abstract the operations where ``pathlib.Path`` and the
``importlib.resources`` ``Traversable`` interface genuinely differ (directory
enumeration, nested layouts, package-resource resolution). For everything they
share — ``read_text()``, ``name``, ``is_dir()``, ``is_file()`` — callers use
the objects directly.
"""

import importlib.resources as resources
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import yaml

from yoker.exceptions import ConfigurationError


def find_package_subdirectory(package: str, subdir: str) -> Any:
  """Return a subdirectory from package resources, or None if not found.

  Args:
    package: Python package name.
    subdir: Directory name within the package.

  Returns:
    Traversable subdirectory path, or None if not found or not accessible.
  """
  directory = find_package_path(package, subdir)
  return directory if is_dir(directory) else None


def find_package_path(package: str, subpath: str) -> Any:
  """Return a file or directory from package resources, or None if not found.

  Unlike :func:`find_package_subdirectory`, this accepts a multi-segment
  ``subpath`` (e.g. ``"skills/my-skill"``) and resolves either a file or a
  directory.

  Args:
    package: Python package name.
    subpath: Slash-separated path within the package (``""`` for the package
      root).

  Returns:
    Traversable path, or None if not found or not accessible.
  """
  try:
    root = resources.files(package)
    path = root.joinpath(subpath) if subpath else root
    if is_file(path) or is_dir(path):
      return path
    return None
  except Exception:
    return None


@dataclass(frozen=True)
class PluginURL:
  """Parsed ``plugin://`` URL: a package and a path within it.

  Attributes:
    package: Python package name.
    subpath: Slash-separated path within the package (``""`` for the package
      root). Callers interpret this (e.g. an ``agents/`` prefix denotes an
      agent resource) — the parser itself is resource-type agnostic.
  """

  package: str
  subpath: str


def parse_plugin_url(url: str) -> PluginURL:
  """Parse a ``plugin://`` URL into a package and subpath.

  Args:
    url: ``plugin://package/path/to/resource`` URL.

  Returns:
    Parsed :class:`PluginURL`.

  Raises:
    ValueError: If the URL is not a valid ``plugin://`` URL.
  """
  if not url.startswith("plugin://"):
    raise ValueError(f"Invalid plugin URL: {url}")
  path = url[len("plugin://") :]
  if not path:
    raise ValueError(f"Invalid plugin URL: {url}")
  parts = path.split("/")
  package = parts[0]
  if not package:
    raise ValueError(f"Invalid plugin URL: {url}")
  return PluginURL(package=package, subpath="/".join(parts[1:]))


def iter_files(
  directory: Any,
  *,
  suffix: str = ".md",
  exclude: tuple[str, ...] = (),
) -> Iterator[Any]:
  """Yield direct child files of a directory whose name ends with ``suffix``.

  Works for both ``pathlib.Path`` and ``importlib.resources`` ``Traversable``
  (which lacks ``glob``). Results are sorted by name for deterministic
  ordering. Names listed in ``exclude`` are skipped — used e.g. to ignore
  ``SKILL.md`` marker files when scanning a flat skills directory.

  Args:
    directory: A Path or Traversable pointing at a directory.
    suffix: File suffix to match (defaults to ``.md``).
    exclude: Tuple of file names to skip.

  Yields:
    Path or Traversable entries for each matching file.
  """
  if not is_dir(directory):
    return
  for entry in sorted(directory.iterdir(), key=lambda e: e.name):
    if not is_file(entry):
      continue
    if entry.name in exclude:
      continue
    if entry.name.endswith(suffix):
      yield entry


def iter_nested(
  directory: Any,
  *,
  child_file: str = "SKILL.md",
) -> Iterator[Any]:
  """Yield ``child_file`` from each subdirectory that contains it.

  Supports nested resource layouts such as ``skills/<name>/SKILL.md``.
  Works for both ``pathlib.Path`` and ``Traversable``. Results are sorted by
  the subdirectory name.

  Args:
    directory: A Path or Traversable pointing at a directory.
    child_file: File name to look for inside each subdirectory.

  Yields:
    Path or Traversable entries for each ``<subdir>/<child_file>`` found.
  """
  if not is_dir(directory):
    return
  for entry in sorted(directory.iterdir(), key=lambda e: e.name):
    if not is_dir(entry):
      continue
    child = entry / child_file
    if is_file(child):
      yield child


def is_dir(path: Any) -> bool:
  """Return True if ``path`` is a directory (Path or Traversable)."""
  checker = getattr(path, "is_dir", None)
  return bool(checker()) if callable(checker) else False


def is_file(path: Any) -> bool:
  """Return True if ``path`` is a file (Path or Traversable)."""
  checker = getattr(path, "is_file", None)
  return bool(checker()) if callable(checker) else False


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, object], str]:
  """Parse YAML frontmatter from Markdown content.

  Args:
    content: Raw file content (may contain frontmatter).

  Returns:
    Tuple of (frontmatter dict, body content).
    If no frontmatter, returns ({}, content).

  Raises:
    ConfigurationError: If frontmatter exists but is invalid YAML.
  """
  lines = content.strip().split("\n")

  # Check for frontmatter delimiter
  if not lines or lines[0] != "---":
    return {}, content

  # Find closing delimiter
  try:
    end_index = lines.index("---", 1)
  except ValueError:
    # No closing delimiter - not valid frontmatter
    return {}, content

  # Extract frontmatter and body
  frontmatter_lines = lines[1:end_index]
  body_lines = lines[end_index + 1 :]

  if not frontmatter_lines:
    # Empty frontmatter
    return {}, "\n".join(body_lines)

  # Parse YAML
  try:
    frontmatter = yaml.safe_load("\n".join(frontmatter_lines))
    if frontmatter is None:
      frontmatter = {}
    if not isinstance(frontmatter, dict):
      raise ConfigurationError(
        setting="frontmatter",
        message=f"Frontmatter must be a YAML dictionary, got {type(frontmatter).__name__}",
      )
    return frontmatter, "\n".join(body_lines)
  except yaml.YAMLError as e:
    raise ConfigurationError(
      setting="frontmatter",
      message=f"Invalid YAML in frontmatter: {e}",
    ) from None
