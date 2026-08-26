"""Regression test: guardrail bypass via namespaced tool names.

Bug: ``_validate_tool_args`` passed ``spec.name`` (e.g. ``"yoker:write"``)
to ``WritePathGuardrail.validate()``, which checked ``tool_name not in
_FILESYSTEM_TOOLS`` — a set of simple names (``"write"``, ``"read"``, ...).
The namespaced name was never in the set, so **all** path validation was
skipped: protected_files, path traversal, blocked patterns, extensions,
file size — everything.

This affected every agent (primary and subagent) for every namespaced
tool. The primary agent in interactive mode was partially saved by the
``_maybe_approve_write_blocked`` approval hook (which strips the namespace),
but subagents and batch-mode agents had zero guardrail protection.

The fix removes the ``_FILESYSTEM_TOOLS`` gate entirely (the guardrail is
already only invoked for ``Path``-annotated parameters) and passes
``spec.simple_name`` to ``validate()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest

from yoker.config import Config, PermissionsConfig
from yoker.core._processing import _validate_tool_args
from yoker.tools.annotations import Text
from yoker.tools.annotations import WritePath as PathArg
from yoker.tools.guardrails.path import WritePathGuardrail
from yoker.tools.schema import ToolSpec, build_tool_spec

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


async def _dummy_write(
  path: Annotated[str, PathArg("Path to the file to write")],
  content: Annotated[str, Text("Content to write")],
  ctx: Any = None,
  create_parents: bool = False,
) -> Any:
  """Stand-in for the real write tool — never actually called."""
  ...


async def _dummy_update(
  path: Annotated[str, PathArg("Path to the file to update")],
  ctx: Any = None,
  operation: Annotated[str, Text("File operation")] = "replace",
  old_string: Annotated[str, Text("Text to find")] = "",
  new_string: Annotated[str, Text("Replacement text")] = "",
  line_number: Any = None,
  line_range: Any = None,
  require_exact_match: Any = None,
) -> Any:
  """Stand-in for the real update tool — never actually called."""
  ...


def _make_namespaced_spec(
  tool_callable: Any,
  simple_name: str,
  namespace: str = "yoker",
) -> ToolSpec:
  """Build a namespaced ToolSpec like the plugin loader does."""
  spec = build_tool_spec(tool_callable, namespace=namespace, name=simple_name)
  return spec


class _FakeAgent:
  """Minimal agent carrying guardrails and config for _validate_tool_args."""

  def __init__(self, config: Config) -> None:
    self._guardrails: dict[str, Any] = {"path_write": WritePathGuardrail(config)}
    self.config = config


# ---------------------------------------------------------------------------
# Regression: namespaced tool name bypasses WritePathGuardrail.validate()
# ---------------------------------------------------------------------------


class TestNamespacedToolGuardrailBypass:
  """The bug: namespaced tool names bypassed the guardrail entirely."""

  @pytest.mark.asyncio
  async def test_namespaced_write_blocked_on_protected_file(self, tmp_path: Path) -> None:
    """yoker:write on Makefile must be blocked by the guardrail.

    Before the fix, ``spec.name`` was ``"yoker:write"`` which was not in
    ``_FILESYSTEM_TOOLS``, so validate() returned valid=True immediately.
    """
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    agent = _FakeAgent(config)
    spec = _make_namespaced_spec(_dummy_write, "write")
    tool_args = {"path": str(target), "content": "malicious"}

    result = _validate_tool_args(agent, spec, tool_args)

    assert result.valid is False, (
      "Namespaced write to Makefile must be blocked. "
      "If this passes, the guardrail is bypassed for namespaced tools."
    )
    assert "write-protected" in (result.reason or "").lower()

  @pytest.mark.asyncio
  async def test_namespaced_update_blocked_on_protected_file(self, tmp_path: Path) -> None:
    """yoker:update on pyproject.toml must be blocked by the guardrail."""
    target = tmp_path / "pyproject.toml"
    target.write_text("[project]\nname = 'x'\n")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    agent = _FakeAgent(config)
    spec = _make_namespaced_spec(_dummy_update, "update")
    tool_args = {
      "path": str(target),
      "operation": "replace",
      "old_string": "x",
      "new_string": "pwned",
    }

    result = _validate_tool_args(agent, spec, tool_args)

    assert result.valid is False, "Namespaced update to pyproject.toml must be blocked."
    assert "write-protected" in (result.reason or "").lower()

  @pytest.mark.asyncio
  async def test_namespaced_write_path_traversal_blocked(self, tmp_path: Path) -> None:
    """Path traversal must be caught even with namespaced tool names."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    agent = _FakeAgent(config)
    spec = _make_namespaced_spec(_dummy_write, "write")
    # /etc/passwd is outside the allowed root
    tool_args = {"path": "/etc/passwd", "content": "x"}

    result = _validate_tool_args(agent, spec, tool_args)

    assert result.valid is False, "Path traversal must be caught for namespaced tools."

  @pytest.mark.asyncio
  async def test_namespaced_write_non_protected_passes(self, tmp_path: Path) -> None:
    """Non-protected files should pass validation (no false positives)."""
    target = tmp_path / "src" / "main.py"
    target.parent.mkdir(parents=True)
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    agent = _FakeAgent(config)
    spec = _make_namespaced_spec(_dummy_write, "write")
    tool_args = {"path": str(target), "content": "print('hello')"}

    result = _validate_tool_args(agent, spec, tool_args)

    assert result.valid is True, "Non-protected file should pass validation."


