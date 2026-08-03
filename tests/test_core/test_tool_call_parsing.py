"""Tests for tool call argument parsing in the processing pipeline.

These tests illustrate and verify the behavior of _build_tool_call when
the LLM emits malformed JSON in tool call arguments — a real-world issue
encountered during dogfooding where large multi-line string values (e.g.
Python code with quotes, newlines, backslashes) produce JSON that fails
to parse.
"""

import json

from yoker.core._processing import _build_tool_call


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

  def test_malformed_json_silently_produces_empty_dict(self) -> None:
    """
    GIVEN: a malformed JSON arguments string (truncated/malformed)
    WHEN: _build_tool_call is called
    THEN: arguments is an empty dict {} — this is the bug!

    This test documents the current (buggy) behavior: when json.loads fails,
    the error is silently swallowed and an empty dict is used. This causes
    downstream errors like "missing a required argument: 'operation'" which
    obscure the real problem (malformed JSON from the LLM).
    """
    malformed_json = '{"path": "/tmp/test.py", "operation": "replace", "old_string": "def foo():\\n  return "unclosed'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": malformed_json})

    # This is the current buggy behavior — arguments silently become {}
    assert tc.function.arguments == {}

  def test_truncated_json_produces_empty_dict(self) -> None:
    """
    GIVEN: a truncated JSON string (as if streaming was cut off)
    WHEN: _build_tool_call is called
    THEN: arguments is an empty dict {}

    Documents that truncated JSON from streaming is also silently swallowed.
    """
    truncated = '{"path": "/tmp/test.py", "operation":'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": truncated})

    assert tc.function.arguments == {}

  def test_empty_arguments_json_produces_empty_dict(self) -> None:
    """
    Given: an empty arguments_json string
    When: _build_tool_call is called
    Then: arguments is an empty dict
    """
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": ""})

    assert tc.function.arguments == {}

  def test_dict_arguments_passed_through_directly(self) -> None:
    """
    Given: arguments already as a dict (not a JSON string)
    When: _build_tool_call is called
    Then: the dict is used as-is without re-parsing
    """
    args_dict = {"path": "/tmp/test.py", "operation": "replace"}
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": args_dict})

    assert tc.function.arguments is args_dict

  def test_large_multiline_python_code_in_arguments(self) -> None:
    """
    Given: JSON arguments containing a large multi-line Python code string
    When: _build_tool_call is called
    Then: the code string is correctly parsed if JSON is valid

    This is the scenario that triggered the investigation: the LLM emits
    a tool call with old_string/new_string containing Python code. When
    the JSON is well-formed, parsing works. The problem occurs when the
    model produces malformed JSON (unescaped chars, truncation).
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

  def test_json_with_unescaped_newline_fails_silently(self) -> None:
    """
    GIVEN: JSON with a literal newline inside a string value (invalid JSON)
    WHEN: _build_tool_call is called
    THEN: arguments is an empty dict {}

    This is the most likely real-world failure mode: the LLM emits a string
    value with literal newlines instead of \\n escape sequences. Standard
    json.loads rejects this, and the current code silently swallows it.
    """
    # Literal newlines inside a JSON string value are invalid
    invalid_json = '{"old_string": "line1\nline2"}'
    tc = _build_tool_call({"id": "call_1", "name": "update", "arguments_json": invalid_json})

    assert tc.function.arguments == {}


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
