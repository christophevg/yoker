"""Tests for descriptive invalid-argument errors (0.12.0 Tier 2).

Verifies that tool-call argument binding failures produce schema-driven,
self-correctable error messages instead of generic TypeError text:

1. Missing required arguments -> message names them + lists all expected args.
2. Unknown arguments -> message names them + lists all expected args.
3. Non-schema binding failures -> fall back to the TypeError message.
4. JSON-parse failures -> error includes an "Expected arguments" hint.
5. ``describe_expected_arguments`` renders the schema correctly.
"""

from unittest.mock import MagicMock

import pytest

from yoker.tools.schema import build_tool_spec, describe_expected_arguments

# ---------------------------------------------------------------------------
# Test tools
# ---------------------------------------------------------------------------


def simple_tool(path: str, limit: int = 10) -> str:
  """Return a test result."""
  return f"{path}:{limit}"


def no_args_tool() -> str:
  """Return a test result."""
  return "ok"


def untyped_tool(path, offset) -> str:  # type: ignore[no-untyped-def]
  """Return a test result."""
  return f"{path}:{offset}"


# ---------------------------------------------------------------------------
# describe_expected_arguments
# ---------------------------------------------------------------------------


class TestDescribeExpectedArguments:
  """Schema-driven rendering of a tool's expected arguments."""

  def test_lists_required_and_optional_with_types(self) -> None:
    spec = build_tool_spec(simple_tool)
    rendered = describe_expected_arguments(spec)
    # post_filter is schema-injected for every tool and is model-facing.
    assert rendered == (
      "path (required, string), limit (optional, integer), post_filter (optional, string)"
    )

  def test_no_parameters(self) -> None:
    spec = build_tool_spec(no_args_tool)
    assert describe_expected_arguments(spec) == "post_filter (optional, string)"

  def test_fallback_to_signature_when_schema_malformed(self) -> None:
    spec = build_tool_spec(simple_tool)
    spec.schema = {}  # simulate malformed/absent schema
    rendered = describe_expected_arguments(spec)
    assert rendered == "path (required, string), limit (optional, integer)"

  def test_fallback_handles_untyped_params(self) -> None:
    spec = build_tool_spec(untyped_tool)
    spec.schema = {}
    rendered = describe_expected_arguments(spec)
    # Untyped params resolve to "any" and are required (no defaults).
    assert rendered == "path (required, any), offset (required, any)"

  def test_excludes_post_filter_and_ctx(self) -> None:
    """post_filter is schema-injected, ctx is executor-injected — neither is
    model-facing, so neither appears in the expected-arguments summary."""
    from yoker.tools.context import ToolContext

    def ctx_tool(path: str, ctx: ToolContext) -> str:
      """Return a test result."""
      return path

    spec = build_tool_spec(ctx_tool)
    rendered = describe_expected_arguments(spec)
    # ctx is executor-injected (not in schema), post_filter is schema-injected.
    assert "ctx" not in rendered
    assert "post_filter" in rendered
    assert rendered.startswith("path (required, string)")


# ---------------------------------------------------------------------------
# Binding error classification (_execute_tool)
# ---------------------------------------------------------------------------


