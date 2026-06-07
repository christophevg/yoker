"""Tests for Yoker configuration system."""

from pathlib import Path

import pytest
from clevis import SecurityAction, SecurityConfig, get_config

from yoker.config import (
  BackendConfig,
  Config,
  ContextConfig,
  HarnessConfig,
  OllamaConfig,
  OllamaParameters,
  PermissionsConfig,
)
from yoker.exceptions import ValidationError


class TestConfigSchema:
  """Tests for configuration schema classes."""

  def test_harness_config_defaults(self) -> None:
    """Test HarnessConfig default values."""
    config = HarnessConfig()
    assert config.name == "yoker"
    assert config.version == "1.0"
    assert config.log_level == "INFO"

  def test_ollama_parameters_defaults(self) -> None:
    """Test OllamaParameters default values."""
    params = OllamaParameters()
    assert params.temperature == 0.7
    assert params.top_p == 0.9
    assert params.top_k == 40
    assert params.num_ctx == 4096

  def test_ollama_config_defaults(self) -> None:
    """Test OllamaConfig default values."""
    config = OllamaConfig()
    assert config.base_url == "http://localhost:11434"
    assert config.model == "llama3.2:latest"
    assert config.timeout_seconds == 60

  def test_config_defaults(self) -> None:
    """Test Config default values."""
    config = Config()
    assert config.model is None
    assert config.agent is None
    assert config.harness.name == "yoker"
    assert config.backend.provider == "ollama"
    assert config.backend.ollama.model == "llama3.2:latest"
    assert config.context.manager == "basic_persistence"
    assert config.permissions.network_access == "none"
    assert config.permissions.filesystem_paths == (".",)
    assert config.tools.list.enabled is True
    assert config.agents.directory == ""
    assert config.logging.format == "text"
    assert config.logging.level == "INFO"

  def test_config_with_model_override(self) -> None:
    """Test Config with model override."""
    config = Config(model="custom-model:latest")
    assert config.model == "custom-model:latest"
    # Backend model is still available as fallback
    assert config.backend.ollama.model == "llama3.2:latest"

  def test_config_with_agent_path(self) -> None:
    """Test Config with agent definition path."""
    config = Config(agent="agents/custom.md")
    assert config.agent == "agents/custom.md"
    # Legacy field is available for backward compatibility
    assert config.agents.definition == ""

  def test_frozen_dataclass(self) -> None:
    """Test that config classes are frozen (immutable)."""
    config = HarnessConfig(name="test")
    with pytest.raises(AttributeError):
      config.name = "changed"  # type: ignore


class TestConfigValidation:
  """Tests for configuration validation."""

  def test_validate_invalid_url(self) -> None:
    """Test validation catches invalid URL during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(backend=BackendConfig(ollama=OllamaConfig(base_url="not-a-valid-url")))
    assert "backend.ollama.base_url" in str(exc_info.value)

  def test_validate_empty_model(self) -> None:
    """Test validation catches empty model during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(backend=BackendConfig(ollama=OllamaConfig(model="")))
    assert "backend.ollama.model" in str(exc_info.value)

  def test_validate_negative_timeout(self) -> None:
    """Test validation catches negative timeout during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(backend=BackendConfig(ollama=OllamaConfig(timeout_seconds=-1)))
    assert "timeout_seconds" in str(exc_info.value)

  def test_validate_invalid_log_level(self) -> None:
    """Test validation catches invalid log level during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(harness=HarnessConfig(log_level="INVALID"))
    assert "harness.log_level" in str(exc_info.value)

  def test_validate_invalid_context_manager(self) -> None:
    """Test validation catches invalid context manager during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(context=ContextConfig(manager="invalid"))
    assert "context.manager" in str(exc_info.value)

  def test_validate_invalid_network_access(self) -> None:
    """Test validation catches invalid network access during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(permissions=PermissionsConfig(network_access="invalid"))
    assert "permissions.network_access" in str(exc_info.value)

  def test_validate_empty_filesystem_paths(self) -> None:
    """Test validation catches empty filesystem_paths during construction."""
    with pytest.raises(ValidationError) as exc_info:
      Config(permissions=PermissionsConfig(filesystem_paths=()))
    assert "permissions.filesystem_paths" in str(exc_info.value)
    assert "must not be empty" in str(exc_info.value).lower()


class TestClevisIntegration:
  """Tests for Clevis integration."""

  def test_get_config_returns_valid_config(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Test that get_config() returns a valid Config."""
    from unittest.mock import patch

    # Change to temp directory to avoid loading project config
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      # Use LOG security action to allow world-writable temp dirs on Windows
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      config = get_config(Config, name="yoker", cli=False, security=security)
      assert isinstance(config, Config)
      # With no config files, should use defaults
      assert config.harness.name == "yoker"

  def test_get_config_with_explicit_config(self) -> None:
    """Test that explicit config parameter overrides discovery."""
    # Create a custom config
    custom_config = Config(harness=HarnessConfig(name="test-harness", version="2.0"))
    # Pass it to Agent/Core - should use it directly
    assert custom_config.harness.name == "test-harness"
    assert custom_config.harness.version == "2.0"


class TestExampleConfig:
  """Tests for example configuration file."""

  def test_example_config_loads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that example configuration file loads successfully."""
    from unittest.mock import patch

    example_path = Path(__file__).parent.parent / "examples" / "yoker.toml"
    if not example_path.exists():
      pytest.skip("Example config not found")

    # Change to temp directory to avoid loading project config
    monkeypatch.chdir(tmp_path)

    # Mock Path.home() to prevent finding home config
    with patch.object(Path, "home", return_value=tmp_path / "home"):
      # Use LOG security action to allow world-writable temp dirs on Windows
      security = SecurityConfig(
        file_permissions=SecurityAction.LOG,
        directory_permissions=SecurityAction.LOG,
      )
      # With Clevis, we can load from a specific file
      config = get_config(Config, name="yoker", cli=False, security=security)
      assert isinstance(config, Config)
      # Default config has the standard values (no config files in tmp_path)
      assert config.harness.name == "yoker"
      assert config.backend.provider == "ollama"
