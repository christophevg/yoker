"""Tests for WritePathGuardrail blocked_write_paths check (MBI-009 T12)."""

from __future__ import annotations

from pathlib import Path

from yoker.config import (
  Config,
  PermissionsConfig,
)
from yoker.tools.guardrails.path import WritePathGuardrail

# Every default blocked_write_paths entry, with a representative path for each.
_DEFAULT_CASES = [
  ("Makefile", "Makefile"),
  ("makefile", "makefile"),
  ("GNUmakefile", "GNUmakefile"),
  ("Justfile", "Justfile"),
  ("justfile", "justfile"),
  ("Taskfile.yml", "Taskfile.yml"),
  ("pyproject.toml", "pyproject.toml"),
  ("tox.ini", "tox.ini"),
  ("setup.py", "setup.py"),
  ("setup.cfg", "setup.cfg"),
  ("yoker.toml", "yoker.toml"),
  (".git/config", ".git/config"),
  (".git/hooks/pre-commit", ".git/hooks/pre-commit"),
  (".github/workflows/ci.yml", ".github/workflows/ci.yml"),
  ("uv.lock", "uv.lock"),
  ("poetry.lock", "poetry.lock"),
]


class TestBlockedWritePathsDefault:
  """Default denylist coverage — each entry blocks write and update."""

  def test_blocks_each_default_on_write(self, tmp_path: Path) -> None:
    """Every default blocked_write_paths entry blocks the write tool."""
    for _pattern, rel in _DEFAULT_CASES:
      full = tmp_path / rel
      full.parent.mkdir(parents=True, exist_ok=True)
      if not full.suffix and full == full.parent:
        continue
      config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
      guardrail = WritePathGuardrail(config)
      result = guardrail.validate("write", {"path": str(full), "content": "x"})
      assert result.valid is False, f"Expected block for {rel}"
      # .git/.github paths also match the blocked_paths glob,
      # which fires before the blocked_write_paths check. Accept either message.
      assert (
        "write-protected" in result.reason.lower() or "blocked pattern" in result.reason.lower()
      )

  def test_blocks_each_default_on_update(self, tmp_path: Path) -> None:
    """Every default blocked_write_paths entry blocks the update tool."""
    for _pattern, rel in _DEFAULT_CASES:
      full = tmp_path / rel
      full.parent.mkdir(parents=True, exist_ok=True)
      if full.exists() or full.is_dir():
        continue
      full.write_text("old")
      config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
      guardrail = WritePathGuardrail(config)
      result = guardrail.validate(
        "update",
        {"path": str(full), "operation": "replace", "old_string": "old", "new_string": "new"},
      )
      assert result.valid is False, f"Expected block for {rel}"
      assert (
        "write-protected" in result.reason.lower() or "blocked pattern" in result.reason.lower()
      )


class TestBlockedWritePathsGlob:
  """Glob matching semantics for blocked_write_paths."""

  def test_glob_matches_git_hooks(self, tmp_path: Path) -> None:
    """.git/hooks/* matches any hook script."""
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    target = hooks / "pre-push"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    # .git also matches blocked_paths — either way it must be blocked.
    assert result.valid is False

  def test_glob_matches_github_workflows(self, tmp_path: Path) -> None:
    """.github/workflows/*.yml matches any workflow file."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    target = wf / "deploy.yml"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    # .github is not in blocked_paths, but deploy.yml matches blocked_write_paths
    assert result.valid is False
    assert "write-protected" in result.reason.lower() or "blocked pattern" in result.reason.lower()

  def test_basename_match_at_depth(self, tmp_path: Path) -> None:
    """Makefile at root matches blocked_write_paths."""
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is False
    assert "write-protected" in result.reason.lower()

  def test_non_protected_file_passes(self, tmp_path: Path) -> None:
    """A non-write-blocked file passes the blocked_write_paths check."""
    target = tmp_path / "foo.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is True

  def test_parent_relative_pattern_blocks_write(self, tmp_path: Path) -> None:
    """Pattern like '../sibling' blocks writes to files under that sibling."""
    # Create a sibling directory next to tmp_path
    sibling = tmp_path.parent / "yoker-test-sibling"
    sibling.mkdir(exist_ok=True)
    target = sibling / "README.md"
    target.write_text("# test")
    try:
      config = Config(
        permissions=PermissionsConfig(
          filesystem_paths=(str(tmp_path), str(sibling)),
          blocked_write_paths=("../yoker-test-sibling"),
          blocked_paths=(),
        )
      )
      guardrail = WritePathGuardrail(config)
      result = guardrail.validate("update", {"path": str(target), "new_string": "x"})
      assert result.valid is False
      assert "write-protected" in (result.reason or "").lower()
    finally:
      target.unlink(missing_ok=True)
      sibling.rmdir()


class TestBlockedWritePathsEmpty:
  """Empty tuple disables all protections (explicit opt-out)."""

  def test_empty_list_disables(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is True

  def test_empty_list_disables_update(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
    )
    assert result.valid is True


class TestBlockedWritePathsReadNotChecked:
  """read tool is never blocked by blocked_write_paths."""

  def test_read_makefile_not_blocked_by_write_paths(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text("all:")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    from yoker.tools.guardrails.path import ReadPathGuardrail

    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(target)})
    assert result.valid is True


class TestBlockedWritePathsSkipBlocks:
  """The ``skip_blocks`` parameter skips the blocked_write_paths check.

  This is used by the approval hook: when the user interactively approves
  a write-blocked path write, the guardrail skips the check for that call.
  Without ``skip_blocks``, the guardrail always enforces.
  """

  def test_skip_blocks_allows_write(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"}, skip_blocks=True)
    assert result.valid is True

  def test_skip_blocks_allows_update(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
      skip_blocks=True,
    )
    assert result.valid is True

  def test_no_skip_blocks_blocks_write(self, tmp_path: Path) -> None:
    """Without skip_blocks, the guardrail always blocks write-blocked paths."""
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is False


class TestIsWriteBlockedPublic:
  """Public ``is_write_blocked`` entry point for the processing loop."""

  def test_is_write_blocked_true_for_makefile(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    assert guardrail.is_write_blocked(str(target)) is True

  def test_is_write_blocked_false_for_normal_file(self, tmp_path: Path) -> None:
    target = tmp_path / "foo.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    assert guardrail.is_write_blocked(str(target)) is False

  def test_is_write_blocked_respects_empty_list(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    assert guardrail.is_write_blocked(str(target)) is False

  def test_is_write_blocked_unresolvable_path(self) -> None:
    """A non-existent path still matches via glob against the relative path."""
    config = Config()
    guardrail = WritePathGuardrail(config)
    # _resolve_path uses os.path.realpath which normalizes any string;
    # the relative path from the root is checked against blocked_write_paths.
    assert guardrail.is_write_blocked("/nonexistent/path/Makefile") is True
