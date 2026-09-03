"""Tests for bare-name tool resolution at dispatch time (0.12.0 Tier 1).

Models sometimes emit the simple tool name (e.g. ``list``) instead of the
namespaced schema name (``yoker__list``). Previously this failed with
``Error: Unknown tool 'list'`` — a guaranteed retry loop. Dispatch now
falls back to ``ToolRegistry.resolve()`` (mirroring
``AgentRegistry.resolve()``): one match → dispatch, several → ambiguity
error listing full names, none → not-found error listing available tools.

Covers:
1. ToolRegistry.resolve(): exact key, bare-name unique, ambiguity, missing
2. _run_tool dispatch: bare-name success, ambiguity error, not-found error
"""

from typing import Annotated
from unittest.mock import MagicMock

import pytest

from yoker.tools.annotations import Text
from yoker.tools.registry import ToolRegistry
from yoker.tools.schema import ToolResult, build_tool_spec


def _make_tool(name: str = "list", namespace: str = "yoker"):
  """Build a ToolSpec with the given simple name and namespace."""

  async def my_tool(
    pattern: Annotated[str, Text("Pattern")] = "",
  ) -> ToolResult:
    """A dummy tool."""
    return ToolResult(success=True, result="ok")

  return build_tool_spec(my_tool, namespace=namespace, name=name)


class TestToolRegistryResolve:
  """ToolRegistry.resolve() mirrors AgentRegistry.resolve()."""

  def test_exact_namespaced_key_returns_as_is(self) -> None:
    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    assert registry.resolve("yoker:list") == "yoker:list"

  def test_bare_name_unique_match_resolves(self) -> None:
    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    assert registry.resolve("list") == "yoker:list"

  def test_bare_name_across_namespaces_resolves(self) -> None:
    """A bare name matching a plugin tool resolves to its full key."""
    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    registry.register_all([_make_tool("grep", namespace="plugin_x")], namespace="plugin_x")
    assert registry.resolve("grep") == "plugin_x:grep"

  def test_bare_name_ambiguous_raises_with_full_names(self) -> None:
    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    registry.register_all([_make_tool("list", namespace="plugin_x")], namespace="plugin_x")
    with pytest.raises(ValueError, match="ambiguous") as excinfo:
      registry.resolve("list")
    # Error lists both full namespaced candidates.
    assert "plugin_x:list" in str(excinfo.value)
    assert "yoker:list" in str(excinfo.value)

  def test_namespaced_unknown_returns_none(self) -> None:
    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    assert registry.resolve("yoker:nonexistent") is None
    # A namespaced name never bare-matches.
    assert registry.resolve("other:list") is None

  def test_unknown_bare_name_returns_none(self) -> None:
    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    assert registry.resolve("nonexistent") is None

  def test_simple_name_with_underscores_not_converted(self) -> None:
    """Registry keys use ``:``, so a name without ``:`` is always bare."""
    registry = ToolRegistry()
    registry.register_all([_make_tool("issue_view")], namespace="yoker")
    assert registry.resolve("issue_view") == "yoker:issue_view"


class TestRunToolBareNameDispatch:
  """_run_tool falls back to registry resolution on exact-key miss."""

  def _make_agent(self, registry: ToolRegistry) -> MagicMock:
    agent = MagicMock()
    agent.tools = registry
    return agent

  @pytest.mark.asyncio
  async def test_bare_name_resolves_and_executes(self) -> None:
    """Bare name dispatched as if the namespaced name was used."""
    from yoker.core._processing import _run_tool

    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    agent = self._make_agent(registry)

    result, success, raw = await _run_tool(agent, "list", {"pattern": "x"})

    assert success
    assert "ok" in result
    assert raw is not None

  @pytest.mark.asyncio
  async def test_namespaced_name_still_works_exact(self) -> None:
    """The normal path — exact key — is unchanged."""
    from yoker.core._processing import _run_tool

    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    agent = self._make_agent(registry)

    result, success, raw = await _run_tool(agent, "yoker:list", {"pattern": "x"})

    assert success
    assert "ok" in result

  @pytest.mark.asyncio
  async def test_ambiguous_bare_name_errors_with_candidates(self) -> None:
    """Ambiguity surfaces as a tool error listing the full names."""
    from yoker.core._processing import _run_tool

    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    registry.register_all([_make_tool("list", namespace="plugin_x")], namespace="plugin_x")
    agent = self._make_agent(registry)

    result, success, raw = await _run_tool(agent, "list", {})

    assert not success
    assert raw is None
    assert "ambiguous" in result
    assert "yoker:list" in result
    assert "plugin_x:list" in result

  @pytest.mark.asyncio
  async def test_unknown_tool_error_lists_available_tools(self) -> None:
    """Not-found error now includes the available tool names for self-correction."""
    from yoker.core._processing import _run_tool

    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    agent = self._make_agent(registry)

    result, success, raw = await _run_tool(agent, "nonexistent", {})

    assert not success
    assert raw is None
    assert "Unknown tool 'nonexistent'" in result
    assert "yoker:list" in result

  @pytest.mark.asyncio
  async def test_schema_name_with_double_underscore_resolves(self) -> None:
    """A model echoing the schema name (``yoker__list``) still dispatches:
    the ``__`` → ``:`` conversion happens upstream in
    _execute_single_tool_call, so by _run_tool the name is already
    canonical (``yoker:list``). This test pins the canonical path end-to-end
    from the schema-format name through the conversion helper's logic."""
    from yoker.core._processing import _run_tool

    registry = ToolRegistry()
    registry.register_all([_make_tool("list")], namespace="yoker")
    agent = self._make_agent(registry)

    # Simulate the upstream conversion: yoker__list -> yoker:list
    schema_name = "yoker__list"
    canonical = schema_name.replace("__", ":", 1)
    result, success, raw = await _run_tool(agent, canonical, {"pattern": "x"})

    assert success
    assert "ok" in result
