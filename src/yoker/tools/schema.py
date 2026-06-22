"""Tool introspection for Yoker.

Provides ``ToolSpec`` and ``build_tool_spec`` for converting any Python
function or callable class into a Yoker tool. Schemas and guardrail
metadata are derived through ``inspect`` and ``typing`` introspection.

Also provides ``ToolResult`` and ``ValidationResult``, the return types used
by tool execution and guardrail validation.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ForwardRef, get_origin

from structlog import get_logger

from yoker.annotations import GuardType, Text
from yoker.schema import NameSpaced

if TYPE_CHECKING:
  from yoker.tools.context import ToolContext

logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolResult:
  """Result of a tool execution.

  Attributes:
    success: Whether the tool executed successfully.
    result: The result data (string content or dict for structured results).
    error: Error message if success is False.
    content_metadata: Optional metadata for content display events.
      When provided, the agent emits a ToolContentEvent after ToolResultEvent.
      Contains operation, path, content_type, content, and metadata dict.
  """

  success: bool
  result: str | dict[str, Any] = ""
  error: str | None = None
  content_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValidationResult:
  """Result of a guardrail validation check.

  Attributes:
    valid: Whether the parameters passed validation.
    reason: Explanation if validation failed.
  """

  valid: bool
  reason: str | None = None


@dataclass
class ToolSpec(NameSpaced):
  """Internal contract for a registered tool.

  Attributes:
    simple_name: Tool simple name, without namespace.
    namespace: Tool namespace.
    description: Tool description shown to the LLM.
    schema: Ollama-compatible function schema with harness metadata stripped.
    guards: Mapping of parameter name to guardrail functional type.
    execute: The original tool function (sync or async).
  """

  description: str = ""
  schema: dict[str, Any] = field(default_factory=dict)
  guards: dict[str, GuardType] = field(default_factory=dict)
  execute: Callable[..., Any] | None = None

  def __post_init__(self):
    if not self.description:
      raise ValueError("A tool needs a description.")
    if not self.execute:
      raise ValueError("A tool needs a callable to execute.")

# JSON-schema type mapping for common Python types.
_JSON_SCHEMA_TYPES: dict[type[Any], str] = {
  str: "string",
  int: "integer",
  float: "number",
  bool: "boolean",
}


def build_tool_spec(
  tool: Callable[..., Any],
  *,
  namespace: str | None = None,
  name: str | None = None,
) -> ToolSpec:
  """Build a ``ToolSpec`` from a function or callable class.

  The resulting spec contains the tool name, description, schema, and
  the original callable. Execution wrapping (argument binding, sync/async
  handling, result normalization) is done at call time in _processing.py.

  Args:
    tool: Plain function or callable instance to register as a tool.
    namespace: Optional namespace prefix. If provided, the spec name
      becomes ``namespace:tool_name``.
    name: Optional explicit tool name override. Takes precedence over the
      callable's ``__yoker_name__`` and ``__name__``.

  Returns:
    A fully populated ``ToolSpec``.

  Raises:
    ValueError: If the callable has no inspectable signature, or if the
      resolved name is empty.
  """
  resolved_name = _resolve_name(tool, explicit_name=name)
  description = _resolve_description(tool)
  signature = inspect.signature(tool)

  properties: dict[str, Any] = {}
  required: list[str] = []
  guards: dict[str, GuardType] = {}

  for param_name, param in signature.parameters.items():
    # Skip ctx: ToolContext - it's injected by the executor, not provided by the model
    if _is_context_parameter(param):
      continue

    param_schema, guard_type = _build_parameter_schema(param, param_name)
    properties[param_name] = param_schema
    if guard_type is not None:
      guards[param_name] = guard_type

    if param.default is inspect.Parameter.empty:
      required.append(param_name)

  schema = {
    "type": "function",
    "function": {
      "name": resolved_name,
      "description": description,
      "parameters": {
        "type": "object",
        "properties": properties,
        "required": required,
      },
    },
  }

  return ToolSpec(
    simple_name=resolved_name,
    namespace=namespace,
    description=description,
    schema=schema,
    guards=guards,
    execute=tool,
  )


def _resolve_name(
  tool: Callable[..., Any],
  *,
  explicit_name: str | None,
) -> str:
  """Resolve the tool name from explicit override or callable metadata."""
  resolved: str | None = explicit_name

  if resolved is None:
    resolved = getattr(tool, "__yoker_name__", None)

  if not resolved:
    resolved = getattr(tool, "__name__", None)

  if not resolved:
    # Callable classes expose their class name via type(tool).__name__
    resolved = type(tool).__name__

  if not resolved or resolved == "<lambda>":
    raise ValueError("Could not resolve a tool name from the callable")

  return resolved


def _resolve_description(tool: Callable[..., Any]) -> str:
  """Resolve the tool description from callable metadata."""
  explicit = getattr(tool, "__yoker_description__", None)
  if isinstance(explicit, str):
    return explicit.strip()

  doc = inspect.getdoc(tool)
  if doc:
    return doc.strip().splitlines()[0]

  raise ValueError("A tool needs a description!")


def _build_parameter_schema(
  param: inspect.Parameter,
  param_name: str,
) -> tuple[dict[str, Any], GuardType | None]:
  """Build a JSON-schema property for a single parameter.

  Returns:
    Tuple of (property_schema, guard_type). The guard type is ``None`` for
    non-string parameters or plain strings without an annotation marker.
  """
  annotation = param.annotation
  description = ""
  guard_type: GuardType | None = None

  # Strip Annotated wrapper to find the base type and metadata markers.
  origin = get_origin(annotation)
  args = getattr(annotation, "__args__", ())
  if origin is not None and args:
    if origin is type and len(args) == 1:
      # typing.Type[T] or similar; not currently supported.
      annotation = args[0]
    else:
      metadata = args[1:]
      annotation = args[0]
      marker = _find_marker(metadata)
      if marker is not None:
        description = marker.description
        guard_type = marker.yoker_type

  json_schema: dict[str, Any] = {}

  if description:
    json_schema["description"] = description

  json_type = _python_type_to_json_schema(annotation)
  if json_type is not None:
    json_schema["type"] = json_type

  # Handle Optional[T] by checking if the default is None.
  if param.default is None:
    # Mark optional if the annotation itself is a union containing None.
    if _is_optional(annotation):
      json_schema.setdefault("type", json_type or "string")

  # Warn when a string parameter lacks an annotation marker.
  if json_type == "string" and guard_type is None:
    logger.warning(
      "tool_parameter_missing_yoker_type",
      parameter=param_name,
    )

  return json_schema, guard_type


def _find_marker(metadata: tuple[Any, ...]) -> Text | None:
  """Return the first recognized marker from Annotated metadata."""
  for item in metadata:
    if isinstance(item, Text):
      return item
  return None


def _python_type_to_json_schema(annotation: Any) -> str | None:
  """Map a Python type annotation to a JSON-schema type string."""
  if annotation is inspect.Parameter.empty:
    return None

  # Resolve string forward references where possible.
  if isinstance(annotation, (str, ForwardRef)):
    return None

  # Unwrap Optional / Union[T, None].
  origin = get_origin(annotation)
  args = getattr(annotation, "__args__", ())
  if origin is not None:
    # typing.Optional[T] -> Union[T, None]
    if type(None) in args:
      non_none = [a for a in args if a is not type(None)]
      if len(non_none) == 1:
        return _python_type_to_json_schema(non_none[0])
    # list[T]
    if origin is list:
      return "array"
    # dict[str, T]
    if origin is dict:
      return "object"

  # Direct type mapping.
  return _JSON_SCHEMA_TYPES.get(annotation)


def _is_optional(annotation: Any) -> bool:
  """Return True if the annotation is ``Optional[T]`."""
  origin = get_origin(annotation)
  if origin is None:
    return False
  args = getattr(annotation, "__args__", ())
  return type(None) in args


def _is_context_parameter(param: inspect.Parameter) -> bool:
  """Return True if this parameter is a ToolContext injection point."""
  from yoker.tools.context import ToolContext

  if param.annotation is ToolContext:
    return True
  # Also handle string annotation "ToolContext" or forward reference
  if isinstance(param.annotation, str):
    return param.annotation == "ToolContext"
  # Handle ForwardRef
  if isinstance(param.annotation, ForwardRef):
    return param.annotation.__forward_arg__ == "ToolContext"
  return False


__all__ = [
  "ToolResult",
  "ValidationResult",
  "ToolSpec",
  "build_tool_spec",
]
