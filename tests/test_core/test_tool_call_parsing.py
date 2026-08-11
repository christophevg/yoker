"""Tests for tool call argument parsing in the processing pipeline.

These tests verify the behavior of _build_tool_call when the LLM emits
well-formed and malformed JSON in tool call arguments — a real-world
issue encountered during dogfooding where large multi-line string values
(e.g. Python code with quotes, newlines, backslashes) produce JSON that
fails to parse.
"""

import json

from yoker.core._processing import _build_tool_call, _repair_json


class TestBuildToolCallArgumentParsing:
  """Test _build_tool_call with various argument JSON shapes."""

  def test_valid_json_arguments_parsed_correctly(self) -> None:
    """
    Given: a well-formed JSON arguments string
    When: _build_tool_call is called
    Then: arguments dict contains all expected keys
    """
    args_json = json.dumps(
      {
        "path": "/tmp/test.py",
        "operation": "replace",
        "old_string": "old",
        "new_string": "new",
      }
    )
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_json})

    assert tc.function.name == "update"
    assert tc.function.arguments["path"] == "/tmp/test.py"
    assert tc.function.arguments["operation"] == "replace"
    assert tc.function.arguments["old_string"] == "old"
    assert tc.function.arguments["new_string"] == "new"
    assert tc.parse_error is None

  def test_multiline_string_in_arguments_parsed_correctly(self) -> None:
    """
    Given: JSON arguments with a multi-line string value (newlines escaped)
    When: _build_tool_call is called
    Then: the multi-line string is correctly parsed
    """
    code = "def foo():\n  return 42\n"
    args_json = json.dumps(
      {
        "path": "/tmp/test.py",
        "operation": "replace",
        "old_string": "old code",
        "new_string": code,
      }
    )
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_json})

    assert tc.function.arguments["new_string"] == code
    assert tc.parse_error is None

  def test_string_with_quotes_in_arguments_parsed_correctly(self) -> None:
    """
    Given: JSON arguments with string values containing quotes
    When: _build_tool_call is called
    Then: the quotes are correctly preserved in the parsed dict
    """
    text_with_quotes = "He said \"hello\" and 'world'"
    args_json = json.dumps({"old_string": text_with_quotes, "new_string": "replaced"})
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_json})

    assert tc.function.arguments["old_string"] == text_with_quotes
    assert tc.parse_error is None

  def test_string_with_backslashes_in_arguments_parsed_correctly(self) -> None:
    """
    Given: JSON arguments with string values containing backslashes
    When: _build_tool_call is called
    Then: the backslashes are correctly preserved
    """
    text_with_backslashes = r"C:\Users\test\nested\path"
    args_json = json.dumps({"old_string": text_with_backslashes})
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_json})

    assert tc.function.arguments["old_string"] == text_with_backslashes
    assert tc.parse_error is None

  def test_malformed_json_sets_parse_error(self) -> None:
    """
    Given: a malformed JSON arguments string (truncated/malformed)
    When: _build_tool_call is called
    Then: arguments is an empty dict and parse_error is set with a
      descriptive message that can be returned to the LLM.
    """
    malformed_json = '{"path": "/tmp/test.py", "operation": "replace", "old_string": "def foo():\\n  return "unclosed'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": malformed_json})

    assert tc.function.arguments == {}
    assert tc.parse_error is not None
    assert "Failed to parse tool arguments as JSON" in tc.parse_error

  def test_truncated_json_sets_parse_error(self) -> None:
    """
    Given: a truncated JSON string (as if streaming was cut off)
    When: _build_tool_call is called
    Then: arguments is an empty dict and parse_error is set.
    """
    truncated = '{"path": "/tmp/test.py", "operation":'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": truncated})

    assert tc.function.arguments == {}
    assert tc.parse_error is not None
    assert "Failed to parse tool arguments as JSON" in tc.parse_error

  def test_empty_arguments_json_produces_empty_dict(self) -> None:
    """
    Given: an empty arguments_json string
    When: _build_tool_call is called
    Then: arguments is an empty dict and no parse_error is set
    """
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": ""})

    assert tc.function.arguments == {}
    assert tc.parse_error is None

  def test_dict_arguments_passed_through_directly(self) -> None:
    """
    Given: arguments already as a dict (not a JSON string)
    When: _build_tool_call is called
    Then: the dict is used as-is without re-parsing
    """
    args_dict = {"path": "/tmp/test.py", "operation": "replace"}
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_dict})

    assert tc.function.arguments is args_dict
    assert tc.parse_error is None

  def test_large_multiline_python_code_in_arguments(self) -> None:
    """
    Given: JSON arguments containing a large multi-line Python code string
    When: _build_tool_call is called
    Then: the code string is correctly parsed if JSON is valid
    """
    python_code = (
      "def _do_replace(\n"
      "  old_content: str,\n"
      "  old_string: str,\n"
      "  new_string: str,\n"
      "  require_exact_match: bool,\n"
      ") -> str:\n"
      '  """Replace old_string with new_string."""\n'
      "  occurrences = old_content.count(old_string)\n"
      "  if occurrences == 0:\n"
      '    raise ValueError("Search text not found")\n'
      "  return old_content.replace(old_string, new_string, 1)\n"
    )
    args_json = json.dumps(
      {
        "path": "/tmp/update.py",
        "operation": "replace",
        "old_string": python_code,
        "new_string": python_code.replace("Search text not found", "Not found"),
      }
    )
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_json})

    assert tc.function.arguments["operation"] == "replace"
    assert "Search text not found" in tc.function.arguments["old_string"]
    assert "Not found" in tc.function.arguments["new_string"]
    assert tc.parse_error is None

  def test_json_with_unescaped_newline_is_repaired(self) -> None:
    """
    Given: JSON with a literal newline inside a string value (invalid JSON)
    When: _build_tool_call is called
    Then: the lenient repair pass fixes the newline and arguments are
      parsed correctly with the original multi-line string preserved.
    """
    # Literal newlines inside a JSON string value are invalid JSON,
    # but the repair pass converts them to \n escape sequences.
    invalid_json = '{"old_string": "line1\nline2"}'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": invalid_json})

    assert tc.function.arguments["old_string"] == "line1\nline2"
    assert tc.parse_error is None

  def test_json_with_unescaped_tab_is_repaired(self) -> None:
    """
    Given: JSON with a literal tab inside a string value
    When: _build_tool_call is called
    Then: the repair pass fixes the tab and arguments are parsed correctly.
    """
    invalid_json = '{"old_string": "col1\tcol2"}'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": invalid_json})

    assert tc.function.arguments["old_string"] == "col1\tcol2"
    assert tc.parse_error is None

  def test_json_with_unescaped_newline_in_multiline_code_is_repaired(self) -> None:
    """
    Given: JSON with literal newlines in a multi-line code string value
    When: _build_tool_call is called
    Then: the repair pass fixes all newlines and the code is preserved.
    """
    code_with_real_newlines = "def foo():\n  return 42\n"
    # Manually construct invalid JSON with literal newlines
    invalid_json = '{"new_string": "' + code_with_real_newlines + '"}'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": invalid_json})

    assert tc.function.arguments["new_string"] == code_with_real_newlines
    assert tc.parse_error is None

  def test_json_with_backslash_n_preserved_through_repair(self) -> None:
    """
    Given: JSON with properly escaped \\n in string values
    When: _build_tool_call is called
    Then: the repair pass detects no changes needed and parsing works.
    """
    valid_json = '{"old_string": "line1\\nline2"}'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": valid_json})

    assert tc.function.arguments["old_string"] == "line1\nline2"
    assert tc.parse_error is None


