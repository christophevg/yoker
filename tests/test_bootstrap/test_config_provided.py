"""Tests for :func:`yoker.bootstrap.config_provided` (MBI-002 task 2.1).

These are logic tests (not IO): the boolean decision, file-existence checks,
``~`` expansion, override-path plumbing, and CLI-arg detection.
"""

from pathlib import Path

import pytest

from yoker.bootstrap import config_provided


class TestConfigProvidedFiles:
  """File-existence based detection."""

  def test_no_config_no_cli_returns_false(self, tmp_path: Path) -> None:
    """No config files and no CLI args -> False (wizard would trigger)."""
    assert (
      config_provided(
        user_config_path=tmp_path / "home.yml",
        project_config_path=tmp_path / "proj.yml",
        cli_args=(),
      )
      is False
    )

  def test_user_config_exists_returns_true(self, tmp_path: Path) -> None:
    """A user-level config file -> True."""
    user = tmp_path / ".yoker.toml"
    user.write_text("# empty", encoding="utf-8")
    assert (
      config_provided(
        user_config_path=user,
        project_config_path=tmp_path / "absent.toml",
        cli_args=(),
      )
      is True
    )

  def test_project_config_exists_returns_true(self, tmp_path: Path) -> None:
    """A project-level config file -> True."""
    project = tmp_path / "yoker.toml"
    project.write_text("# empty", encoding="utf-8")
    assert (
      config_provided(
        user_config_path=tmp_path / "absent.toml",
        project_config_path=project,
        cli_args=(),
      )
      is True
    )

  def test_both_files_exist_returns_true(self, tmp_path: Path) -> None:
    """Both config files -> True."""
    user = tmp_path / ".yoker.toml"
    project = tmp_path / "yoker.toml"
    user.write_text("x = 1", encoding="utf-8")
    project.write_text("y = 2", encoding="utf-8")
    assert (
      config_provided(
        user_config_path=user,
        project_config_path=project,
        cli_args=(),
      )
      is True
    )

  def test_empty_toml_file_counts_as_provided(self, tmp_path: Path) -> None:
    """An empty (but consciously created) file is still "provided"."""
    user = tmp_path / ".yoker.toml"
    user.write_text("", encoding="utf-8")
    assert (
      config_provided(
        user_config_path=user,
        project_config_path=tmp_path / "absent.toml",
        cli_args=(),
      )
      is True
    )


class TestConfigProvidedCLI:
  """CLI-arg based detection."""

  def test_yoker_flag_returns_true(self, tmp_path: Path) -> None:
    """A single yoker-related CLI flag -> True."""
    assert (
      config_provided(
        user_config_path=tmp_path / "a.toml",
        project_config_path=tmp_path / "b.toml",
        cli_args=["--backend-ollama-model", "gpt-oss:latest"],
      )
      is True
    )

  def test_ui_flag_returns_true(self, tmp_path: Path) -> None:
    """A UI flag is a yoker flag too."""
    assert (
      config_provided(
        user_config_path=tmp_path / "a.toml",
        project_config_path=tmp_path / "b.toml",
        cli_args=["--ui-mode", "batch"],
      )
      is True
    )

  def test_help_only_returns_false(self, tmp_path: Path) -> None:
    """``--help`` is not configuration -> False."""
    assert (
      config_provided(
        user_config_path=tmp_path / "a.toml",
        project_config_path=tmp_path / "b.toml",
        cli_args=["--help"],
      )
      is False
    )

  def test_with_flag_does_not_count(self, tmp_path: Path) -> None:
    """``--with`` selects plugins, not configuration -> False."""
    assert (
      config_provided(
        user_config_path=tmp_path / "a.toml",
        project_config_path=tmp_path / "b.toml",
        cli_args=["--with", "pkgq"],
      )
      is False
    )

  def test_empty_cli_returns_false(self, tmp_path: Path) -> None:
    assert (
      config_provided(
        user_config_path=tmp_path / "a.toml",
        project_config_path=tmp_path / "b.toml",
        cli_args=(),
      )
      is False
    )

  def test_unknown_flag_returns_false(self, tmp_path: Path) -> None:
    """An unrelated flag is not a yoker config override."""
    assert (
      config_provided(
        user_config_path=tmp_path / "a.toml",
        project_config_path=tmp_path / "b.toml",
        cli_args=["--unknown-flag", "value"],
      )
      is False
    )


class TestConfigProvidedPaths:
  """Path handling."""

  def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``~`` in the user config path is expanded."""
    real = tmp_path / "realhome"
    real.mkdir()
    monkeypatch.setenv("HOME", str(real))
    user_path = Path("~/.yoker.toml")
    # File does not exist -> False via tilde-expanded path
    assert (
      config_provided(
        user_config_path=user_path,
        project_config_path=tmp_path / "absent.toml",
        cli_args=(),
      )
      is False
    )
    # Create the file at the expanded location and re-check
    (real / ".yoker.toml").write_text("x = 1", encoding="utf-8")
    assert (
      config_provided(
        user_config_path=user_path,
        project_config_path=tmp_path / "absent.toml",
        cli_args=(),
      )
      is True
    )

  def test_file_overrides_cli_check_short_circuits(self, tmp_path: Path) -> None:
    """When a file exists, CLI args are not consulted (but result is True)."""
    user = tmp_path / ".yoker.toml"
    user.write_text("x = 1", encoding="utf-8")
    assert (
      config_provided(
        user_config_path=user,
        project_config_path=tmp_path / "absent.toml",
        cli_args=["--help"],
      )
      is True
    )
