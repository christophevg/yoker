"""Tests for the ``yoker init`` subcommand handler (MBI-004 task 4.3)."""

import os
import stat
from unittest.mock import MagicMock

import pytest

from yoker.cli.config_cmd import _mask_value
from yoker.cli.init import (
  _confirm_overwrite,
  _resolve_path,
  _write_default_config,
  run_init,
)


class TestResolvePath:
  """Test --path resolution and forbidden-prefix validation."""

  def test_default_path_is_home_yoker_toml(self, tmp_path, monkeypatch):
    """When --path is not given, default to ~/.yoker.toml."""
    monkeypatch.setattr("yoker.cli.init._default_config_path", lambda: tmp_path / ".yoker.toml")
    result = _resolve_path(None)
    assert result == tmp_path / ".yoker.toml"

  def test_custom_path_resolved(self, tmp_path):
    """--path with a valid path is returned resolved."""
    custom = tmp_path / "custom.toml"
    result = _resolve_path(str(custom))
    assert result == custom.resolve()

  def test_forbidden_path_prefix_rejected(self):
    """--path under /etc is rejected with a ValidationError exit."""
    with pytest.raises(SystemExit) as exc_info:
      _resolve_path("/etc/yoker.toml")
    assert exc_info.value.code == 1

  def test_forbidden_path_usr_rejected(self):
    """--path under /usr is rejected."""
    with pytest.raises(SystemExit) as exc_info:
      _resolve_path("/usr/local/yoker.toml")
    assert exc_info.value.code == 1


class TestWriteDefaultConfig:
  """Test non-interactive default config writing."""

  def test_writes_default_config(self, tmp_path):
    """--no-interactive writes a valid TOML config file."""
    target = tmp_path / "yoker.toml"
    _write_default_config(target, force=False)
    assert target.exists()
    content = target.read_text()
    assert "[backend" in content
    assert "chmod 600" not in content  # that's the stdout message

  def test_written_file_has_0600_permissions(self, tmp_path):
    """Written config file has chmod 0600."""
    target = tmp_path / "yoker.toml"
    _write_default_config(target, force=False)
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600

  def test_refuses_overwrite_without_force(self, tmp_path):
    """Existing file is not overwritten without --force."""
    target = tmp_path / "yoker.toml"
    target.write_text("existing config\n")
    with pytest.raises(SystemExit) as exc_info:
      _write_default_config(target, force=False)
    assert exc_info.value.code == 1
    assert target.read_text() == "existing config\n"

  def test_force_overwrites_existing_file(self, tmp_path):
    """--force overwrites an existing file."""
    target = tmp_path / "yoker.toml"
    target.write_text("existing config\n")
    _write_default_config(target, force=True)
    content = target.read_text()
    assert "existing config" not in content
    assert "[backend" in content

  def test_confirmation_message_printed(self, tmp_path, capsys):
    """A confirmation message with the path is printed after writing."""
    target = tmp_path / "yoker.toml"
    _write_default_config(target, force=False)
    captured = capsys.readouterr()
    assert str(target) in captured.out
    assert "chmod 600" in captured.out


class TestMaskValue:
  """Test API key masking helper (shared with config_cmd)."""

  def test_short_key_masked_as_stars(self):
    """Keys <= 4 chars are fully masked."""
    assert _mask_value("abc") == "***"

  def test_long_key_shows_last_four(self):
    """Keys > 4 chars show ***... plus last 4 chars."""
    assert _mask_value("sk-abcdef1234") == "***...1234"

  def test_exactly_four_chars_masked(self):
    """Keys of exactly 4 chars are fully masked."""
    assert _mask_value("abcd") == "***"


class TestConfirmOverwrite:
  """Test interactive overwrite confirmation."""

  def test_yes_confirms(self, tmp_path, monkeypatch):
    """Answering 'y' confirms the overwrite."""
    monkeypatch.setattr("sys.stdin", MagicMock(readline=lambda: "y\n"))
    assert _confirm_overwrite(tmp_path / "test.toml") is True

  def test_no_rejects(self, tmp_path, monkeypatch):
    """Answering 'n' rejects the overwrite."""
    monkeypatch.setattr("sys.stdin", MagicMock(readline=lambda: "n\n"))
    assert _confirm_overwrite(tmp_path / "test.toml") is False

  def test_empty_answer_rejects(self, tmp_path, monkeypatch):
    """Empty answer (just Enter) rejects the overwrite."""
    monkeypatch.setattr("sys.stdin", MagicMock(readline=lambda: "\n"))
    assert _confirm_overwrite(tmp_path / "test.toml") is False

  def test_eof_rejects(self, tmp_path, monkeypatch):
    """EOF on stdin rejects the overwrite."""
    monkeypatch.setattr("sys.stdin", MagicMock(readline=lambda: ""))
    assert _confirm_overwrite(tmp_path / "test.toml") is False


class TestRunInit:
  """Test the top-level run_init dispatch."""

  def test_no_interactive_writes_defaults(self, tmp_path, monkeypatch):
    """run_init with --no-interactive writes a default config file."""
    target = tmp_path / "yoker.toml"

    # Patch Clevis to return an InitConfig with no_interactive=True
    init_config = MagicMock()
    init_config.no_interactive = True
    init_config.path = str(target)
    init_config.force = False

    monkeypatch.setattr("yoker.cli.init.load_subcommand_config", lambda cls: init_config)
    run_init()
    assert target.exists()
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600
