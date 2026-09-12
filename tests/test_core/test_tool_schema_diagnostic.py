"""Regression tests: bare subscripted generics must map to correct schema types.

Root cause (found via live session testing): ``_build_parameter_schema``
stripped the "Annotated wrapper" from ANY subscripted generic — bare
``dict[str, str] | None`` has get_args ``(str, str)`` indistinguishable from
``Annotated`` metadata, so ``env_vars`` was reduced to ``str`` and declared
``{"type": "string"}`` in the tool schema. Models reading that schema
correctly passed a JSON string; the make tool then rejected it with
"Parameter 'env_vars' must be an object" — the mismatch that motivated the
(now replaced) blunt Ollama per-value coercion, whose collateral damage on
``write(content='{"key": "value"}')`` produced the original "Invalid content
parameter" bug report.

Covers:
1. Real tool schemas: make.env_vars -> "object", write.content -> "string".
2. The type mapper directly: Optional[dict] -> "object", Optional[list] -> "array".
3. Annotated markers still resolve (description + guardrail type).
"""

from typing import Annotated

from yoker.builtin.make import make
from yoker.builtin.write import write
from yoker.tools.annotations import Text
from yoker.tools.schema import _python_type_to_json_schema, build_tool_spec


def test_real_make_env_vars_schema_declares_object() -> None:
  spec = build_tool_spec(make, namespace="yoker", name="make")
  props = spec.schema["function"]["parameters"]["properties"]
  # Failing this shows the actual property dict in the assertion output.
  assert props["env_vars"].get("type") == "object", props["env_vars"]


def test_real_write_content_schema_declares_string() -> None:
  spec = build_tool_spec(write, namespace="yoker", name="write")
  props = spec.schema["function"]["parameters"]["properties"]
  assert props["content"].get("type") == "string", props["content"]


def test_type_mapper_handles_optional_dict() -> None:
  """Direct mapper check: dict[str,str] | None must map to "object"."""
  assert _python_type_to_json_schema(dict[str, str] | None) == "object"


def test_type_mapper_handles_optional_list() -> None:
  assert _python_type_to_json_schema(list[str] | None) == "array"


def test_annotated_dict_still_resolves_marker() -> None:
  """Annotated[T, Text(...)] still yields description + object type."""

  async def tool(env_vars: Annotated[dict[str, str], Text("Env vars")] | None = None) -> str:
    """A test tool."""
    return "ok"

  spec = build_tool_spec(tool)
  props = spec.schema["function"]["parameters"]["properties"]
  assert props["env_vars"].get("type") == "object"
  assert "Env vars" in props["env_vars"].get("description", "")


def test_annotated_writepath_guard_still_resolves() -> None:
  """Guardrail markers (WritePath) are unaffected by the gating fix."""
  props = build_tool_spec(write, namespace="yoker", name="write").schema["function"]["parameters"][
    "properties"
  ]
  assert props["path"].get("type") == "string"
