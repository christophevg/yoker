"""Tests for Clevis CLI generation with multi-provider backend config."""

import pytest


class TestCliGeneration:
  """Tests for Clevis CLI argument generation."""

  def test_backend_provider_cli_arg_exists(self) -> None:
    """CLI includes --backend-provider choice argument.

    This test verifies the field exists in the Config structure.
    Actual CLI generation is tested via integration tests or manual verification.
    """
    from yoker.config import BackendConfig, Config, OpenAIConfig

    # Verify the provider field exists and has the right type
    config = Config()
    assert hasattr(config.backend, "provider")
    assert config.backend.provider == "ollama"

    # Verify we can set it to other values (with required config)
    backend = BackendConfig(provider="openai", openai=OpenAIConfig(api_key="test"))
    assert backend.provider == "openai"

  def test_api_key_cli_args_absent(self) -> None:
    """No --backend-*-api-key CLI arguments are generated.

    Per Q6 amendment and H1 resolved, api_key fields are annotated with
    metadata={'cli': False} to exclude them from CLI generation.
    """
    import dataclasses

    from yoker.config import AnthropicConfig, OllamaConfig, OpenAIConfig

    # Check OllamaConfig
    ollama_fields = dataclasses.fields(OllamaConfig)
    ollama_api_key = next(f for f in ollama_fields if f.name == "api_key")
    assert ollama_api_key.metadata.get("cli") is False, "OllamaConfig.api_key should have cli=False"

    # Check OpenAIConfig
    openai_fields = dataclasses.fields(OpenAIConfig)
    openai_api_key = next(f for f in openai_fields if f.name == "api_key")
    assert openai_api_key.metadata.get("cli") is False, "OpenAIConfig.api_key should have cli=False"

    # Check AnthropicConfig
    anthropic_fields = dataclasses.fields(AnthropicConfig)
    anthropic_api_key = next(f for f in anthropic_fields if f.name == "api_key")
    assert anthropic_api_key.metadata.get("cli") is False, (
      "AnthropicConfig.api_key should have cli=False"
    )

  def test_compaction_cli_args_absent_metadata(self) -> None:
    """The compaction field is marked cli=False (TOML-only nested config)."""
    import dataclasses

    from yoker.config import ContextConfig

    field = next(f for f in dataclasses.fields(ContextConfig) if f.name == "compaction")
    assert field.metadata.get("cli") is False, "ContextConfig.compaction should have cli=False"

  def test_compaction_cli_args_absent_parse(self, monkeypatch, tmp_path) -> None:
    """No --context-compaction-* CLI flags are accepted by the chat parser.

    Behavioral proof mirroring test_chat_flags.py: driving the real Clevis
    parse through ``load_subcommand_config`` — a would-be generated flag
    must be rejected with SystemExit (argparse: unrecognized argument).
    """
    import sys
    from importlib import reload

    from clevis import _reset_factories

    import yoker.cli.commands
    from yoker.cli.shared import load_subcommand_config

    _reset_factories()
    reload(yoker.cli.commands)
    monkeypatch.setenv("YOKER_DEV_MODE", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    try:
      monkeypatch.setattr(
        sys,
        "argv",
        ["yoker", "chat", "--context-compaction-strategies", "cutoff"],
        raising=False,
      )
      with pytest.raises(SystemExit):
        load_subcommand_config(yoker.cli.commands.ChatConfig)
    finally:
      _reset_factories()
      reload(yoker.cli.commands)

  def test_backend_provider_choices(self) -> None:
    """BackendConfig provider field accepts all three providers."""
    from yoker.config import AnthropicConfig, BackendConfig, OllamaConfig, OpenAIConfig

    # Test each provider
    ollama_backend = BackendConfig(provider="ollama", ollama=OllamaConfig())
    assert ollama_backend.provider == "ollama"

    openai_backend = BackendConfig(provider="openai", openai=OpenAIConfig(), ollama=None)
    assert openai_backend.provider == "openai"

    anthropic_backend = BackendConfig(
      provider="anthropic", anthropic=AnthropicConfig(), ollama=None
    )
    assert anthropic_backend.provider == "anthropic"

  def test_backend_config_defaults_for_all_providers(self) -> None:
    """BackendConfig() defaults work for all providers."""
    from yoker.config import BackendConfig

    # Default backend is Ollama
    backend = BackendConfig()
    assert backend.provider == "ollama"
    assert backend.ollama is not None
    assert backend.openai is None
    assert backend.anthropic is None

    # openai and anthropic default to None
    backend_with_openai = BackendConfig(
      provider="ollama", ollama=BackendConfig().ollama, openai=None
    )
    assert backend_with_openai.openai is None

    backend_with_anthropic = BackendConfig(
      provider="ollama", ollama=BackendConfig().ollama, anthropic=None
    )
    assert backend_with_anthropic.anthropic is None
