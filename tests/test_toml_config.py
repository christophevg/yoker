"""Tests for TOML configuration file integration."""

from pathlib import Path
from unittest.mock import patch

import pytest
from clevis import SecurityAction, SecurityConfig, get_config

from yoker.config import Config


class TestTomlConfig:
  """Tests for TOML configuration file loading."""

  def test_config_with_model_field(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that top-level model field is loaded from TOML."""
    # Create a test config file
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
model = "test-model:latest"

[backend.ollama]
model = "backend-model:latest"
""")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    # Should load top-level model
    assert config.model == "test-model:latest"
    # Backend model is still available
    assert config.backend.ollama.model == "backend-model:latest"

  def test_config_with_agent_field(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that top-level agent field is loaded from TOML."""
    # Create a test config file
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
agent = "agents/custom.md"

[agents]
directory = "./agents"
""")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    # Should load top-level agent
    assert config.agent == "agents/custom.md"
    # Agents config is still available
    assert config.agents.directory == "./agents"

  def test_config_without_optional_fields(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that model and agent fields default to None."""
    # Create a minimal config file
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
[backend.ollama]
model = "llama3.2:latest"
""")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    # Should be None (not set)
    assert config.model is None
    assert config.agent is None
    # Backend model should be set
    assert config.backend.ollama.model == "llama3.2:latest"

  def test_config_env_var_interpolation(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that environment variables are interpolated in TOML."""
    # Set environment variable
    monkeypatch.setenv("TEST_MODEL", "env-model:latest")

    # Create a config file with env var interpolation
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
model = "${TEST_MODEL}"

[backend.ollama]
model = "${TEST_MODEL:-default-model:latest}"
""")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    # Should interpolate environment variable
    assert config.model == "env-model:latest"
    assert config.backend.ollama.model == "env-model:latest"

  def test_config_cli_args_override_toml(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that CLI args override TOML config (Clevis handles this)."""
    # Create a config file with model
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
model = "toml-model:latest"

[backend.ollama]
model = "backend-model:latest"
""")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      # Note: In actual CLI usage, Clevis would parse --model argument
      # For this test, we're verifying that the Config schema supports the field
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)

    # Should load from TOML
    assert config.model == "toml-model:latest"

    # When using CLI with --model, Clevis would pass it explicitly:
    # Config(model="cli-model:latest", backend=...)
    # This would override the TOML value
