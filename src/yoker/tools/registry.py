"""Tool registry for managing and dispatching Yoker tools.

Provides ``ToolRegistry``, a thin ``UserDict`` subclass that accepts
any callable as a tool and stores the resulting ``ToolSpec``.
"""

from collections import UserDict
from collections.abc import Callable
from typing import Any

from structlog import get_logger

from yoker.tools.schema import ToolSpec, build_tool_spec

log = get_logger(__name__)


class ToolRegistry(UserDict[str, ToolSpec]):
  """Registry for managing available tools.

  Tools are registered by passing a plain function or callable class
  instance. The registry stores the resulting ``ToolSpec`` and can be
  used like a normal dictionary.

  Example:
    registry = ToolRegistry()
    registry.register(read_file)
    spec = registry["read_file"]
    schemas = [s.schema for s in registry.values()]
  """

  def register(
    self,
    tool: Callable[..., Any],
    *,
    namespace: str | None = None,
    name: str | None = None,
  ) -> ToolSpec:
    """Register a callable as a tool.

    Args:
      tool: Function or callable class instance to register.
      namespace: Optional namespace prefix for the tool name.
      name: Optional explicit tool name override.

    Returns:
      The ``ToolSpec`` that was registered.

    Raises:
      ValueError: If a tool with the same name is already registered.
    """
    spec = build_tool_spec(tool, namespace=namespace, name=name)
    if spec.name in self.data:
      raise ValueError(f"Tool '{spec.name}' is already registered")
    self.data[spec.name] = spec
    log.info("tool_registered", tool=spec.name)
    return spec

  @property
  def tools(self) -> list[ToolSpec]:
    """Return all registered tool specs sorted by name."""
    return sorted(self.data.values(), key=lambda spec: spec.name)

  def find_tools(self, namespace: str) -> list[ToolSpec]:
    return [tool for tool in self.tools if tool.namespace == namespace]

  @property
  def namespaces(self) -> list[str]:
    """Return all registered tool namespaces sorted alphabetically."""
    return sorted({tool.namespace for tool in self.data.values()})

  @property
  def names(self) -> list[str]:
    """Return all registered tool names sorted alphabetically."""
    return sorted(self.data.keys())


__all__ = ["ToolRegistry"]
