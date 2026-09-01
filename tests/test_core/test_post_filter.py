"""Tests for the post-filter feature on all tool outputs.

The post_filter parameter is auto-injected into every tool's schema. It
allows the LLM to specify a regex pattern to filter tool output
line-by-line before it is returned, reducing context growth.

These tests verify:
1. post_filter appears in every tool's schema
2. post_filter is extracted before binding to the tool function
3. post_filter correctly filters output lines
4. post_filter handles edge cases (no matches, invalid regex, empty filter)
5. post_filter does not interfere with tool execution on error results
"""

import json
from typing import Annotated
from unittest.mock import MagicMock

import pytest

from yoker.tools.annotations import ReadPath as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult, build_tool_spec

# ---------------------------------------------------------------------------
# Schema injection tests
# ---------------------------------------------------------------------------


class TestPostFilterInSchema:
  """Verify post_filter is auto-injected into every tool's schema."""

  def test_post_filter_present_in_schema(self) -> None:
    """post_filter appears in the properties of a simple tool."""

    async def my_tool(
      path: Annotated[str, PathArg("File path")],
    ) -> ToolResult:
      """Read a file and return its contents."""
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(my_tool)
    props = spec.schema["function"]["parameters"]["properties"]
    assert "post_filter" in props
    assert props["post_filter"]["type"] == "string"
    assert "filter" in props["post_filter"]["description"].lower()

  def test_post_filter_not_in_required(self) -> None:
    """post_filter is optional — never in the required list."""

    async def my_tool(
      path: Annotated[str, PathArg("File path")],
    ) -> ToolResult:
      """Read a file and return its contents."""
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(my_tool)
    required = spec.schema["function"]["parameters"]["required"]
    assert "post_filter" not in required

  def test_post_filter_present_with_namespace(self) -> None:
    """post_filter appears even with a namespace prefix."""

    async def my_tool(
      path: Annotated[str, PathArg("File path")],
    ) -> ToolResult:
      """Read a file and return its contents."""
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(my_tool, namespace="yoker")
    props = spec.schema["function"]["parameters"]["properties"]
    assert "post_filter" in props

  def test_post_filter_description_warns_on_substring_matching(self) -> None:
    """The injected description warns about substring false-positives (#60 A2)."""

    async def my_tool() -> ToolResult:
      """Simple tool."""
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(my_tool)
    description = spec.schema["function"]["parameters"]["properties"]["post_filter"]["description"]
    assert "substring" in description
    assert "bypassed" in description
    assert "number prefix" in description

  def test_post_filter_present_on_tool_with_many_params(self) -> None:
    """post_filter appears alongside many existing parameters."""

    async def complex_tool(
      path: Annotated[str, PathArg("File path")],
      pattern: Annotated[str, Text("Search pattern")] = "",
      max_results: int | None = None,
      case_insensitive: bool = False,
    ) -> ToolResult:
      """Search for patterns in files."""
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(complex_tool)
    props = spec.schema["function"]["parameters"]["properties"]
    assert "post_filter" in props
    # Ensure existing params are still there
    assert "path" in props
    assert "pattern" in props
    assert "max_results" in props
    assert "case_insensitive" in props


# ---------------------------------------------------------------------------
# Post-filter execution tests
# ---------------------------------------------------------------------------