class TestRepairJson:
  """Test the _repair_json helper directly."""

  def test_no_control_chars_returns_none(self) -> None:
    """When there are no control chars, no repair is needed."""
    assert _repair_json('{"key": "value"}') is None

  def test_literal_newline_in_string_is_repaired(self) -> None:
    """Literal newlines inside string values are replaced with \\n."""
    raw = '{"old": "line1\nline2"}'
    repaired = _repair_json(raw)
    assert repaired is not None
    assert json.loads(repaired) == {"old": "line1\nline2"}

  def test_literal_tab_in_string_is_repaired(self) -> None:
    """Literal tabs inside string values are replaced with \\t."""
    raw = '{"old": "a\tb"}'
    repaired = _repair_json(raw)
    assert repaired is not None
    assert json.loads(repaired) == {"old": "a\tb"}

  def test_newline_outside_string_is_not_touched(self) -> None:
    """Newlines in the structural part of JSON are valid and left alone."""
    raw = '{\n  "key": "value"\n}'
    repaired = _repair_json(raw)
    # The newline is outside a string — no repair needed (returns None
    # because the original is already valid JSON).
    assert repaired is None

  def test_unrepairable_json_returns_none(self) -> None:
    """When repair can't fix the issue, return None."""
    raw = '{"key": "value" "missing_colon" "value2"}'
    repaired = _repair_json(raw)
    assert repaired is None

  def test_escaped_newline_not_double_escaped(self) -> None:
    """Properly escaped \\n in strings is not double-escaped."""
    raw = '{"old": "line1\\nline2"}'
    repaired = _repair_json(raw)
    # Already valid JSON — no repair needed.
    assert repaired is None

  def test_mixed_escaped_and_unescaped_newlines(self) -> None:
    """Mix of escaped and unescaped newlines: only unescaped are fixed."""
    raw = '{"old": "line1\\nline2\nline3"}'
    repaired = _repair_json(raw)
    assert repaired is not None
    result = json.loads(repaired)
    assert result["old"] == "line1\nline2\nline3"


class TestBuildToolCallBasicStructure:
  """Test basic structure of _build_tool_call output."""

  def test_tool_call_has_id(self) -> None:
    """Tool call preserves the id from the buffer."""
    tc = _build_tool_call({"id": "call_abc", "name": "read", "arguments_json": "{}"})
    assert tc.id == "call_abc"

  def test_tool_call_generates_id_when_missing(self) -> None:
    """Tool call generates an id when none is provided."""
    tc = _build_tool_call({"id": None, "name": "read", "arguments_json": "{}"})
    assert tc.id is not None
    assert tc.id.startswith("call_")

  def test_tool_call_has_function_name(self) -> None:
    """Tool call preserves the function name from the buffer."""
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": "{}"})
    assert tc.function.name == "update"

  def test_tool_call_parse_error_none_for_valid_json(self) -> None:
    """parse_error is None when JSON parses successfully."""
    tc = _build_tool_call({"id": "call_1", "name": "read", "arguments_json": '{"path": "/tmp"}'})
    assert tc.parse_error is None

  def test_tool_call_parse_error_set_for_malformed_json(self) -> None:
    """parse_error is set when JSON parsing fails and repair can't fix it."""
    tc = _build_tool_call({"id": "call_1", "name": "read", "arguments_json": "{broken"})
    assert tc.parse_error is not None
    assert "Failed to parse" in tc.parse_error
