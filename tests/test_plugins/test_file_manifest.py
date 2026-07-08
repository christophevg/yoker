"""Tests for the file-based manifest (agent.toml) parser."""

from pathlib import Path

import pytest

from yoker.exceptions import PluginError
from yoker.plugins.file_manifest import (
  PluginConfig,
  RunConfig,
  load_file_manifest,
)


class TestLoadFileManifest:
  """Tests for load_file_manifest()."""

  def test_missing_file_returns_none(self, tmp_path: Path) -> None:
    """A non-existent agent.toml returns None (caller decides if that's an error)."""
    result = load_file_manifest(tmp_path / "agent.toml")
    assert result is None

  def test_run_section_parses(self, tmp_path: Path) -> None:
    """The [run] section populates run_config."""
    path = tmp_path / "agent.toml"
    path.write_text(
      '[run]\nagent = "researcher"\nprompt = "Analyze the codebase"\n',
      encoding="utf-8",
    )
    result = load_file_manifest(path)
    assert result is not None
    assert result.run_config == RunConfig(agent="researcher", prompt="Analyze the codebase")

  def test_run_section_partial(self, tmp_path: Path) -> None:
    """[run] with only agent or only prompt leaves the other as None."""
    path = tmp_path / "agent.toml"
    path.write_text('[run]\nagent = "x"\n', encoding="utf-8")
    result = load_file_manifest(path)
    assert result is not None
    assert result.run_config.agent == "x"
    assert result.run_config.prompt is None

  def test_plugin_section_defaults(self, tmp_path: Path) -> None:
    """plugin_config defaults to skills/agents when section is absent."""
    path = tmp_path / "agent.toml"
    path.write_text('[run]\nagent = "x"\n', encoding="utf-8")
    result = load_file_manifest(path)
    assert result is not None
    assert result.plugin_config == PluginConfig()

  def test_plugin_section_parses(self, tmp_path: Path) -> None:
    """The [plugin] section populates plugin_config."""
    path = tmp_path / "agent.toml"
    path.write_text(
      '[plugin]\nskills_dir = "custom_skills"\nagents_dir = "custom_agents"\n'
      'tools_module = "my_plugin.tools"\n',
      encoding="utf-8",
    )
    result = load_file_manifest(path)
    assert result is not None
    assert result.plugin_config == PluginConfig(
      skills_dir="custom_skills",
      agents_dir="custom_agents",
      tools_module="my_plugin.tools",
    )

  def test_config_overrides_extracted(self, tmp_path: Path) -> None:
    """Non-[run]/[plugin] tables are returned as config overrides."""
    path = tmp_path / "agent.toml"
    path.write_text(
      '[run]\nagent = "x"\n\n'
      '[backend.ollama]\nmodel = "llama3.2"\n\n'
      "[tools.git]\nenabled = false\n",
      encoding="utf-8",
    )
    result = load_file_manifest(path)
    assert result is not None
    assert "run" not in result.config_overrides
    assert "plugin" not in result.config_overrides
    assert result.config_overrides["backend"]["ollama"]["model"] == "llama3.2"
    assert result.config_overrides["tools"]["git"]["enabled"] is False

  def test_config_overrides_only(self, tmp_path: Path) -> None:
    """A manifest with only config overrides (no [run]/[plugin]) is valid."""
    path = tmp_path / "agent.toml"
    path.write_text('[ui]\nmode = "batch"\n', encoding="utf-8")
    result = load_file_manifest(path)
    assert result is not None
    assert result.run_config == RunConfig()
    assert result.plugin_config == PluginConfig()
    assert result.config_overrides["ui"]["mode"] == "batch"

  def test_empty_manifest(self, tmp_path: Path) -> None:
    """An empty agent.toml yields empty run/plugin/overrides."""
    path = tmp_path / "agent.toml"
    path.write_text("", encoding="utf-8")
    result = load_file_manifest(path)
    assert result is not None
    assert result.run_config == RunConfig()
    assert result.plugin_config == PluginConfig()
    assert result.config_overrides == {}

  def test_malformed_toml_raises_plugin_error(self, tmp_path: Path) -> None:
    """Malformed TOML raises a PluginError with the file path."""
    path = tmp_path / "agent.toml"
    path.write_text("this is not = = valid toml [[[", encoding="utf-8")
    with pytest.raises(PluginError) as exc:
      load_file_manifest(path)
    assert str(path) in str(exc.value)

  def test_run_wrong_type_raises(self, tmp_path: Path) -> None:
    """[run] that is not a table raises PluginError."""
    path = tmp_path / "agent.toml"
    path.write_text('run = "not a table"\n', encoding="utf-8")
    with pytest.raises(PluginError):
      load_file_manifest(path)

  def test_run_agent_wrong_type_raises(self, tmp_path: Path) -> None:
    """[run].agent that is not a string raises PluginError."""
    path = tmp_path / "agent.toml"
    path.write_text("[run]\nagent = 42\n", encoding="utf-8")
    with pytest.raises(PluginError):
      load_file_manifest(path)

  def test_run_unknown_key_raises(self, tmp_path: Path) -> None:
    """Unknown keys in [run] raise PluginError (fail fast on typos)."""
    path = tmp_path / "agent.toml"
    path.write_text('[run]\nagent = "x"\nbogus = true\n', encoding="utf-8")
    with pytest.raises(PluginError):
      load_file_manifest(path)

  def test_plugin_unknown_key_raises(self, tmp_path: Path) -> None:
    """Unknown keys in [plugin] raise PluginError."""
    path = tmp_path / "agent.toml"
    path.write_text("[plugin]\nbogus = true\n", encoding="utf-8")
    with pytest.raises(PluginError):
      load_file_manifest(path)

  def test_plugin_tools_module_wrong_type_raises(self, tmp_path: Path) -> None:
    """[plugin].tools_module that is not a string raises PluginError."""
    path = tmp_path / "agent.toml"
    path.write_text("[plugin]\ntools_module = 123\n", encoding="utf-8")
    with pytest.raises(PluginError):
      load_file_manifest(path)

  def test_does_not_import_tools_module(self, tmp_path: Path) -> None:
    """The parser must not import tools_module (deferred to the loader)."""
    path = tmp_path / "agent.toml"
    path.write_text(
      '[plugin]\ntools_module = "this.module.should.not.be.imported"\n', encoding="utf-8"
    )
    result = load_file_manifest(path)
    assert result is not None
    # The value is kept as a string; no import attempted.
    assert result.plugin_config.tools_module == "this.module.should.not.be.imported"