class TestPostFilterExecution:
  """Verify post_filter is applied correctly during tool execution."""

  @pytest.mark.asyncio
  async def test_post_filter_keeps_matching_lines(self) -> None:
    """Only lines matching the pattern are returned."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(
        success=True,
        result="line1: error something\nline2: all good\nline3: warning here",
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "error|warning"})

    assert result.success
    assert "line1: error something" in result.result
    assert "line3: warning here" in result.result
    assert "line2: all good" not in result.result
    assert "[post_filter:" in result.result
    # #60: the zero-match hint only appears when nothing matched.
    assert "Hint:" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_all_lines_match_returns_unfiltered(self) -> None:
    """When all lines match, no filtering is applied (no summary appended)."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(success=True, result="hello world\nfoo bar")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": ".*"})

    assert result.success
    assert result.result == "hello world\nfoo bar"
    assert "[post_filter:" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_no_matches_returns_empty_with_summary(self) -> None:
    """When no lines match, empty content with summary is returned."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(success=True, result="line1\nline2\nline3")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "nonexistent"})

    assert result.success
    assert "line1" not in result.result
    assert "line2" not in result.result
    assert "line3" not in result.result
    assert "[post_filter: 0/3 lines matched" in result.result
    # #60: zero-match output carries a hint explaining the two known pitfalls.
    assert "substring" in result.result
    assert "line-number prefix" in result.result

  @pytest.mark.asyncio
  async def test_post_filter_not_provided_returns_full_output(self) -> None:
    """When post_filter is not provided, full output is returned."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(success=True, result="line1\nline2\nline3")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {})

    assert result.success
    assert result.result == "line1\nline2\nline3"

  @pytest.mark.asyncio
  async def test_post_filter_empty_string_returns_full_output(self) -> None:
    """Empty post_filter string means no filtering."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(success=True, result="line1\nline2")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": ""})

    assert result.success
    assert result.result == "line1\nline2"

  @pytest.mark.asyncio
  async def test_post_filter_invalid_regex_returns_unfiltered(self) -> None:
    """Invalid regex pattern returns original output unchanged."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(success=True, result="line1\nline2")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "[invalid"})

    assert result.success
    assert result.result == "line1\nline2"
    assert "[post_filter:" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_does_not_reach_tool_function(self) -> None:
    """post_filter is extracted before binding — the tool function never sees it."""
    from yoker.core._processing import _execute_tool

    received_args: dict = {}

    async def my_tool(
      path: Annotated[str, PathArg("File path")],
    ) -> ToolResult:
      """Read a file."""
      received_args["path"] = path
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"path": "/tmp/test", "post_filter": "ok"})

    assert result.success
    assert received_args["path"] == "/tmp/test"
    # The tool function should not receive post_filter as a kwarg
    assert "post_filter" not in received_args

  @pytest.mark.asyncio
  async def test_post_filter_on_error_result_filters_error(self) -> None:
    """post_filter IS applied to error results (e.g. make tool failures).

    Tools like make put combined stdout+stderr in the error field on failure.
    The LLM needs to filter this to find relevant lines. Only errors with
    more than 3 lines are filtered — short tool-level diagnostics are
    preserved in full.
    """
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return an error with multiple lines (like make tool output)."""
      return ToolResult(
        success=False,
        error=(
          "line1: error something\n"
          "line2: all good\n"
          "line3: FAIL here\n"
          "line4: more output\n"
          "line5: another line"
        ),
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "error|FAIL"})

    assert not result.success
    assert "line1: error something" in (result.error or "")
    assert "line3: FAIL here" in (result.error or "")
    assert "line2: all good" not in (result.error or "")
    assert "[post_filter:" in (result.error or "")

  @pytest.mark.asyncio
  async def test_post_filter_preserves_content_metadata(self) -> None:
    """post_filter does not strip content_metadata from the result."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a result with metadata."""
      return ToolResult(
        success=True,
        result="line1: error\nline2: ok",
        content_metadata={"operation": "read", "path": "/tmp/test"},
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "error"})

    assert result.success
    assert "line1: error" in result.result
    assert "line2: ok" not in result.result
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "read"

  @pytest.mark.asyncio
  async def test_post_filter_filters_content_metadata_content(self) -> None:
    """post_filter also filters content_metadata.content so the UI display
    matches what the LLM receives. Without this, the terminal shows full
    unfiltered output while the LLM only sees filtered lines."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a result with content metadata mirroring the result."""
      return ToolResult(
        success=True,
        result="line1: error\nline2: ok\nline3: error here",
        content_metadata={
          "operation": "github",
          "path": "default",
          "content_type": "text/plain",
          "content": "line1: error\nline2: ok\nline3: error here",
          "metadata": {"returncode": 0},
        },
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "error"})

    assert result.success
    # result.result is filtered
    assert "line1: error" in result.result
    assert "line3: error here" in result.result
    assert "line2: ok" not in result.result
    # content_metadata.content is also filtered
    assert result.content_metadata is not None
    md_content = result.content_metadata.get("content", "")
    assert "line1: error" in md_content
    assert "line3: error here" in md_content
    assert "line2: ok" not in md_content

  @pytest.mark.asyncio
  async def test_post_filter_case_sensitive_by_default(self) -> None:
    """post_filter regex is case-sensitive by default."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return mixed-case lines."""
      return ToolResult(
        success=True,
        result="Error: something\nerror: lowercase\nERROR: uppercase",
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "Error"})

    assert result.success
    assert "Error: something" in result.result
    assert "error: lowercase" not in result.result
    assert "ERROR: uppercase" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_case_insensitive_with_regex_flag(self) -> None:
    """post_filter supports case-insensitive matching via (?i) regex flag."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return mixed-case lines."""
      return ToolResult(
        success=True,
        result="Error: something\nerror: lowercase\nERROR: uppercase",
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "(?i)error"})

    assert result.success
    assert "Error: something" in result.result
    assert "error: lowercase" in result.result
    assert "ERROR: uppercase" in result.result

  @pytest.mark.asyncio
  async def test_post_filter_with_tool_taking_ctx(self) -> None:
    """post_filter works with tools that expect ToolContext injection."""
    from yoker.core._processing import _execute_tool

    async def my_tool(
      path: Annotated[str, PathArg("File path")],
      ctx: ToolContext,
    ) -> ToolResult:
      """Read a file with context."""
      return ToolResult(success=True, result="error line\nok line")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=MagicMock())
    agent.config.tools_shared = MagicMock()
    agent._tool_backends = {}

    result = await _execute_tool(spec, agent, {"path": "/tmp/test", "post_filter": "error"})

    assert result.success
    assert "error line" in result.result
    assert "ok line" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_single_line_output(self) -> None:
    """post_filter works on single-line output."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a single line."""
      return ToolResult(success=True, result="just one line")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "one"})

    assert result.success
    assert "just one line" in result.result
    # All lines matched — no summary appended
    assert "[post_filter:" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_with_regex_anchors(self) -> None:
    """post_filter supports regex anchors like ^ and $."""
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return import lines."""
      return ToolResult(
        success=True,
        result="import os\nimport sys\nfrom pathlib import Path",
      )

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "^import"})

    assert result.success
    assert "import os" in result.result
    assert "import sys" in result.result
    assert "from pathlib import Path" not in result.result

  @pytest.mark.asyncio
  async def test_post_filter_does_not_mutate_tool_args(self) -> None:
    """post_filter extraction must not mutate the original tool_args dict.

    tool_args is shared with the ToolCallEvent emitted before execution.
    Popping from it would hide post_filter from the UI display and any
    event handlers that inspect arguments after execution.
    """
    from yoker.core._processing import _execute_tool

    async def my_tool() -> ToolResult:
      """Return a test result."""
      return ToolResult(success=True, result="ok")

    spec = build_tool_spec(my_tool)
    agent = MagicMock()
    tool_args = {"post_filter": "ok"}
    result = await _execute_tool(spec, agent, tool_args)

    assert result.success
    # The original dict must still contain post_filter
    assert "post_filter" in tool_args
    assert tool_args["post_filter"] == "ok"

  @pytest.mark.asyncio
  async def test_post_filter_dict_result_filters_string_values(self) -> None:
    """post_filter filters individual string values within dict results.

    This reproduces the bug where make check with post_filter=FAILED
    returned 281K characters unfiltered — the dict result was not filtered
    because _apply_post_filter only operated on string results.
    """
    from yoker.core._processing import _execute_tool

    async def make_like_tool() -> ToolResult:
      """Simulate a make-tool-style dict result."""
      return ToolResult(
        success=True,
        result={
          "exit_code": 0,
          "stdout": "test_1 PASSED\ntest_2 FAILED\ntest_3 PASSED",
          "stderr": "",
        },
      )

    spec = build_tool_spec(make_like_tool)
    agent = MagicMock()
    result = await _execute_tool(spec, agent, {"post_filter": "FAILED"})

    assert result.success
    # Result is still a dict, but stdout is filtered
    assert isinstance(result.result, dict)
    assert result.result["exit_code"] == 0
    assert "test_2 FAILED" in result.result["stdout"]
    assert "test_1 PASSED" not in result.result["stdout"]
    assert "test_3 PASSED" not in result.result["stdout"]
    assert "[post_filter: 1/3" in result.result["stdout"]


# ---------------------------------------------------------------------------
# Unit tests for _enforce_output_limit
# ---------------------------------------------------------------------------


class TestEnforceOutputLimit:
  """Tests for the _enforce_output_limit function."""

  def _make_spec(self):
    """Build a tool spec with a named function (lambdas can't be resolved)."""

    async def dummy_tool() -> ToolResult:
      """Dummy tool for testing."""
      return ToolResult(success=True, result="ok")

    return build_tool_spec(dummy_tool)

  def test_no_limit_config_returns_original(self) -> None:
    """Tools without max_output_kb in config are not checked."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    agent = MagicMock()
    # MagicMock returns MagicMock for any attribute — not an int, so skipped
    result = ToolResult(success=True, result="x" * 500000)
    out = _enforce_output_limit(result, agent, spec)
    assert out is result  # unchanged

  def test_output_under_limit_returns_original(self) -> None:
    """Output under the limit is returned unchanged."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 100
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    result = ToolResult(success=True, result="x" * 1000)  # 1KB, under 100KB
    out = _enforce_output_limit(result, agent, spec)
    assert out is result  # unchanged

  def test_output_over_limit_returns_error(self) -> None:
    """Output over the limit returns a ToolResult with a clear error."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 10  # 10KB limit
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    big_output = "x" * 50000  # ~50KB, over 10KB limit
    result = ToolResult(success=True, result=big_output)
    out = _enforce_output_limit(result, agent, spec)

    assert not out.success
    assert "exceeds" in out.error.lower()
    assert "post_filter" in out.error.lower()

  def test_output_over_limit_on_error_field(self) -> None:
    """On failure, the error field is checked (not result)."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 10
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    big_error = "x" * 50000  # ~50KB
    result = ToolResult(success=False, error=big_error)
    out = _enforce_output_limit(result, agent, spec)

    assert not out.success
    assert "exceeds" in out.error.lower()

  def test_dict_result_converted_and_checked(self) -> None:
    """Dict results (e.g. from make) are converted to string and checked."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 1  # 1KB limit
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    result = ToolResult(success=True, result={"exit_code": 0, "stdout": "x" * 500000})
    out = _enforce_output_limit(result, agent, spec)
    assert not out.success
    assert "exceeds" in (out.error or "").lower()
    assert "post_filter" in (out.error or "").lower()

  def test_single_line_output_gets_json_hint(self) -> None:
    """Single-line output (e.g. JSON) gets a hint that post_filter cannot help."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 10
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    result = ToolResult(
      success=True, result=json.dumps({"data": "x" * 50000}) + "\n"
    )  # single line + trailing newline, as subprocess stdout
    out = _enforce_output_limit(result, agent, spec)

    assert not out.success
    assert "single-line" in (out.error or "")
    assert "limit/state" in (out.error or "")

  def test_multiline_output_keeps_post_filter_advice(self) -> None:
    """Multi-line output keeps the standard post_filter advice (no JSON hint)."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 10
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    result = ToolResult(success=True, result=("x" * 100 + "\n") * 500)  # multi-line, ~50KB
    out = _enforce_output_limit(result, agent, spec)

    assert not out.success
    assert "single-line" not in (out.error or "")

  def test_overflow_guidance_includes_collection_error_patterns(self) -> None:
    """The overflow advice names pytest collection-error patterns (#60 A1)."""
    from yoker.core._processing import _enforce_output_limit

    spec = self._make_spec()
    config = MagicMock()
    config.max_output_kb = 10
    agent = MagicMock()
    agent.config.tools.__getitem__ = MagicMock(return_value=config)

    result = ToolResult(success=True, result=("x" * 100 + "\n") * 500)  # multi-line, ~50KB
    out = _enforce_output_limit(result, agent, spec)

    assert not out.success
    assert "ERROR collecting" in (out.error or "")
    assert "ERRORS" in (out.error or "")
    assert "##[error]" in (out.error or "")


# ---------------------------------------------------------------------------
# Unit tests for _apply_post_filter
# ---------------------------------------------------------------------------


class TestApplyPostFilter:
  """Direct unit tests for the _apply_post_filter helper."""

  def test_filter_matching_lines(self) -> None:
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(success=True, result="error: a\nok: b\nerror: c")
    filtered = _apply_post_filter(result, "error")
    assert "error: a" in filtered.result
    assert "error: c" in filtered.result
    assert "ok: b" not in filtered.result
    assert "[post_filter: 2/3" in filtered.result

  def test_filter_all_match_no_summary(self) -> None:
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(success=True, result="line1\nline2")
    filtered = _apply_post_filter(result, "line")
    assert filtered.result == "line1\nline2"
    assert "[post_filter:" not in filtered.result

  def test_filter_no_matches(self) -> None:
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(success=True, result="line1\nline2\nline3")
    filtered = _apply_post_filter(result, "zzz")
    assert "line1" not in filtered.result
    assert "line2" not in filtered.result
    assert "line3" not in filtered.result
    assert "[post_filter: 0/3" in filtered.result

  def test_filter_invalid_regex_returns_original(self) -> None:
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(success=True, result="line1\nline2")
    filtered = _apply_post_filter(result, "[invalid")
    assert filtered.result == "line1\nline2"
    assert "[post_filter:" not in filtered.result

  def test_filter_empty_content_returns_original(self) -> None:
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(success=True, result="")
    filtered = _apply_post_filter(result, "anything")
    assert filtered.result == ""

  def test_filter_preserves_success_and_error(self) -> None:
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(success=True, result="error line\nok line", error=None)
    filtered = _apply_post_filter(result, "error")
    assert filtered.success is True
    assert filtered.error is None

  def test_filter_preserves_content_metadata(self) -> None:
    from yoker.core._processing import _apply_post_filter

    metadata = {"operation": "read", "path": "/tmp/test"}
    result = ToolResult(success=True, result="error line\nok line", content_metadata=metadata)
    filtered = _apply_post_filter(result, "error")
    assert filtered.content_metadata == metadata

  def test_filter_dict_result_filters_string_values(self) -> None:
    """post_filter on a dict result filters individual string values.

    Dict results (e.g. from the make tool: {"exit_code": 0, "stdout": "...",
    "stderr": "..."}) have their string values filtered line-by-line.
    Non-string values (exit_code, etc.) are preserved unchanged.
    """
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(
      success=True,
      result={
        "exit_code": 0,
        "stdout": "error: something\nok: fine\nerror: other",
        "stderr": "",
      },
    )
    filtered = _apply_post_filter(result, "error")
    # Result remains a dict with filtered string values
    assert isinstance(filtered.result, dict)
    assert filtered.result["exit_code"] == 0
    assert "error: something" in filtered.result["stdout"]
    assert "error: other" in filtered.result["stdout"]
    assert "ok: fine" not in filtered.result["stdout"]
    assert "[post_filter: 2/3" in filtered.result["stdout"]

  def test_filter_error_field_on_failure(self) -> None:
    """post_filter filters the error field on failure results.

    Tools like make put combined stdout+stderr in error on failure.
    The LLM needs to grep through this to find relevant lines. Only errors
    with more than 3 lines are filtered (short diagnostics preserved).
    """
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(
      success=False,
      result="",
      error=("line1: error\nline2: ok\nline3: FAIL\nline4: more\nline5: extra"),
    )
    filtered = _apply_post_filter(result, "error|FAIL")
    assert not filtered.success
    assert "line1: error" in (filtered.error or "")
    assert "line3: FAIL" in (filtered.error or "")
    assert "line2: ok" not in (filtered.error or "")
    assert "[post_filter:" in (filtered.error or "")

  def test_filter_short_error_field_preserved(self) -> None:
    """post_filter does NOT filter short error messages (≤ 3 lines).

    Tool-level diagnostics like "Agent not found: X. Available agents: ..."
    are short structured messages the LLM must see in full. Filtering them
    would strip the entire message, leaving an empty error.
    """
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(
      success=False,
      result="",
      error="Agent not found: skill-adapter. Available agents: c3:api-architect, c3:bug-fixer",
    )
    filtered = _apply_post_filter(result, "updated|Error|error")
    assert not filtered.success
    # Error should be preserved unchanged — no filtering, no summary line
    assert filtered.error == result.error
    assert "[post_filter:" not in (filtered.error or "")

  def test_filter_both_result_and_error(self) -> None:
    """post_filter filters both result and error fields when both are strings."""
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(
      success=False,
      result="FAIL: result line\nok: result line",
      error=("FAIL: error line\nok: error line\nline3: more\nline4: extra"),
    )
    filtered = _apply_post_filter(result, "FAIL")
    assert "FAIL: result line" in filtered.result
    assert "ok: result line" not in filtered.result
    assert "FAIL: error line" in (filtered.error or "")
    assert "ok: error line" not in (filtered.error or "")

  def test_filter_dict_result_but_filters_error(self) -> None:
    """post_filter on dict result filters dict string values and error field."""
    from yoker.core._processing import _apply_post_filter

    result = ToolResult(
      success=False,
      result={
        "exit_code": 1,
        "stdout": "error: stdout line\nok: stdout line",
        "stderr": "...",
      },
      error="line1: error\nline2: ok\nline3: more\nline4: extra",
    )
    filtered = _apply_post_filter(result, "error")
    # Dict result remains a dict, with stdout filtered
    assert isinstance(filtered.result, dict)
    assert filtered.result["exit_code"] == 1
    assert "error: stdout line" in filtered.result["stdout"]
    assert "ok: stdout line" not in filtered.result["stdout"]
    # Error field is filtered
    assert "line1: error" in (filtered.error or "")

  def test_filter_dict_result_make_tool_scenario(self) -> None:
    """post_filter on a make-tool-style dict result with large stdout.

    This reproduces the bug where make check with post_filter=FAILED
    returned 281K characters unfiltered — the dict result's string values
    were not filtered line-by-line.
    """
    from yoker.core._processing import _apply_post_filter

    # Simulate a make check success result with lots of stdout
    big_stdout = "\n".join(f"test_{i} PASSED" for i in range(1000))
    result = ToolResult(
      success=True,
      result={"exit_code": 0, "stdout": big_stdout, "stderr": ""},
    )
    filtered = _apply_post_filter(result, "FAILED")
    # The result is still a dict, but stdout is filtered
    assert isinstance(filtered.result, dict)
    # No lines should match "FAILED" since all tests passed
    assert "PASSED" not in filtered.result["stdout"]
    assert "[post_filter: 0/" in filtered.result["stdout"]
    assert "line2: ok" not in (filtered.error or "")
