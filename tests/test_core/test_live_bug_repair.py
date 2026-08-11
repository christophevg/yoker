"""Live end-to-end tests for the tool call argument repair fix.

These tests simulate the exact scenarios from the bug report:
- LLM generates JSON with literal unescaped newlines in string values
- LLM generates JSON with the ⏺ Unicode character
- LLM generates truncated JSON from streaming interruptions
- Combination of all the above
"""

import json

from yoker.core._processing import _build_tool_call, _repair_json


class TestLiveBugReportScenarios:
  """Simulate the exact scenarios from the user's bug report."""

  def test_literal_newlines_with_special_unicode_repaired(self):
    """The full scenario: ⏺ char + literal newlines in old_string/new_string.

    Before the fix: json.loads fails, arguments silently become {},
    and the LLM gets "missing required argument: 'operation'" —
    confusing and unhelpful.

    After the fix: the repair pass fixes the literal newlines,
    all arguments are preserved, and the ⏺ character survives.
    """
    invalid_json = (
      '{"path": "/tmp/test.py", "operation": "replace", '
      '"old_string": "⏺ [10:44:18] old\nline2", '
      '"new_string": "⏺ [10:44:18] new\nline2"}'
    )
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": invalid_json})

    assert tc.parse_error is None, "Should have been repaired!"
    assert tc.function.arguments["operation"] == "replace"
    assert "⏺" in tc.function.arguments["old_string"]
    assert "⏺" in tc.function.arguments["new_string"]
    assert tc.function.arguments["old_string"] == "⏺ [10:44:18] old\nline2"
    assert tc.function.arguments["new_string"] == "⏺ [10:44:18] new\nline2"

  def test_truncated_json_returns_descriptive_error(self):
    """Truncated JSON (streaming cut off) gets a descriptive parse_error.

    Before the fix: silent empty dict, confusing "missing argument" error.
    After the fix: descriptive error that tells the LLM what went wrong.
    """
    truncated = '{"path": "/tmp/test.py", "operation": "replace", "old_string": "def foo():'
    tc = _build_tool_call({"id": "call_2", "name": "update", "arguments_json": truncated})

    assert tc.parse_error is not None
    assert "Failed to parse tool arguments as JSON" in tc.parse_error
    assert tc.function.arguments == {}

  def test_garbage_json_returns_descriptive_error(self):
    """Completely unparseable JSON gets a descriptive parse_error."""
    garbage = '{broken json !!!'
    tc = _build_tool_call({"id": "call_3", "name": "update", "arguments_json": garbage})

    assert tc.parse_error is not None
    assert "Failed to parse" in tc.parse_error
    assert tc.function.arguments == {}

  def test_valid_json_with_unicode_preserved(self):
    """Valid JSON with ⏺ character passes through unchanged."""
    valid_with_unicode = json.dumps({
      "path": "/tmp/test.py",
      "operation": "replace",
      "old_string": "⏺ [10:44:18] old line",
      "new_string": "⏺ [10:44:18] new line",
    })
    tc = _build_tool_call({"id": "call_4", "name": "update", "arguments_json": valid_with_unicode})

    assert tc.parse_error is None
    assert "⏺" in tc.function.arguments["old_string"]
    assert "⏺" in tc.function.arguments["new_string"]

  def test_multiline_code_with_literal_newlines_repaired(self):
    """Multi-line Python code with literal newlines is repaired.

    This is the most common real-world trigger: the LLM puts code
    in old_string/new_string with literal newlines instead of \\n.
    """
    old_code = "def foo():\n  return 42\n"
    new_code = "def foo():\n  return 43\n"
    # Manually construct invalid JSON with literal newlines (not \n escapes)
    invalid_json = (
      '{"path": "/tmp/test.py", "operation": "replace", '
      '"old_string": "' + old_code + '", '
      '"new_string": "' + new_code + '"}'
    )
    tc = _build_tool_call({"id": "call_5", "name": "update", "arguments_json": invalid_json})

    assert tc.parse_error is None, "Should have been repaired!"
    assert tc.function.arguments["operation"] == "replace"
    assert tc.function.arguments["old_string"] == old_code
    assert tc.function.arguments["new_string"] == new_code

  def test_mixed_escaped_and_literal_newlines_repaired(self):
    """Mix of \\n escapes and literal newlines in the same string."""
    invalid_json = '{"old_string": "line1\\nline2\nline3"}'
    tc = _build_tool_call({"id": "call_6", "name": "update", "arguments_json": invalid_json})

    assert tc.parse_error is None
    assert tc.function.arguments["old_string"] == "line1\nline2\nline3"

  def test_parse_error_includes_raw_preview(self):
    """The parse_error message includes a preview of the raw JSON for debugging."""
    truncated = '{"path": "/tmp/test.py", "operation":'
    tc = _build_tool_call({"id": "call_7", "name": "update", "arguments_json": truncated})

    assert tc.parse_error is not None
    # The error should include some of the raw JSON so the LLM can see what went wrong
    assert "Raw arguments" in tc.parse_error

  def test_repair_does_not_touch_newlines_outside_strings(self):
    """Newlines in the structural part of JSON are valid and left alone."""
    # Pretty-printed JSON with newlines between keys is valid JSON
    valid_pretty = '{\n  "path": "/tmp/test.py",\n  "operation": "replace"\n}'
    tc = _build_tool_call({"id": "call_8", "name": "update", "arguments_json": valid_pretty})

    assert tc.parse_error is None
    assert tc.function.arguments["operation"] == "replace"