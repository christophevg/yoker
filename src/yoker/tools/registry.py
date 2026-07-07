"""Tool registry for managing and dispatching Yoker tools.

Provides ``ToolRegistry``, a thin ``UserDict`` subclass that accepts
any callable as a tool and stores the resulting ``ToolSpec``.
"""

from collections import UserDict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from structlog import get_logger

from yoker.tools.schema import ToolSpec, build_tool_spec

if TYPE_CHECKING:
  from yoker.config import Config
  from yoker.plugins import PluginComponents

logger = get_logger(__name__)

# Built-in yoker tools gated by config.tools.<name>.enabled
_TOOL_CONFIG_MAP = {
  "list": "list",
  "read": "read",
  "write": "write",
  "update": "update",
  "search": "search",
  "agent": "agent",
  "git": "git",
  "mkdir": "mkdir",
  "existence": "existence",
  "websearch": "websearch",
  "webfetch": "webfetch",
  "skill": "skill",
}

# Tools that additionally require a backend API key
_API_KEY_REQUIRED_TOOLS = {"websearch", "webfetch"}


def _filter_enabled_tools(
  tools: list[ToolSpec],
  config: "Config",
  namespace: str,
) -> list[ToolSpec]:
  """Filter built-in yoker tools by their enabled flag in config.

  Plugin tools (non-yoker namespace) pass through unchanged. For yoker
  tools, each tool's ``simple_name`` maps to ``config.tools.<name>.enabled``;
  disabled tools are dropped. ``websearch``/``webfetch`` additionally
  require ``config.backend.config.api_key``.
  """
  if namespace != "yoker":
    return tools

  enabled: list[ToolSpec] = []
  for spec in tools:
    name = spec.simple_name
    if name is None:
      continue
    config_attr = _TOOL_CONFIG_MAP.get(name)
    if config_attr is None:
      enabled.append(spec)
      continue
    tool_config = getattr(config.tools, config_attr, None)
    if tool_config is None:
      enabled.append(spec)
      continue
    if not tool_config.enabled:
      logger.info("tool_disabled_by_config", tool=name, namespace=namespace)
      continue
    if name in _API_KEY_REQUIRED_TOOLS and not config.backend.config.api_key:
      logger.info("tool_disabled_no_api_key", tool=name, namespace=namespace)
      continue
    enabled.append(spec)
  return enabled


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
    logger.info("tool_registered", tool=spec.name)
    return spec

  @property
  def tools(self) -> list[ToolSpec]:
    """Return all registered tool specs sorted by name."""
    return sorted(self.data.values(), key=lambda spec: spec.name)

  def register_all(self, specs: list[ToolSpec], namespace: str) -> None:
    """Register pre-built ToolSpec objects under a namespace.

    Mirrors :meth:`AgentRegistry.register_all`. Specs are already
    namespaced from plugin load.
    """
    logger.info("register_tools_started", namespace=namespace, count=len(specs))
    for spec in specs:
      if spec.name in self.data:
        raise ValueError(f"Tool '{spec.name}' is already registered")
      self.data[spec.name] = spec
      logger.info("tool_registered", name=spec.name, namespace=namespace)

  def register_plugin_tools(
    self,
    plugins: list["PluginComponents"],
    config: "Config",
  ) -> None:
    """Register tools from clean plugin list, applying config-level filtering.

    Consumes the generator output of :func:`load_plugins`. Security and
    global-enabled gating happen in ``load_plugins``; only tool-level
    enabled/api-key filtering happens here.
    """
    for plugin in plugins:
      if not plugin.tools:
        continue
      enabled = _filter_enabled_tools(plugin.tools, config, plugin.source)
      self.register_all(enabled, namespace=plugin.source)
      logger.info("tools_registered", package=plugin.source, count=len(enabled))

  def get_schemas(self) -> list[dict[str, Any]]:
    """Return schemas for all registered tools.

    Returns:
      List of tool schemas in Ollama function format.
    """
    return [spec.schema for spec in self.tools]

  def find_tools(self, namespace: str) -> list[ToolSpec]:
    return [tool for tool in self.tools if tool.namespace == namespace]

  @property
  def namespaces(self) -> list[str]:
    """Return all registered tool namespaces sorted alphabetically."""
    return sorted([tool.namespace for tool in self.data.values() if tool.namespace])

  @property
  def names(self) -> list[str]:
    """Return all registered tool names sorted alphabetically."""
    return sorted(self.data.keys())


__all__ = ["ToolRegistry"]
