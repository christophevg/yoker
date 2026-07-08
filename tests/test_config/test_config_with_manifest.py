"""Tests for get_yoker_config_with_manifest() — manifest override layer."""

from importlib import reload
from pathlib import Path

import pytest
from clevis import _reset_factories

from yoker.config import Config, get_yoker_config_with_manifest
from yoker.plugins.file_manifest import PluginConfig, RunConfig


def _restore_subcommand_factories() -> None:
  """Re-register the @configclass(cmd=...) subcommand configs.

  _reset_factories() wipes all factories, including the subcommand configs
  registered by yoker.cli.commands at import time. Reimporting that module is
  a no-op (sys.modules cache), so reload() is used to re-run the decorators.
  """
  import yoker.cli.commands

  reload(yoker.cli.commands)


class TestGetYokerConfigWithManifest:
  """Tests for the manifest-aware config loader."""

  @pytest.fixture(autouse=True)
  def _isolate_clevis(self):
    """Reset clevis global state around each test and restore subcommand configs.

    get_yoker_config_with_manifest(cli=True) calls get_factory(Config), which
    registers Config's factory on clevis's shared default parser. Config has no
    ``cmd``, so its args land on the root parser alongside the subparser group
    declared by the @configclass(cmd=...) subcommand configs (task 4.1). That
    root-level configuration leaks across tests and breaks the main() dispatch
    tests. Setup wipes global state for a clean parser; teardown wipes again
    and re-registers the subcommand configs other tests rely on.
    """
    _reset_factories()
    yield
    _reset_factories()
    _restore_subcommand_factories()

  def test_no_manifest_returns_defaults(self, tmp_path: Path, monkeypatch) -> None:
    """With manifest_path=None, behaves like get_yoker_config() with empty run/plugin."""
    # Isolate from the user/project TOML by pointing HOME and cwd at tmp_path.
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    config, run_config, plugin_config = get_yoker_config_with_manifest(None, cli=False)

    assert isinstance(config, Config)
    assert run_config == RunConfig()
    assert plugin_config == PluginConfig()
    # Defaults preserved (no manifest, no TOML).
    assert config.backend.provider == "ollama"

  def test_missing_manifest_file_returns_defaults(self, tmp_path: Path, monkeypatch) -> None:
    """A manifest_path that doesn't exist is treated as no manifest."""
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    config, run_config, plugin_config = get_yoker_config_with_manifest(
      tmp_path / "agent.toml", cli=False
    )

    assert isinstance(config, Config)
    assert run_config == RunConfig()
    assert plugin_config == PluginConfig()

  def test_manifest_overrides_backend_model(self, tmp_path: Path, monkeypatch) -> None:
    """A [backend.ollama] model override is applied to the merged config."""
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text('[backend.ollama]\nmodel = "llama3.2"\n', encoding="utf-8")

    config, run_config, plugin_config = get_yoker_config_with_manifest(manifest_path, cli=False)

    assert config.backend.ollama.model == "llama3.2"
    # Other ollama fields preserved (deep merge, not replace).
    assert config.backend.ollama.base_url == "http://localhost:11434"
    assert run_config == RunConfig()
    assert plugin_config == PluginConfig()

  def test_manifest_run_and_plugin_sections_extracted(self, tmp_path: Path, monkeypatch) -> None:
    """[run] and [plugin] are extracted and returned, not merged into Config."""
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text(
      '[run]\nagent = "researcher"\nprompt = "Analyze"\n\n'
      '[plugin]\nskills_dir = "s"\nagents_dir = "a"\n'
      'tools_module = "m.tools"\n',
      encoding="utf-8",
    )

    config, run_config, plugin_config = get_yoker_config_with_manifest(manifest_path, cli=False)

    assert run_config == RunConfig(agent="researcher", prompt="Analyze")
    assert plugin_config == PluginConfig(skills_dir="s", agents_dir="a", tools_module="m.tools")
    # [run] and [plugin] must NOT leak into the Config tree.
    assert not hasattr(config, "run")
    assert not hasattr(config, "plugin")

  def test_manifest_disables_tool(self, tmp_path: Path, monkeypatch) -> None:
    """A [tools.<name>] enabled=false override is applied."""
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text("[tools.git]\nenabled = false\n", encoding="utf-8")

    config, _, _ = get_yoker_config_with_manifest(manifest_path, cli=False)

    assert config.tools.git.enabled is False
    # Other tool untouched.
    assert config.tools.read.enabled is True

  def test_manifest_overrides_ui_mode(self, tmp_path: Path, monkeypatch) -> None:
    """A [ui] mode override is applied."""
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text('[ui]\nmode = "batch"\n', encoding="utf-8")

    config, _, _ = get_yoker_config_with_manifest(manifest_path, cli=False)

    assert config.ui.mode == "batch"

  def test_cli_overrides_manifest(self, tmp_path: Path, monkeypatch) -> None:
    """CLI args take precedence over manifest overrides."""
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text('[backend.ollama]\nmodel = "from-manifest"\n', encoding="utf-8")

    monkeypatch.setattr(
      "sys.argv",
      ["yoker", "--backend-ollama-model", "from-cli"],
    )

    config, _, _ = get_yoker_config_with_manifest(manifest_path, cli=True)

    assert config.backend.ollama.model == "from-cli"

  def test_malformed_manifest_raises_plugin_error(self, tmp_path: Path, monkeypatch) -> None:
    """A malformed agent.toml surfaces as PluginError."""
    from yoker.exceptions import PluginError

    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    manifest_path = tmp_path / "agent.toml"
    manifest_path.write_text("not = = valid [[[", encoding="utf-8")

    with pytest.raises(PluginError):
      get_yoker_config_with_manifest(manifest_path, cli=False)
