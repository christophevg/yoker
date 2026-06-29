"""Tests for Config TOML writer."""

import tempfile
from pathlib import Path

from clevis import get_config

from yoker.config import (
  AgentsConfig,
  BackendConfig,
  Config,
  OllamaConfig,
  OpenAIConfig,
  PermissionsConfig,
  PluginsConfig,
)
from yoker.config.writer import render_config_toml


class TestRenderConfigToml:
  """Tests for render_config_toml function."""

  def test_render_ollama_only_config(self) -> None:
    """Test rendering an Ollama-only BackendConfig."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(
        base_url="http://localhost:11434",
        model="llama3.2:latest",
        timeout_seconds=60,
      ),
      openai=None,
      anthropic=None,
    )

    toml_str = render_config_toml(Config(backend=backend))

    # Should contain backend.provider
    assert 'provider = "ollama"' in toml_str

    # Should contain [backend.ollama] section
    assert "[backend.ollama]" in toml_str
    assert 'base_url = "http://localhost:11434"' in toml_str
    assert 'model = "llama3.2:latest"' in toml_str

    # Should NOT contain openai or anthropic sections (None sub-configs)
    assert "[backend.openai]" not in toml_str
    assert "[backend.anthropic]" not in toml_str

  def test_render_config_omits_none_sub_configs(self) -> None:
    """Test that None sub-configs are omitted from TOML output."""
    config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(),
        openai=None,  # Explicitly None
        anthropic=None,  # Explicitly None
      )
    )

    toml_str = render_config_toml(config)

    # Should not contain any references to openai or anthropic
    assert "openai" not in toml_str.lower()
    assert "anthropic" not in toml_str.lower()

  def test_render_config_with_openai(self) -> None:
    """Test rendering a config with OpenAI sub-config set."""
    backend = BackendConfig(
      provider="openai",
      ollama=OllamaConfig(),
      openai=OpenAIConfig(
        api_key="sk-test",
        model="gpt-4o-mini",
      ),
      anthropic=None,
    )

    toml_str = render_config_toml(Config(backend=backend))

    # Should contain provider
    assert 'provider = "openai"' in toml_str

    # Should contain [backend.openai] section
    assert "[backend.openai]" in toml_str
    assert 'model = "gpt-4o-mini"' in toml_str

    # Should NOT contain anthropic section
    assert "[backend.anthropic]" not in toml_str

  def test_roundtrip_ollama_config(self) -> None:
    """Test that writing and reading config produces equivalent config."""
    original_config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          base_url="http://localhost:11434",
          model="llama3.2:latest",
          timeout_seconds=60,
        ),
        openai=None,
        anthropic=None,
      )
    )

    # Write config to TOML
    toml_str = render_config_toml(original_config)

    # Write to temporary file
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
      # Secure directory permissions for Clevis security check
      # (TemporaryDirectory creates world-writable dirs on Windows)
      os.chmod(tmpdir, 0o700)

      config_path = Path(tmpdir) / "test.toml"
      config_path.write_text(toml_str)

      # Set secure file permissions (owner-only readable)
      os.chmod(config_path, 0o600)

      original_dir = os.getcwd()
      try:
        os.chdir(tmpdir)
        loaded_config = get_config(Config, name="test", user=False, cli=False)

        # Verify backend config is equivalent
        assert loaded_config.backend.provider == original_config.backend.provider
        assert loaded_config.backend.ollama.model == original_config.backend.ollama.model
        assert loaded_config.backend.ollama.base_url == original_config.backend.ollama.base_url
        assert (
          loaded_config.backend.ollama.timeout_seconds
          == original_config.backend.ollama.timeout_seconds
        )

        # Verify None sub-configs remain None
        assert loaded_config.backend.openai is None
        assert loaded_config.backend.anthropic is None
      finally:
        os.chdir(original_dir)

  def test_render_full_config(self) -> None:
    """Test rendering a full Config with all sections."""
    config = Config()

    toml_str = render_config_toml(config)

    # Should contain all major sections
    assert "[harness]" in toml_str
    assert "[backend]" in toml_str
    assert "[backend.ollama]" in toml_str
    assert "[context]" in toml_str
    assert "[permissions]" in toml_str
    assert "[tools]" in toml_str
    assert "[logging]" in toml_str
    assert "[ui]" in toml_str

  def test_render_config_with_tuple_fields(self) -> None:
    """Test that tuple/list fields are rendered correctly."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(".", "/tmp"),
        network_access="none",
      )
    )

    toml_str = render_config_toml(config)

    # Should contain filesystem_paths as array
    assert 'filesystem_paths = [".", "/tmp"]' in toml_str

  def test_render_config_with_dict_fields(self) -> None:
    """Test that dict fields are rendered correctly."""
    config = Config(
      plugins=PluginsConfig(
        enabled=True,
        packages=("pkg1", "pkg2"),
        trusted={"pkg1": True, "pkg2": False},
      )
    )

    toml_str = render_config_toml(config)

    # Should contain trusted dict as section
    assert "[plugins.trusted]" in toml_str

  def test_render_config_with_empty_collections(self) -> None:
    """Test that empty collections are omitted."""
    config = Config(
      agents=AgentsConfig(
        directories=(),
        definition="",
      )
    )

    toml_str = render_config_toml(config)

    # Empty tuple should be omitted from output
    assert "directories" not in toml_str