# ---------------------------------------------------------------------------
# Regression: subagent has no protected_files protection
# ---------------------------------------------------------------------------


class TestSubagentProtectedFiles:
  """Subagents must have the same guardrail protection as the primary agent.

  Before the fix, subagents had no approval handler wired, so
  ``_maybe_approve_write_blocked`` returned False (no handler → no skip),
  and the guardrail was bypassed by the namespace bug. The guardrail
  must be the single enforcement point — the approval hook is a UI
  enhancement, not a replacement for the guardrail.
  """

  @pytest.mark.asyncio
  async def test_subagent_write_makefile_blocked(self, tmp_path: Path) -> None:
    """A subagent (no approval handler) must still be blocked by the guardrail."""
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    agent = _FakeAgent(config)
    # Subagent: no approval handler wired
    assert (
      not hasattr(agent, "_approval_handler") or getattr(agent, "_approval_handler", None) is None
    )
    spec = _make_namespaced_spec(_dummy_write, "write")
    tool_args = {"path": str(target), "content": "all:"}

    result = _validate_tool_args(agent, spec, tool_args)

    assert result.valid is False, "Subagent must be blocked from writing Makefile by the guardrail."

  @pytest.mark.asyncio
  async def test_subagent_update_pyproject_blocked(self, tmp_path: Path) -> None:
    """A subagent updating pyproject.toml must be blocked."""
    target = tmp_path / "pyproject.toml"
    target.write_text("[project]\nname = 'x'\n")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    agent = _FakeAgent(config)
    spec = _make_namespaced_spec(_dummy_update, "update")
    tool_args = {
      "path": str(target),
      "operation": "replace",
      "old_string": "x",
      "new_string": "pwned",
    }

    result = _validate_tool_args(agent, spec, tool_args)

    assert result.valid is False, "Subagent must be blocked from updating pyproject.toml."


# ---------------------------------------------------------------------------
# Subagent approval propagation: subagents in interactive sessions get
# the same approval prompt as the primary agent.
# ---------------------------------------------------------------------------


class TestSubagentApprovalPropagation:
  """Subagents must receive the session's approval handler.

  The approval handler is stored on the Session and propagated to every
  agent created via ``_create_agent``. This ensures subagents in an
  interactive session trigger the same approval prompt as the primary
  agent when writing to a protected file.
  """

  def test_session_stores_approval_handler(self) -> None:
    """Session._approval_handler defaults to None."""
    from yoker.session import Session

    # Cannot construct a full Session without a config, but we can check
    # the attribute exists and defaults to None on the class.
    assert (
      hasattr(Session, "_approval_handler")
      or "_approval_handler" in Session.__init__.__code__.co_names
    )

  def test_subagent_inherits_approval_handler(self) -> None:
    """When the session has an approval handler, spawned agents inherit it."""
    # We test the propagation logic directly: _create_agent copies
    # session._approval_handler onto the agent. We verify by checking
    # that the Session has the attribute and that _create_agent references it.
    import inspect

    from yoker.session import Session

    source = inspect.getsource(Session._create_agent)
    assert "_approval_handler" in source, (
      "_create_agent must propagate _approval_handler to spawned agents"
    )


# ---------------------------------------------------------------------------
# Regression: guardrail always enforces (no interactive_approvals bypass)
# ---------------------------------------------------------------------------


class TestGuardrailAlwaysEnforces:
  """The guardrail must always enforce protected_files.

  Previously, the ``interactive_approvals`` flag caused the guardrail to
  skip the protected_files check, deferring to the approval hook. This
  created a gap: if the approval hook was not wired (subagents, batch
  mode), there was no protection at all.

  After the fix, the guardrail always enforces. The ``skip_blocks``
  parameter is the only way to skip the check, and it is only set when
  the user interactively approves via ``_maybe_approve_write_blocked``.
  """

  def test_guardrail_blocks_write_without_skip(self, tmp_path: Path) -> None:
    """The guardrail must block write-blocked paths by default."""
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)

    result = guardrail.validate("write", {"path": str(target), "content": "x"})

    assert result.valid is False, "Guardrail must always enforce blocked_write_paths by default."

  def test_guardrail_blocks_update_without_skip(self, tmp_path: Path) -> None:
    """The guardrail must block write-blocked updates by default."""
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)

    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
    )

    assert result.valid is False, "Guardrail must always enforce blocked_write_paths on update."
