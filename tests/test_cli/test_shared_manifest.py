"""Tests for load_subcommand_config_with_manifest() — subcommand-aware manifest cascade.

Covers the 5-step config cascade in :func:`yoker.cli.shared.load_subcommand_config_with_manifest`:
dataclass defaults -> user TOML -> project TOML -> subcommand section extraction ->
manifest overrides -> CLI args (highest priority).

These tests complement ``test_config_with_manifest.py`` (which tests the base
``Config`` cascade via ``get_yoker_config_with_manifest``) by exercising the
subcommand-specific variant used by ``yoker run`` and ``yoker loop``.
"""

from __future__ import annotations

import sys
from importlib import reload
from pathlib import Path

import pytest
from clevis import _reset_factories

import yoker.cli.commands
from yoker.cli.shared import load_subcommand_config, load_subcommand_config_with_manifest


def _restore_subcommand_factories() -> None:
  """Re-register the @configclass(cmd=...) subcommand configs after _reset_factories."""
  reload(yoker.cli.commands)


class TestLoadSubcommandConfigWithManifest:
  """Direct tests for the subcommand-aware manifest config cascade."""

  @pytest.fixture(autouse=True)
  def _isolate_clevis(self, tmp_path: Path, monkeypatch):
    """Reset Clevis global state and re-register subcommand configs for each test.

    The function under test calls ``get_factory(RunConfig)``, which needs the
    ``cmd="run"`` attribute set by ``@configclass(cmd="run")``. After
    ``_reset_factories()``, the factory is gone, so we reload
    ``yoker.cli.commands`` to re-run the decorators.

    ``reload`` creates new class objects, so tests must reference
    ``yoker.cli.commands.RunConfig`` (the reloaded class) rather than a
    top-level import, which would point at the pre-reload class and have no
    registered factory.
    """
    _reset_factories()
    _restore_subcommand_factories()
    # Isolate from real TOML files and security checks.
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    yield
    _reset_factories()
    _restore_subcommand_factories()

  def test_manifest_overrides_base_toml(self, tmp_path: Path) -> None:
    """Manifest config_overrides override base TOML values."""
    project_toml = tmp_path / "yoker.toml"
    project_toml.write_text('[backend.ollama]\nmodel = "from-toml"\n', encoding="utf-8")
    sys.argv = ["yoker", "run"]

    config = load_subcommand_config_with_manifest(
      yoker.cli.commands.RunConfig,
      {"backend": {"ollama": {"model": "from-manifest"}}},
    )

    assert config.backend.ollama.model == "from-manifest"

  def test_cli_wins_over_manifest(self, tmp_path: Path) -> None:
    """CLI args take priority over manifest overrides."""
    project_toml = tmp_path / "yoker.toml"
    project_toml.write_text('[backend.ollama]\nmodel = "from-toml"\n', encoding="utf-8")
    sys.argv = ["yoker", "run", "--backend-ollama-model", "from-cli"]

    config = load_subcommand_config_with_manifest(
      yoker.cli.commands.RunConfig,
      {"backend": {"ollama": {"model": "from-manifest"}}},
    )

    assert config.backend.ollama.model == "from-cli"

  def test_subcommand_section_extracted(self, tmp_path: Path) -> None:
    """The [run] section is extracted and replaces root-level TOML values."""
    project_toml = tmp_path / "yoker.toml"
    project_toml.write_text(
      'source = "root-source"\n\n[run]\nsource = "section-source"\n',
      encoding="utf-8",
    )
    sys.argv = ["yoker", "run"]

    config = load_subcommand_config_with_manifest(yoker.cli.commands.RunConfig, {})

    # [run] section is extracted to root level — section value wins over root.
    assert config.source == "section-source"

  def test_empty_overrides_matches_load_subcommand_config(self, tmp_path: Path) -> None:
    """Empty config_overrides dict behaves like load_subcommand_config()."""
    project_toml = tmp_path / "yoker.toml"
    project_toml.write_text('[backend.ollama]\nmodel = "base-model"\n', encoding="utf-8")
    sys.argv = ["yoker", "run"]

    RunConfig = yoker.cli.commands.RunConfig
    with_manifest = load_subcommand_config_with_manifest(RunConfig, {})
    without_manifest = load_subcommand_config(RunConfig)

    assert with_manifest.backend.ollama.model == "base-model"
    assert without_manifest.backend.ollama.model == "base-model"
    assert with_manifest.source == without_manifest.source

  def test_validation_runs_on_final_config(self, tmp_path: Path) -> None:
    """Invalid config values raise errors via __post_init__ validation.

    BackendConfig.__post_init__ validates that known providers have their
    corresponding config. Setting provider to "openai" without an openai
    config triggers a ValidationError.
    """
    from yoker.exceptions import ValidationError

    sys.argv = ["yoker", "run"]

    with pytest.raises(ValidationError):
      load_subcommand_config_with_manifest(
        yoker.cli.commands.RunConfig,
        {"backend": {"provider": "openai", "openai": None}},
      )

  def test_manifest_overrides_user_toml(self, tmp_path: Path) -> None:
    """Manifest overrides take precedence over user TOML (~/.yoker.toml)."""
    user_toml = tmp_path / ".yoker.toml"
    user_toml.write_text('[backend.ollama]\nmodel = "user-model"\n', encoding="utf-8")
    sys.argv = ["yoker", "run"]

    config = load_subcommand_config_with_manifest(
      yoker.cli.commands.RunConfig,
      {"backend": {"ollama": {"model": "manifest-model"}}},
    )

    assert config.backend.ollama.model == "manifest-model"
