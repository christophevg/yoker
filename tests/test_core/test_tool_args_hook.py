"""Tests for the host-side tool-argument hook (Agent._tool_args_hook).

Covers the contract end to end:

1. Unit: _apply_tool_args_hook (sync/async, replacement, None passthrough,
   exception fail-safe, invalid-return fail-safe, missing attribute).
2. Hook ordering: the hook runs BEFORE schema-aware coercion, so injected
   string-encoded values get the same normalizing treatment as
   model-provided ones (end-to-end through _run_tool).
3. Constructor kwarg: Agent(tool_args_hook=...) stores the attribute.
"""

from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest

from yoker.core._processing import _apply_tool_args_hook, _coerce_schema_aware_args, _run_tool
from yoker.core.thinking import ThinkingMode
from yoker.tools.annotations import Text
from yoker.tools.registry import ToolRegistry
from yoker.tools.schema import ToolResult, build_tool_spec


def _string_tool():
  async def my_tool(
    path: Annotated[str, Text("Path")],
    content: Annotated[str, Text("Content")],
  ) -> ToolResult:
    """A dummy tool with two string parameters."""
    return ToolResult(success=True, result="ok")

  return build_tool_spec(my_tool, namespace="yoker", name="write")


def _object_tool():
  async def my_tool(
    target: Annotated[str, Text("Target")],
    env_vars: Annotated[dict[str, str], Text("Env vars")] | None = None,
  ) -> ToolResult:
    """A dummy tool with an optional object parameter."""
    return ToolResult(success=True, result="ok")

  return build_tool_spec(my_tool, namespace="yoker", name="make")


def _recording_tool(received: dict):
  """Build a make-like spec whose tool records the kwargs it received."""

  async def my_tool(
    target: Annotated[str, Text("Target")],
    env_vars: Annotated[dict[str, str], Text("Env vars")] | None = None,
  ) -> ToolResult:
    """Recording tool."""
    received["kwargs"] = {"target": target, "env_vars": env_vars}
    return ToolResult(success=True, result="ok")

  return build_tool_spec(my_tool, namespace="yoker", name="make")


def _mock_agent(spec) -> MagicMock:
  """Minimal agent mock for _run_tool, like test_schema_aware_coercion."""
  registry = ToolRegistry()
  registry.register_all([spec], namespace="yoker")
  agent = MagicMock()
  agent.tools = registry
  agent._guardrails = {}
  agent._approval_handler = None
  agent._tool_args_hook = None
  agent.config.logging.include_permission_checks = False
  return agent


class TestApplyToolArgsHook:
  """Unit tests for _apply_tool_args_hook."""

  @pytest.mark.asyncio
  async def test_no_hook_attribute_returns_original(self) -> None:
    spec = _string_tool()
    agent = MagicMock(spec=[])  # no _tool_args_hook attribute at all
    args = {"path": "a", "content": "b"}
    result = await _apply_tool_args_hook(agent, spec, args)
    assert result is args

  @pytest.mark.asyncio
  async def test_none_hook_returns_original(self) -> None:
    spec = _string_tool()
    agent = MagicMock()
    agent._tool_args_hook = None
    args = {"path": "a", "content": "b"}
    result = await _apply_tool_args_hook(agent, spec, args)
    assert result is args

  @pytest.mark.asyncio
  async def test_sync_hook_replacement(self) -> None:
    spec = _string_tool()
    agent = MagicMock()
    agent._tool_args_hook = lambda name, args: {**args, "content": "injected"}
    result = await _apply_tool_args_hook(agent, spec, {"path": "a", "content": "b"})
    assert result == {"path": "a", "content": "injected"}

  @pytest.mark.asyncio
  async def test_async_hook_replacement(self) -> None:
    spec = _string_tool()

    async def hook(name: str, args: dict) -> dict:
      return {**args, "content": "injected"}

    agent = MagicMock()
    agent._tool_args_hook = hook
    result = await _apply_tool_args_hook(agent, spec, {"path": "a", "content": "b"})
    assert result == {"path": "a", "content": "injected"}

  @pytest.mark.asyncio
  async def test_hook_none_passthrough(self) -> None:
    """Returning None keeps the original arguments (the injection veto)."""
    spec = _string_tool()
    agent = MagicMock()
    agent._tool_args_hook = lambda name, args: None
    args = {"path": "a", "content": "b"}
    result = await _apply_tool_args_hook(agent, spec, args)
    assert result is args

  @pytest.mark.asyncio
  async def test_hook_in_place_mutation_visible(self) -> None:
    """A hook may mutate the dict in place and return None."""
    spec = _string_tool()

    def hook(name: str, args: dict) -> None:
      args["content"] = "mutated"

    agent = MagicMock()
    agent._tool_args_hook = hook
    args = {"path": "a", "content": "b"}
    result = await _apply_tool_args_hook(agent, spec, args)
    assert result is args
    assert result == {"path": "a", "content": "mutated"}

  @pytest.mark.asyncio
  async def test_hook_receives_canonical_name(self) -> None:
    """The hook gets the namespaced tool name, e.g. 'yoker:write'."""
    spec = _string_tool()
    seen: list[str] = []

    def hook(name: str, args: dict) -> None:
      seen.append(name)

    agent = MagicMock()
    agent._tool_args_hook = hook
    await _apply_tool_args_hook(agent, spec, {"path": "a", "content": "b"})
    assert seen == ["yoker:write"]

  @pytest.mark.asyncio
  async def test_hook_exception_is_fail_safe(self) -> None:
    """A raising hook never breaks the tool call: original args pass."""
    spec = _string_tool()
    agent = MagicMock()
    agent._tool_args_hook = MagicMock(side_effect=RuntimeError("boom"))
    args = {"path": "a", "content": "b"}
    result = await _apply_tool_args_hook(agent, spec, args)
    assert result is args

  @pytest.mark.asyncio
  async def test_hook_non_dict_return_is_fail_safe(self) -> None:
    spec = _string_tool()
    agent = MagicMock()
    agent._tool_args_hook = lambda name, args: "not a dict"
    args = {"path": "a", "content": "b"}
    result = await _apply_tool_args_hook(agent, spec, args)
    assert result is args