class TestBindingErrors:
  """_execute_tool produces self-correctable messages on binding failure."""

  @pytest.mark.asyncio
  async def test_missing_required_argument(self) -> None:
    from yoker.core._processing import _execute_tool

    spec = build_tool_spec(simple_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {})

    assert not result.success
    assert "Invalid arguments for tool 'simple_tool'" in result.error
    assert "missing required argument(s): path" in result.error
    assert (
      "Expected arguments: path (required, string), limit (optional, integer), "
      "post_filter (optional, string)" in result.error
    )

  @pytest.mark.asyncio
  async def test_unknown_argument(self) -> None:
    from yoker.core._processing import _execute_tool

    spec = build_tool_spec(simple_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"path": "a", "limit": 1, "pat": "x"})

    assert not result.success
    assert "unknown argument(s): pat" in result.error
    assert (
      "Expected arguments: path (required, string), limit (optional, integer), "
      "post_filter (optional, string)" in result.error
    )

  @pytest.mark.asyncio
  async def test_missing_and_unknown_combined(self) -> None:
    from yoker.core._processing import _execute_tool

    spec = build_tool_spec(simple_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"pat": "x"})

    assert not result.success
    assert "missing required argument(s): path" in result.error
    assert "unknown argument(s): pat" in result.error

  @pytest.mark.asyncio
  async def test_non_schema_failure_falls_back_to_typeerror(self) -> None:
    """Multiple values for a parameter is not a missing/unknown failure —
    the original TypeError detail is preserved."""
    from yoker.core._processing import _execute_tool

    agent = MagicMock()

    # 'path' provided both positionally and by keyword is not possible via
    # kwargs-only binding; use a duplicate-key dict instead — Python dedups
    # those, so simulate via a spec whose schema is intact but a signature
    # that raises a non-missing/unknown TypeError.
    def tool(path: str) -> str:
      """Return a test result."""
      return path

    tool_spec = build_tool_spec(tool)
    # Corrupt the schema so classification falls back but binding still fails
    # with a generic TypeError (e.g. unbindable value).
    tool_spec.schema["function"]["parameters"]["required"] = []
    result = await _execute_tool(tool_spec, agent, {"path": "a", "extra": "b"})

    assert not result.success
    assert "Invalid arguments for tool 'tool'" in result.error
    assert "unknown argument(s): extra" in result.error
    assert "Expected arguments: " in result.error

  @pytest.mark.asyncio
  async def test_valid_call_unaffected(self) -> None:
    from yoker.core._processing import _execute_tool

    spec = build_tool_spec(simple_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"path": "a", "limit": 3})

    assert result.success
    assert result.result == "a:3"


# ---------------------------------------------------------------------------
# JSON-parse failure hint (_execute_single_tool_call)
# ---------------------------------------------------------------------------


class TestParseErrorHint:
  """JSON-parse failures include an expected-arguments hint when resolvable."""

  @pytest.mark.asyncio
  async def test_parse_error_includes_expected_arguments(self) -> None:
    from yoker.core._processing import _build_tool_call, _execute_single_tool_call
    from yoker.events.types import ToolResultEvent

    captured: dict[str, str] = {}

    async def handler(event: object) -> None:
      if isinstance(event, ToolResultEvent):
        captured["result"] = str(event.result)

    def simple_tool(path: str) -> str:
      """Return a test result."""
      return path

    spec = build_tool_spec(simple_tool)
    agent = MagicMock()
    agent.tools.get.return_value = spec
    agent.tools.resolve.return_value = None
    agent._event_handlers = [handler]

    # Build a tool call whose arguments are unparseable JSON.
    call = _build_tool_call({"id": "1", "name": "yoker__simple_tool", "arguments_json": "{broken"})
    assert getattr(call, "parse_error", None)

    await _execute_single_tool_call(agent, call)

    assert "result" in captured
    assert "Failed to parse tool arguments as JSON" in captured["result"]
    assert "Expected arguments: path (required, string)" in captured["result"]

  @pytest.mark.asyncio
  async def test_parse_error_without_resolvable_tool_has_no_hint(self) -> None:
    from yoker.core._processing import _build_tool_call, _execute_single_tool_call
    from yoker.events.types import ToolResultEvent

    captured: dict[str, str] = {}

    async def handler(event: object) -> None:
      if isinstance(event, ToolResultEvent):
        captured["result"] = str(event.result)

    agent = MagicMock()
    agent.tools.get.return_value = None
    agent.tools.resolve.return_value = None
    agent._event_handlers = [handler]

    call = _build_tool_call({"id": "1", "name": "yoker__mystery", "arguments_json": "{broken"})
    assert getattr(call, "parse_error", None)

    await _execute_single_tool_call(agent, call)

    assert "Failed to parse tool arguments as JSON" in captured["result"]
    assert "Expected arguments:" not in captured["result"]
