"""Tests for the ``yoker config`` subcommand handler (MBI-004 task 4.4)."""

import json
from unittest.mock import patch

from yoker.cli.commands import ConfigCmdConfig
from yoker.cli.config_cmd import (
  _dataclass_to_dict,
  _mask_api_keys,
  _mask_value,
  run_config_cmd,
)
from yoker.config import Config
from yoker.config.providers import OpenAIConfig


def _make_config_cmd(**kwargs) -> ConfigCmdConfig:
  """Build a ConfigCmdConfig with defaults, overriding given kwargs."""
  defaults = {"json": False, "show_path": False, "reveal": False}
  defaults.update(kwargs)
  return ConfigCmdConfig(**defaults)


class TestMaskApiKeys:
  """Test API key masking in config output."""

  def test_ollama_api_key_masked(self):
    """Ollama api_key is masked by default."""
    config = _make_config_cmd()
    config.backend.ollama.api_key = "sk-secret-key-1234"
    masked = _mask_api_keys(config)
    assert masked.backend.ollama.api_key == "***...1234"

  def test_openai_api_key_masked(self):
    """OpenAI api_key is masked by default."""
    config = _make_config_cmd()
    config.backend.openai = OpenAIConfig(api_key="sk-proj-abcdef7890")
    masked = _mask_api_keys(config)
    assert masked.backend.openai.api_key == "***...7890"

  def test_none_api_key_stays_none(self):
    """None api_key is not masked (stays None, omitted from output)."""
    config = _make_config_cmd()
    assert config.backend.ollama.api_key is None
    masked = _mask_api_keys(config)
    assert masked.backend.ollama.api_key is None

  def test_original_config_not_mutated(self):
    """Masking does not mutate the original config."""
    config = _make_config_cmd()
    config.backend.ollama.api_key = "sk-secret-key-1234"
    _mask_api_keys(config)
    assert config.backend.ollama.api_key == "sk-secret-key-1234"


class TestMaskValue:
  """Test the _mask_value helper."""

  def test_short_key_masked(self):
    assert _mask_value("ab") == "***"

  def test_long_key_shows_last_four(self):
    assert _mask_value("sk-abcdef1234") == "***...1234"

  def test_empty_string_masked(self):
    assert _mask_value("") == "***"


class TestDataclassToDict:
  """Test JSON serialization helper."""

  def test_simple_config_converts(self):
    """A default Config converts to a dict without errors."""
    config = Config()
    result = _dataclass_to_dict(config)
    assert isinstance(result, dict)
    assert "backend" in result
    assert isinstance(result["backend"], dict)

  def test_none_values_omitted(self):
    """None values are omitted from the dict."""
    config = Config()
    result = _dataclass_to_dict(config)
    # agent is None by default
    assert "agent" not in result


class TestRunConfigCmd:
  """Test the top-level run_config_cmd dispatch."""

  def test_outputs_toml_by_default(self, capsys):
    """run_config_cmd prints TOML by default."""
    config = _make_config_cmd()
    with patch("yoker.cli.config_cmd.load_subcommand_config", return_value=config):
      with patch(
        "yoker.cli.config_cmd.render_config_toml",
        return_value='[backend]\nprovider = "ollama"\n',
      ):
        run_config_cmd()

    captured = capsys.readouterr()
    assert "backend" in captured.out
    assert "ollama" in captured.out

  def test_outputs_json_with_flag(self, capsys):
    """run_config_cmd --json prints JSON."""
    config = _make_config_cmd(json=True)
    with patch("yoker.cli.config_cmd.load_subcommand_config", return_value=config):
      run_config_cmd()

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed, dict)
    assert "backend" in parsed

  def test_show_path_prints_paths(self, capsys, tmp_path, monkeypatch):
    """--show-path prints the config file paths that exist."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    user_config = fake_home / ".yoker.toml"
    user_config.write_text('[backend]\nprovider = "ollama"\n')

    monkeypatch.setattr("yoker.cli.config_cmd.Path.home", lambda: fake_home)
    monkeypatch.setattr("yoker.cli.config_cmd.Path.cwd", lambda: tmp_path)

    config = _make_config_cmd(show_path=True)
    with patch("yoker.cli.config_cmd.load_subcommand_config", return_value=config):
      with patch("yoker.cli.config_cmd.render_config_toml", return_value="dummy\n"):
        run_config_cmd()

    captured = capsys.readouterr()
    assert "user:" in captured.out
    assert str(user_config) in captured.out

  def test_show_path_no_files_found(self, capsys, tmp_path, monkeypatch):
    """--show-path with no config files prints a 'not found' message."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("yoker.cli.config_cmd.Path.home", lambda: fake_home)
    monkeypatch.setattr("yoker.cli.config_cmd.Path.cwd", lambda: tmp_path)

    config = _make_config_cmd(show_path=True)
    with patch("yoker.cli.config_cmd.load_subcommand_config", return_value=config):
      with patch("yoker.cli.config_cmd.render_config_toml", return_value="dummy\n"):
        run_config_cmd()

    captured = capsys.readouterr()
    assert "No config files found" in captured.out

  def test_api_key_masked_in_toml_output(self, capsys):
    """API keys are masked in TOML output by default."""
    config = _make_config_cmd(reveal=False)
    config.backend.ollama.api_key = "sk-secret-key-1234"
    with patch("yoker.cli.config_cmd.load_subcommand_config", return_value=config):
      run_config_cmd()

    captured = capsys.readouterr()
    assert "sk-secret-key-1234" not in captured.out
    assert "***...1234" in captured.out

  def test_api_key_revealed_with_flag(self, capsys):
    """API keys are shown in full with --reveal."""
    config = _make_config_cmd(reveal=True)
    config.backend.ollama.api_key = "sk-secret-key-1234"
    with patch("yoker.cli.config_cmd.load_subcommand_config", return_value=config):
      run_config_cmd()

    captured = capsys.readouterr()
    assert "sk-secret-key-1234" in captured.out
