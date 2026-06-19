"""Public annotations for Yoker tools.

Provides marker classes that attach guardrail types and descriptions to
function parameters. The framework introspects these annotations to build
tool schemas and dispatch guardrails at execution time.

Example:
  from typing import Annotated
  from yoker.annotations import Path, Text

  def read_file(
    path: Annotated[str, Path("Path to the file to read")],
    encoding: Annotated[str, Text("File encoding")] = "utf-8",
  ) -> str:
    ...
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GuardType(str, Enum):
  """Functional type of a guardrailed string parameter."""

  PATH = "path"
  URL = "url"
  QUERY = "query"
  TEXT = "text"


@dataclass(frozen=True)
class Text:
  """Marker for plain text parameters with no guardrail.

  Attributes:
    description: Parameter description for the generated schema.
    yoker_type: Functional type used by the guardrail dispatcher.
  """

  description: str = ""
  yoker_type: GuardType = GuardType.TEXT


@dataclass(frozen=True)
class Path(Text):
  """Marker for filesystem path parameters."""

  yoker_type: GuardType = GuardType.PATH


@dataclass(frozen=True)
class Url(Text):
  """Marker for URL parameters."""

  yoker_type: GuardType = GuardType.URL


@dataclass(frozen=True)
class Query(Text):
  """Marker for web search query parameters."""

  yoker_type: GuardType = GuardType.QUERY


def tool(
  func: Callable[..., Any] | None = None,
  *,
  name: str | None = None,
  description: str | None = None,
) -> Callable[..., Any]:
  """Optional decorator to override a tool's name or description.

  When applied to a function or callable class, this decorator sets
  ``__yoker_name__`` and ``__yoker_description__`` metadata attributes
  that ``build_tool_spec`` reads during introspection.

  The decorator is sugar; the same metadata can be set directly on
  the callable.

  Args:
    func: Callable being decorated. None when used with keyword arguments.
    name: Explicit tool name override.
    description: Explicit tool description override.

  Returns:
    The decorated callable, unchanged except for metadata attributes.
  """

  def _apply(target: Callable[..., Any]) -> Callable[..., Any]:
    if name is not None:
      target.__yoker_name__ = name  # type: ignore[attr-defined]
    if description is not None:
      target.__yoker_description__ = description  # type: ignore[attr-defined]
    return target

  if func is not None:
    return _apply(func)
  return _apply


__all__ = [
  "GuardType",
  "Text",
  "Path",
  "Url",
  "Query",
  "tool",
]
