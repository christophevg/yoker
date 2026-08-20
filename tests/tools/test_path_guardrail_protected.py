"""Tests for PathGuardrail protected_files check (MBI-009 T12)."""

from __future__ import annotations

from pathlib import Path

from yoker.config import (
  Config,
  PermissionsConfig,
  ReadToolConfig,
  ToolsConfig,
)
from yoker.tools.guardrails.path import PathGuardrail

# Every default protected_files entry, with a representative path for each.
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


class TestProtectedFilesDefault:
  """Default denylist coverage — each entry blocks write and update."""

  def test_blocks_each_default_on_write(self, tmp_path: Path) -> None:
    """Every default protected_files entry blocks the write tool."""
    for _pattern, rel in _DEFAULT_CASES:
      full = tmp_path / rel
      full.parent.mkdir(parents=True, exist_ok=True)
      # Some entries are directories — skip writing the file in that case.
      if not full.suffix and full == full.parent:
        continue
      config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
      guardrail = PathGuardrail(config)
      result = guardrail.validate("write", {"path": str(full), "content": "x"})
      assert result.valid is False, f"Expected block for {rel}"
      # .git/.github paths also match the pre-existing \.git blocked_pattern,
      # which fires before the protected_files check. Accept either message.
      assert "protected" in result.reason.lower() or "blocked pattern" in result.reason.lower()

  def test_blocks_each_default_on_update(self, tmp_path: Path) -> None:
    """Every default protected_files entry blocks the update tool."""
    for _pattern, rel in _DEFAULT_CASES:
      full = tmp_path / rel
      full.parent.mkdir(parents=True, exist_ok=True)
      if full.exists() or full.is_dir():
        continue
      full.write_text("old")
      config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
      guardrail = PathGuardrail(config)
      result = guardrail.validate(
        "update",
        {"path": str(full), "operation": "replace", "old_string": "old", "new_string": "new"},
      )
      assert result.valid is False, f"Expected block for {rel}"
      assert "protected" in result.reason.lower() or "blocked pattern" in result.reason.lower()


class TestProtectedFilesGlob:
  """fnmatch glob matching semantics."""

  def test_glob_matches_git_hooks(self, tmp_path: Path) -> None:
    """.git/hooks/* matches any hook script."""
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    target = hooks / "pre-push"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    # .git also matches blocked_patterns — either way it must be blocked.
    assert result.valid is False

  def test_glob_matches_github_workflows(self, tmp_path: Path) -> None:
    """.github/workflows/*.yml matches any workflow file."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    target = wf / "deploy.yml"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    # .github contains the substring .git which matches the pre-existing
    # \.git blocked_pattern. Either that or the protected_files glob blocks.
    assert result.valid is False
    assert "protected" in result.reason.lower() or "blocked pattern" in result.reason.lower()

  def test_basename_match_at_depth(self, tmp_path: Path) -> None:
    """Makefile matches at any depth via basename match."""
    sub = tmp_path / "subdir" / "deep"
    sub.mkdir(parents=True)
    target = sub / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is False
    assert "protected" in result.reason.lower()
    # The error message reports the relative path, not the basename.
    assert "subdir/deep/Makefile" in result.reason

  def test_non_protected_file_passes(self, tmp_path: Path) -> None:
    """A non-protected file passes the protected_files check."""
    target = tmp_path / "foo.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is True


class TestProtectedFilesEmpty:
  """Empty tuple disables all protections (explicit opt-out)."""

  def test_empty_list_disables(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        protected_files=(),
      )
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is True

  def test_empty_list_disables_update(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        protected_files=(),
      )
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
    )
    assert result.valid is True


class TestProtectedFilesReadNotChecked:
  """read tool is never blocked by protected_files."""

  def test_read_makefile_not_blocked_by_protected(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text("all:")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      # Allow the no-extension Makefile via empty allowed_extensions.
      tools=ToolsConfig(read=ReadToolConfig(allowed_extensions=())),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(target)})
    assert result.valid is True


class TestProtectedFilesSkipProtected:
  """The ``skip_protected`` parameter skips the protected_files check.

  This is used by the approval hook: when the user interactively approves
  a protected-file write, the guardrail skips the check for that call.
  Without ``skip_protected``, the guardrail always enforces.
  """

  def test_skip_protected_allows_write(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"}, skip_protected=True)
    assert result.valid is True

  def test_skip_protected_allows_update(self, tmp_path: Path) -> None:
    # Use pyproject.toml — .toml is in the default allowed_extensions so
    # the read-extension check passes, isolating the protected_files skip.
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
      skip_protected=True,
    )
    assert result.valid is True

  def test_no_skip_protected_blocks_write(self, tmp_path: Path) -> None:
    """Without skip_protected, the guardrail always blocks protected files."""
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is False


class TestIsProtectedPublic:
  """Public ``is_protected`` entry point for the processing loop."""

  def test_is_protected_true_for_makefile(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    assert guardrail.is_protected(str(target)) is True

  def test_is_protected_false_for_normal_file(self, tmp_path: Path) -> None:
    target = tmp_path / "foo.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    assert guardrail.is_protected(str(target)) is False

  def test_is_protected_respects_empty_list(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        protected_files=(),
      )
    )
    guardrail = PathGuardrail(config)
    assert guardrail.is_protected(str(target)) is False

  def test_is_protected_unresolvable_path(self) -> None:
    """A non-existent path outside allowed roots still matches via basename."""
    config = Config()
    guardrail = PathGuardrail(config)
    # _resolve_path uses os.path.realpath which normalizes any string;
    # _relative_for_protected falls back to the basename when the path is
    # not under any allowed root, so Makefile still matches.
    assert guardrail.is_protected("/nonexistent/path/Makefile") is True
