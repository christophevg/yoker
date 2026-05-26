"""Tests for environment variable configuration."""

import os
from pathlib import Path

import pytest

from yoker.config import (
  BackendConfig,
  Config,
  HarnessConfig,
  OllamaConfig,
  load_config,
  load_env_config,
  merge_configs,
)
from yoker.config.loader import _coerce_value, _get_env_var_name


class TestEnvVarNames:
  """Tests for environment variable name generation."""

  def test_simple_field(self) -> None:
    """Test simple field name conversion."""
    assert _get_env_var_name(("harness", "name")) == "YOKER_HARNESS_NAME"
    assert _get_env_var_name(("backend", "provider")) == "YOKER_BACKEND_PROVIDER"

  def test_nested_field(self) -> None:
    """Test nested field name conversion."""
    assert _get_env_var_name(("backend", "ollama", "model")) == "YOKER_BACKEND_OLLAMA_MODEL"
    assert _get_env_var_name(("backend", "ollama", "base_url")) == "YOKER_BACKEND_OLLAMA_BASE_URL"

  def test_with_prefix(self) -> None:
    """Test prefix support."""
    assert (
      _get_env_var_name(("backend", "ollama", "model"), "MYAPP")
      == "MYAPP_YOKER_BACKEND_OLLAMA_MODEL"
    )
    assert _get_env_var_name(("harness", "name"), "MYAPP") == "MYAPP_YOKER_HARNESS_NAME"


class TestTypeCoercion:
  """Tests for type coercion from environment variables."""

  def test_string(self) -> None:
    """Test string coercion."""
    assert _coerce_value("hello", str) == "hello"
    assert _coerce_value("llama3.2:latest", str) == "llama3.2:latest"

  def test_integer(self) -> None:
    """Test integer coercion."""
    assert _coerce_value("60", int) == 60
    assert _coerce_value("0", int) == 0
    assert _coerce_value("-1", int) == -1

  def test_float(self) -> None:
    """Test float coercion."""
    assert _coerce_value("0.7", float) == 0.7
    assert _coerce_value("3.14", float) == 3.14

  def test_boolean_true(self) -> None:
    """Test boolean true coercion."""
    for value in ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]:
      assert _coerce_value(value, bool) is True

  def test_boolean_false(self) -> None:
    """Test boolean false coercion."""
    for value in ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]:
      assert _coerce_value(value, bool) is False

  def test_boolean_invalid(self) -> None:
    """Test boolean coercion with invalid value."""
    with pytest.raises(ValueError):
      _coerce_value("maybe", bool)

  def test_tuple(self) -> None:
    """Test tuple coercion (comma-separated)."""
    result = _coerce_value("/path1,/path2,/path3", tuple)
    assert result == ("/path1", "/path2", "/path3")

  def test_tuple_with_spaces(self) -> None:
    """Test tuple coercion with spaces."""
    result = _coerce_value(" /path1 , /path2 , /path3 ", tuple)
    assert result == ("/path1", "/path2", "/path3")

  def test_empty_tuple(self) -> None:
    """Test empty tuple."""
    result = _coerce_value("", tuple)
    assert result == ()


