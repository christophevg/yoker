"""Tests for Yoker configuration system."""

from pathlib import Path

import pytest

from yoker.config import (
  BackendConfig,
  Config,
  ContextConfig,
  HarnessConfig,
  OllamaConfig,
  OllamaParameters,
  PermissionsConfig,
  load_config,
  load_config_with_defaults,
  validate_config,
)
from yoker.exceptions import ConfigurationError, FileNotFoundError, ValidationError


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
    assert config.harness.name == "yoker"
    assert config.backend.provider == "ollama"
    assert config.backend.ollama.model == "llama3.2:latest"
    assert config.context.manager == "basic_persistence"
    assert config.permissions.network_access == "none"
    assert config.permissions.filesystem_paths == (".",)
    assert config.tools.list.enabled is True
    assert config.agents.directory == "./agents"
    assert config.logging.format == "text"
    assert config.logging.level == "INFO"

  def test_frozen_dataclass(self) -> None:
    """Test that config classes are frozen (immutable)."""
    config = HarnessConfig(name="test")
    with pytest.raises(AttributeError):
      config.name = "changed"  # type: ignore


class TestConfigLoader:
  """Tests for configuration loading."""

  def test_load_config_missing_file(self) -> None:
    """Test loading non-existent configuration file."""
    with pytest.raises(FileNotFoundError) as exc_info:
      load_config("/nonexistent/path/config.toml")
    assert "configuration not found" in str(exc_info.value).lower()

  def test_load_config_minimal(self, tmp_path: Path) -> None:
    """Test loading minimal configuration."""
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("")

    config = load_config(config_file)
    assert isinstance(config, Config)
    assert config.harness.name == "yoker"

  def test_load_config_full(self, tmp_path: Path) -> None:
    """Test loading full configuration."""
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("""
[harness]
name = "test-harness"
version = "2.0"
log_level = "DEBUG"

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://custom:11434"
model = "custom-model"
timeout_seconds = 120

[backend.ollama.parameters]
temperature = 0.5
top_p = 0.8
top_k = 50
num_ctx = 8192

[context]
manager = "compaction"
storage_path = "/custom/path"
session_id = "test-session"
persist_after_turn = false

[permissions]
filesystem_paths = ["/app", "/data"]
network_access = "local"
max_file_size_kb = 1000
max_recursion_depth = 5

[tools.list]
enabled = true
max_depth = 10
max_entries = 5000

[logging]
format = "text"
include_tool_calls = false
""")

    config = load_config(config_file)
    assert config.harness.name == "test-harness"
    assert config.harness.version == "2.0"
    assert config.harness.log_level == "DEBUG"
    assert config.backend.provider == "ollama"
    assert config.backend.ollama.base_url == "http://custom:11434"
    assert config.backend.ollama.model == "custom-model"
    assert config.backend.ollama.timeout_seconds == 120
    assert config.backend.ollama.parameters.temperature == 0.5
    assert config.context.manager == "compaction"
    assert config.context.storage_path == "/custom/path"
    assert config.context.session_id == "test-session"
    assert config.context.persist_after_turn is False
    assert config.permissions.filesystem_paths == ("/app", "/data")
    assert config.permissions.network_access == "local"
    assert config.tools.list.max_depth == 10
    assert config.logging.format == "text"

  def test_load_config_invalid_toml(self, tmp_path: Path) -> None:
    """Test loading invalid TOML file."""
    config_file = tmp_path / "yoker.toml"
    config_file.write_text("invalid toml [content")

    with pytest.raises(ConfigurationError) as exc_info:
      load_config(config_file)
    assert "Failed to parse TOML" in str(exc_info.value)

  def test_load_config_with_defaults_missing(self) -> None:
    """Test load_config_with_defaults with missing file."""
    config = load_config_with_defaults("/nonexistent/path/config.toml")
    assert isinstance(config, Config)
    assert config.harness.name == "yoker"

  def test_load_config_with_defaults_none(self) -> None:
    """Test load_config_with_defaults with None path."""
    config = load_config_with_defaults(None)
    assert isinstance(config, Config)
    assert config.harness.name == "yoker"


class TestConfigValidator:
  """Tests for configuration validation."""

  def test_validate_valid_config(self) -> None:
    """Test validating valid configuration."""
    config = Config()
    warnings = validate_config(config)
    assert isinstance(warnings, list)

  def test_validate_invalid_url(self) -> None:
    """Test validation catches invalid URL."""
    config = Config()
    config = Config(backend=BackendConfig(ollama=OllamaConfig(base_url="not-a-valid-url")))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "backend.ollama.base_url" in str(exc_info.value)

  def test_validate_empty_model(self) -> None:
    """Test validation catches empty model."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="")))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "backend.ollama.model" in str(exc_info.value)

  def test_validate_negative_timeout(self) -> None:
    """Test validation catches negative timeout."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(timeout_seconds=-1)))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "timeout_seconds" in str(exc_info.value)

  def test_validate_invalid_log_level(self) -> None:
    """Test validation catches invalid log level."""
    config = Config(harness=HarnessConfig(log_level="INVALID"))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "harness.log_level" in str(exc_info.value)

  def test_validate_invalid_context_manager(self) -> None:
    """Test validation catches invalid context manager."""
    config = Config(context=ContextConfig(manager="invalid"))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "context.manager" in str(exc_info.value)

  def test_validate_invalid_network_access(self) -> None:
    """Test validation catches invalid network access."""
    config = Config(permissions=PermissionsConfig(network_access="invalid"))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "permissions.network_access" in str(exc_info.value)

  def test_validate_empty_filesystem_paths(self) -> None:
    """Test validation catches empty filesystem_paths."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=()))
    with pytest.raises(ValidationError) as exc_info:
      validate_config(config)
    assert "permissions.filesystem_paths" in str(exc_info.value)
    assert "must not be empty" in str(exc_info.value).lower()


class TestExampleConfig:
  """Tests for example configuration file."""

  def test_example_config_loads(self) -> None:
    """Test that example configuration file loads successfully."""
    example_path = Path(__file__).parent.parent / "examples" / "yoker.toml"
    if not example_path.exists():
      pytest.skip("Example config not found")

    config = load_config(example_path)
    assert isinstance(config, Config)
    assert config.harness.name == "my-yoke"
    assert config.backend.provider == "ollama"

  def test_example_config_validates(self) -> None:
    """Test that example configuration validates successfully."""
    example_path = Path(__file__).parent.parent / "examples" / "yoker.toml"
    if not example_path.exists():
      pytest.skip("Example config not found")

    config = load_config(example_path)
    warnings = validate_config(config)
    assert isinstance(warnings, list)
