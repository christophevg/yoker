"""Tests for schema-aware per-value argument coercion at dispatch time.

Some models/backends (notably Ollama, ollama/ollama#6155) string-encode
object/array parameters, e.g. ``{"env_vars": "{\\"TEST\\": \\"foo\\"}"}``.
Previously the Ollama backend parsed any string starting with ``{`` or
``[``, which destroyed legitimate JSON-looking strings for string-typed
parameters (e.g. ``write(content='{"key": "value"}')`` → dict →
"Invalid content parameter" retry loop).

Per-value coercion now lives in the execution layer where the tool's
parameter schema is available: a string value is parsed into a dict/list
only when the schema declares the parameter as ``object``/``array`` AND
the value parses as a JSON object/array.

Covers:
1. Coercion when schema type matches (object / array).
2. Verbatim pass-through for string-typed parameters (the write-tool bug).
3. Pass-through for malformed JSON, quoted scalars, non-string values.
4. Robustness: missing/malformed schema, no mutation of the input dict.
5. End-to-end through _run_tool (env_vars rescued for make).
"""

from typing import Annotated
from unittest.mock import MagicMock

import pytest

from yoker.core._processing import _coerce_schema_aware_args
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


def _array_tool():
  async def my_tool(
    items: Annotated[list[str], Text("Items")] | None = None,
  ) -> ToolResult:
    """A dummy tool with an optional array parameter."""
    return ToolResult(success=True, result="ok")

  return build_tool_spec(my_tool, namespace="yoker", name="batch")


class TestCoerceSchemaAwareArgs:
  """Unit tests for _coerce_schema_aware_args."""

  def test_object_typed_param_string_dict_is_coerced(self) -> None:
    spec = _object_tool()
    result = _coerce_schema_aware_args(spec, {"target": "test", "env_vars": '{"TEST": "foo"}'})
    assert result["env_vars"] == {"TEST": "foo"}
    assert result["target"] == "test"

  def test_array_typed_param_string_list_is_coerced(self) -> None:
    spec = _array_tool()
    result = _coerce_schema_aware_args(spec, {"items": '["a", "b"]'})
    assert result["items"] == ["a", "b"]

  def test_string_typed_param_json_string_stays_verbatim(self) -> None:
    """The write-tool regression: JSON-looking content is legitimate data."""
    spec = _string_tool()
    result = _coerce_schema_aware_args(
      spec, {"path": "/tmp/data.json", "content": '{"key": "value"}'}
    )
    assert result["content"] == '{"key": "value"}'

  def test_malformed_json_stays_verbatim(self) -> None:
    """Unparseable string for an object-typed param passes through unchanged."""
    spec = _object_tool()
    result = _coerce_schema_aware_args(spec, {"target": "t", "env_vars": "{not json"})
    assert result["env_vars"] == "{not json"

  def test_quoted_scalar_stays_verbatim(self) -> None:
    """A JSON scalar string is not an object/array — keep the string."""
    spec = _object_tool()
    result = _coerce_schema_aware_args(spec, {"target": "t", "env_vars": '"123"'})
    assert result["env_vars"] == '"123"'

  def test_non_string_value_passes_through(self) -> None:
    spec = _object_tool()
    result = _coerce_schema_aware_args(spec, {"target": "t", "env_vars": {"TEST": "foo"}})
    assert result["env_vars"] == {"TEST": "foo"}

  def test_unknown_param_not_in_schema_passes_through(self) -> None:
    spec = _string_tool()
    result = _coerce_schema_aware_args(spec, {"unknown": '{"a": 1}'})
    assert result["unknown"] == '{"a": 1}'

  def test_missing_schema_is_noop(self) -> None:
    """A malformed/absent schema leaves arguments untouched."""
    spec = _object_tool()
    object.__setattr__(spec, "schema", {})
    args = {"target": "t", "env_vars": '{"TEST": "foo"}'}
    result = _coerce_schema_aware_args(spec, args)
    assert result == args

  def test_input_dict_not_mutated(self) -> None:
    spec = _object_tool()
    args = {"target": "t", "env_vars": '{"TEST": "foo"}'}
    _coerce_schema_aware_args(spec, args)
    assert args["env_vars"] == '{"TEST": "foo"}'

  def test_no_coercion_returns_original_dict_object(self) -> None:
    """The no-change fast path returns the same object, not a copy."""
    spec = _string_tool()
    args = {"path": "/x", "content": "plain"}
    assert _coerce_schema_aware_args(spec, args) is args


class TestRunToolSchemaAwareCoercion:
  """_run_tool applies the coercion after spec resolution, before execution."""

  def _make_agent(self, spec) -> MagicMock:
    registry = ToolRegistry()
    registry.register_all([spec], namespace="yoker")
    agent = MagicMock()
    agent.tools = registry
    return agent

  @pytest.mark.asyncio
  async def test_run_tool_coerces_object_param_for_object_tool(self) -> None:
    """make-like tool: string-encoded env_vars reaches the tool as a dict."""
    received: dict = {}

    async def make_tool(
      target: Annotated[str, Text("Target")],
      env_vars: Annotated[dict[str, str], Text("Env vars")] | None = None,
    ) -> ToolResult:
      """A dummy make-like tool."""
      received["env_vars"] = env_vars
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(make_tool, namespace="yoker", name="make")
    agent = self._make_agent(spec)

    result, success, _ = await _run_tool_call(
      agent, "yoker:make", {"target": "test", "env_vars": '{"T": "1"}'}
    )

    assert success
    assert result == "ok"
    assert received["env_vars"] == {"T": "1"}

  @pytest.mark.asyncio
  async def test_run_tool_preserves_json_string_for_string_tool(self) -> None:
    """write-like tool: JSON-looking content reaches the tool as a string."""
    received: dict = {}

    async def write_tool(
      path: Annotated[str, Text("Path")],
      content: Annotated[str, Text("Content")],
    ) -> ToolResult:
      """A dummy write-like tool."""
      received["content"] = content
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(write_tool, namespace="yoker", name="write")
    agent = self._make_agent(spec)

    result, success, _ = await _run_tool_call(
      agent, "yoker:write", {"path": "/tmp/data.json", "content": '{"key": "value"}'}
    )

    assert success
    assert result == "ok"
    assert received["content"] == '{"key": "value"}'

  @pytest.mark.asyncio
  async def test_run_tool_coerces_real_make_tool_env_vars(self) -> None:
    """End-to-end with the REAL make tool: string-encoded env_vars is coerced.

    Pairs with the schema fix (test_tool_schema_diagnostic.py): the real
    make tool's schema now declares env_vars as object, so the coercion
    fires at dispatch and the tool receives a dict.
    """
    from yoker.builtin.make import make as real_make

    spec = build_tool_spec(real_make, namespace="yoker", name="make")
    coerced = _coerce_schema_aware_args(spec, {"target": "check", "env_vars": '{"T": "1"}'})
    assert coerced["env_vars"] == {"T": "1"}


async def _run_tool_call(
  agent: MagicMock, tool_name: str, tool_args: dict
) -> tuple[str, bool, object]:
  """Invoke _run_tool with a fully-qualified tool name."""
  from yoker.core._processing import _run_tool

  return await _run_tool(agent, tool_name, tool_args)


if __name__ == "__main__":
  pytest.main([__file__])