class TestToolArgsHookOrdering:
  """The hook runs BEFORE normalization: injected values receive the same
  coercing/expanding/validation treatment as model-provided ones."""

  @pytest.mark.asyncio
  async def test_injected_string_object_param_is_coerced(self) -> None:
    """Hook-injected string for an object-typed param is coerced to a dict
    before execution (end-to-end through _run_tool)."""
    received: dict = {}
    spec = _recording_tool(received)
    agent = _mock_agent(spec)
    agent._tool_args_hook = lambda name, args: {**args, "env_vars": '{"T": "1"}'}

    result, success, _ = await _run_tool(agent, "yoker:make", {"target": "t"})

    assert success
    assert result == "ok"
    assert received["kwargs"]["env_vars"] == {"T": "1"}

  @pytest.mark.asyncio
  async def test_model_args_coerced_when_hook_passes_none(self) -> None:
    """With the hook returning None, model-provided args normalize as usual."""
    received: dict = {}
    spec = _recording_tool(received)
    agent = _mock_agent(spec)
    agent._tool_args_hook = lambda name, args: None

    result, success, _ = await _run_tool(
      agent, "yoker:make", {"target": "t", "env_vars": '{"T": "1"}'}
    )

    assert success
    assert received["kwargs"]["env_vars"] == {"T": "1"}

  @pytest.mark.asyncio
  async def test_hook_not_run_for_unknown_tool(self) -> None:
    """An unknown tool fails with the standard error; hook never fires."""
    ran: list[str] = []
    spec = _string_tool()
    agent = _mock_agent(spec)

    def hook(name: str, args: dict) -> None:
      ran.append(name)

    agent._tool_args_hook = hook
    result, success, _ = await _run_tool(agent, "yoker:no_such_tool", {})

    assert not success
    assert "Unknown tool" in result
    assert ran == []


class TestHookRunsBeforeCoercion:
  """Ordering proof at the unit level: the hook sees RAW model args, the
  coercion sees hook-injected values."""

  @pytest.mark.asyncio
  async def test_hook_sees_raw_args_before_coercion(self) -> None:
    spec = _object_tool()
    seen_args: list[dict] = []

    def hook(name: str, args: dict) -> None:
      seen_args.append(dict(args))

    agent = MagicMock()
    agent._tool_args_hook = hook
    await _apply_tool_args_hook(agent, spec, {"target": "t", "env_vars": '{"T": "1"}'})
    # Hook observed the raw string, untouched by coercion.
    assert seen_args == [{"target": "t", "env_vars": '{"T": "1"}'}]

    # And a value injected into that shape would then be coerced:
    coerced = _coerce_schema_aware_args(spec, {"target": "t", "env_vars": '{"T": "1"}'})
    assert coerced["env_vars"] == {"T": "1"}


class TestAgentConstructorKwarg:
  """Agent(tool_args_hook=...) stores the attribute; default is None."""

  def _agent(self, config: Any, **kwargs: Any) -> Any:
    from yoker.core import Agent  # deferred: pulls the full config stack

    return Agent(
      config=config,
      thinking_mode=ThinkingMode.OFF,
      parse_cli_args=False,
      console_logging=False,
      backend=MagicMock(),
      **kwargs,
    )

  @pytest.fixture()
  def agent_config(self, tmp_path: Any) -> Any:
    """Config shaped for Agent.__init__ (mirrors other core-agent tests)."""
    from yoker.config import Config

    config = Config()
    config.enabled = True
    config.tools = MagicMock()
    return config

  @pytest.mark.asyncio
  async def test_constructor_stores_hook(self, agent_config: Any) -> None:
    def hook(name: str, args: dict) -> None:
      return None

    agent = self._agent(agent_config, tool_args_hook=hook)
    assert agent._tool_args_hook is hook

  @pytest.mark.asyncio
  async def test_constructor_default_is_none(self, agent_config: Any) -> None:
    agent = self._agent(agent_config)
    assert agent._tool_args_hook is None


if __name__ == "__main__":
  pytest.main([__file__])