class TestLoadEnvConfig:
  """Tests for load_env_config function."""

  def test_no_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test with no environment variables set."""
    # Clear any existing YOKER env vars
    for key in list(os.environ.keys()):
      if key.startswith("YOKER_"):
        monkeypatch.delenv(key, raising=False)

    result = load_env_config()
    assert result == {}

  def test_simple_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test simple string env var."""
    monkeypatch.setenv("YOKER_HARNESS_NAME", "my-project")
    result = load_env_config()
    assert result == {"harness": {"name": "my-project"}}

  def test_nested_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test nested configuration from env vars."""
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_MODEL", "llama3.2:latest")
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_BASE_URL", "http://custom:11434")

    result = load_env_config()
    assert result == {
      "backend": {
        "ollama": {
          "model": "llama3.2:latest",
          "base_url": "http://custom:11434",
        }
      }
    }

  def test_integer_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test integer environment variable."""
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_TIMEOUT_SECONDS", "120")
    result = load_env_config()
    assert result == {"backend": {"ollama": {"timeout_seconds": 120}}}

  def test_boolean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test boolean environment variable."""
    monkeypatch.setenv("YOKER_CONTEXT_PERSIST_AFTER_TURN", "true")
    result = load_env_config()
    assert result == {"context": {"persist_after_turn": True}}

  def test_list_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test list (comma-separated) environment variable."""
    monkeypatch.setenv("YOKER_PERMISSIONS_FILESYSTEM_PATHS", "/workspace,/docs,/tmp")
    result = load_env_config()
    assert result == {"permissions": {"filesystem_paths": ("/workspace", "/docs", "/tmp")}}

  def test_multiple_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test multiple environment variables."""
    monkeypatch.setenv("YOKER_HARNESS_NAME", "test-harness")
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_MODEL", "codellama")
    monkeypatch.setenv("YOKER_CONTEXT_MANAGER", "compaction")

    result = load_env_config()
    assert result == {
      "harness": {"name": "test-harness"},
      "backend": {"ollama": {"model": "codellama"}},
      "context": {"manager": "compaction"},
    }

  def test_with_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test prefix support (YOKER_PREFIX)."""
    # Set the prefix
    monkeypatch.setenv("YOKER_PREFIX", "MYAPP")
    # Set env vars with prefix
    monkeypatch.setenv("MYAPP_YOKER_HARNESS_NAME", "myapp-project")
    # Set unprefixed env var (should be ignored when prefix is set)
    monkeypatch.setenv("YOKER_HARNESS_NAME", "ignored")

    result = load_env_config()
    assert result == {"harness": {"name": "myapp-project"}}

  def test_explicit_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test explicit prefix parameter (not from YOKER_PREFIX)."""
    # Set env vars with custom prefix
    monkeypatch.setenv("CUSTOM_YOKER_HARNESS_NAME", "custom-project")

    result = load_env_config(prefix="CUSTOM")
    assert result == {"harness": {"name": "custom-project"}}

  def test_invalid_env_var_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid env vars are logged but don't fail."""
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_TIMEOUT_SECONDS", "not-a-number")
    # Should not raise, just log warning
    result = load_env_config()
    # Invalid value should be ignored
    assert result == {}

  def test_unknown_env_var_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that unknown env vars are ignored."""
    monkeypatch.setenv("YOKER_UNKNOWN_FIELD", "value")
    monkeypatch.setenv("YOKER_BACKEND_UNKNOWN", "value")
    result = load_env_config()
    # Unknown fields should be ignored
    assert result == {}


class TestMergeConfigs:
  """Tests for merge_configs function."""

  def test_empty_overrides(self) -> None:
    """Test merging with empty overrides."""
    base = Config()
    result = merge_configs(base, {})
    assert result == base

  def test_override_string(self) -> None:
    """Test overriding string value."""
    base = Config()
    overrides = {"harness": {"name": "overridden"}}
    result = merge_configs(base, overrides)
    assert result.harness.name == "overridden"
    # Other values should remain default
    assert result.harness.version == "1.0"

  def test_override_nested(self) -> None:
    """Test overriding nested value."""
    base = Config()
    overrides = {"backend": {"ollama": {"model": "codellama"}}}
    result = merge_configs(base, overrides)
    assert result.backend.ollama.model == "codellama"
    # Other values should remain default
    assert result.backend.ollama.base_url == "http://localhost:11434"

  def test_override_preserves_other_fields(self) -> None:
    """Test that overriding preserves other fields in same section."""
    base = Config(harness=HarnessConfig(name="original", version="1.0"))
    overrides = {"harness": {"name": "new"}}
    result = merge_configs(base, overrides)
    assert result.harness.name == "new"
    assert result.harness.version == "1.0"

  def test_multiple_overrides(self) -> None:
    """Test multiple overrides."""
    base = Config()
    overrides = {
      "harness": {"name": "test"},
      "backend": {"ollama": {"model": "llama3"}},
      "context": {"manager": "compaction"},
    }
    result = merge_configs(base, overrides)
    assert result.harness.name == "test"
    assert result.backend.ollama.model == "llama3"
    assert result.context.manager == "compaction"

  def test_override_creates_new_config(self) -> None:
    """Test that merge creates new Config (immutability)."""
    base = Config()
    overrides = {"harness": {"name": "modified"}}
    result = merge_configs(base, overrides)
    # Base should be unchanged
    assert base.harness.name == "yoker"
    # Result should have override
    assert result.harness.name == "modified"


class TestEnvVarPriority:
  """Tests for environment variable priority in config resolution."""

  def test_env_overrides_explicit_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that env vars override explicit config parameter."""
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_MODEL", "env-model")

    # Create explicit config
    explicit_config = Config(backend=BackendConfig(ollama=OllamaConfig(model="config-model")))

    # Load env config and merge
    env_overrides = load_env_config()
    merged = merge_configs(explicit_config, env_overrides)

    # Env var should override
    assert merged.backend.ollama.model == "env-model"

  def test_env_overrides_file_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that env vars override file config."""
    # Create config file
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
[backend.ollama]
model = "file-model"
""")

    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_MODEL", "env-model")

    # Load from file
    file_config = load_config(config_file)

    # Merge env vars
    env_overrides = load_env_config()
    merged = merge_configs(file_config, env_overrides)

    # Env var should override
    assert merged.backend.ollama.model == "env-model"

  def test_prefix_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that YOKER_PREFIX determines which env vars to use."""
    # Set both prefixed and unprefixed
    monkeypatch.setenv("YOKER_PREFIX", "MYAPP")
    monkeypatch.setenv("MYAPP_YOKER_HARNESS_NAME", "prefixed")
    monkeypatch.setenv("YOKER_HARNESS_NAME", "unprefixed")

    # Load with prefix
    result = load_env_config()

    # Only prefixed should be used
    assert result == {"harness": {"name": "prefixed"}}


class TestIntegration:
  """Integration tests for env var configuration."""

  def test_full_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test creating full config from environment variables."""
    # Set comprehensive env vars
    monkeypatch.setenv("YOKER_HARNESS_NAME", "env-harness")
    monkeypatch.setenv("YOKER_HARNESS_VERSION", "2.0")
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_MODEL", "llama3")
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_BASE_URL", "http://remote:11434")
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("YOKER_CONTEXT_MANAGER", "compaction")
    monkeypatch.setenv("YOKER_CONTEXT_STORAGE_PATH", "/custom/path")
    monkeypatch.setenv("YOKER_PERMISSIONS_FILESYSTEM_PATHS", "/app,/data")
    monkeypatch.setenv("YOKER_PERMISSIONS_NETWORK_ACCESS", "local")

    env_overrides = load_env_config()
    base_config = Config()
    merged = merge_configs(base_config, env_overrides)

    assert merged.harness.name == "env-harness"
    assert merged.harness.version == "2.0"
    assert merged.backend.ollama.model == "llama3"
    assert merged.backend.ollama.base_url == "http://remote:11434"
    assert merged.backend.ollama.timeout_seconds == 120
    assert merged.context.manager == "compaction"
    assert merged.context.storage_path == "/custom/path"
    assert merged.permissions.filesystem_paths == ("/app", "/data")
    assert merged.permissions.network_access == "local"

  def test_env_with_toml_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that env vars override TOML config values."""
    # Create config file with some values
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
[harness]
name = "toml-harness"

[backend.ollama]
model = "toml-model"
timeout_seconds = 60
""")

    # Set env vars for some values
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_MODEL", "env-model")
    monkeypatch.setenv("YOKER_BACKEND_OLLAMA_TIMEOUT_SECONDS", "120")

    # Load and merge
    file_config = load_config(config_file)
    env_overrides = load_env_config()
    merged = merge_configs(file_config, env_overrides)

    # TOML value should remain
    assert merged.harness.name == "toml-harness"
    # Env var should override
    assert merged.backend.ollama.model == "env-model"
    assert merged.backend.ollama.timeout_seconds == 120
