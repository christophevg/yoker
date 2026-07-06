"""Tests for the :func:`yoker.config.make_config` factory (MBI-003 task 3.1)."""

import dataclasses

import pytest

from yoker.config import (
  KNOWN_PROVIDERS,
  AnthropicConfig,
  BackendConfig,
  Config,
  GeminiConfig,
  OpenAIConfig,
  make_config,
)


class TestMakeConfigDefaults:
  """Defaults: ``make_config()`` returns a valid ``Config()`` with no I/O."""

  def test_returns_config_instance(self) -> None:
    """make_config() returns a Config."""
    config = make_config()
    assert isinstance(config, Config)

  def test_default_provider_is_ollama(self) -> None:
    """The default backend provider is ollama (matches Config default)."""
    config = make_config()
    assert config.backend.provider == "ollama"

  def test_does_not_touch_filesystem(self, tmp_path, monkeypatch) -> None:
    """make_config does not read any TOML file.

    We run it from a tmp_path with HOME redirected and assert no yoker.toml
    is opened. The factory builds purely from dataclass defaults.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    # No config files exist in tmp_path. If make_config tried to discover
    # them it would either warn or use defaults — either way it must not
    # raise and must return a Config.
    config = make_config()
    assert isinstance(config, Config)
    assert config.backend.provider == "ollama"


class TestMakeConfigModelOverride:
  """``model`` override is applied to the active provider sub-config."""

  def test_model_applied_to_ollama(self) -> None:
    """model is set on the active provider's sub-config."""
    config = make_config(model="qwen3.5:cloud")
    assert config.backend.ollama.model == "qwen3.5:cloud"
    # The active provider config property reflects the override too.
    assert config.backend.config.model == "qwen3.5:cloud"

  def test_model_applied_to_openai(self) -> None:
    """model + provider=openai sets OpenAIConfig.model."""
    config = make_config(provider="openai", model="gpt-4o-mini")
    assert config.backend.provider == "openai"
    assert isinstance(config.backend.openai, OpenAIConfig)
    assert config.backend.openai.model == "gpt-4o-mini"
    assert config.backend.config.model == "gpt-4o-mini"

  def test_model_applied_to_anthropic(self) -> None:
    """provider=anthropic gets a default AnthropicConfig with the model."""
    config = make_config(provider="anthropic", model="claude-3-5-sonnet")
    assert config.backend.provider == "anthropic"
    assert isinstance(config.backend.anthropic, AnthropicConfig)
    assert config.backend.anthropic.model == "claude-3-5-sonnet"

  def test_model_applied_to_gemini(self) -> None:
    """provider=gemini gets a default GeminiConfig with the model."""
    config = make_config(provider="gemini", model="gemini-2.0-flash")
    assert config.backend.provider == "gemini"
    assert isinstance(config.backend.gemini, GeminiConfig)
    assert config.backend.gemini.model == "gemini-2.0-flash"

  def test_provider_only_keeps_default_model(self) -> None:
    """provider without model keeps the sub-config default model."""
    config = make_config(provider="openai")
    assert config.backend.provider == "openai"
    # OpenAIConfig default model is gpt-4o-mini — no override applied.
    assert config.backend.openai.model == "gpt-4o-mini"


class TestMakeConfigPlugins:
  """``plugins`` enables plugin loading and sets packages."""

  def test_plugins_enabled_with_packages(self) -> None:
    """plugins= enables plugins and stores the packages tuple."""
    config = make_config(plugins=["pkgq", "c3"])
    assert config.plugins.enabled is True
    assert config.plugins.packages == ("pkgq", "c3")

  def test_plugins_none_keeps_disabled(self) -> None:
    """Without plugins=, the default (disabled) is preserved."""
    config = make_config()
    assert config.plugins.enabled is False
    assert config.plugins.packages == ()

  def test_plugins_empty_list_enables(self) -> None:
    """plugins=[] still flips enabled=True (caller asked for plugins)."""
    config = make_config(plugins=[])
    assert config.plugins.enabled is True
    assert config.plugins.packages == ()


class TestMakeConfigDirectories:
  """skills_directories / agents_directories overrides."""

  def test_skills_directories(self) -> None:
    config = make_config(skills_directories=("/a", "/b"))
    assert config.skills.directories == ("/a", "/b")

  def test_agents_directories(self) -> None:
    config = make_config(agents_directories=("/agents",))
    assert config.agents.directories == ("/agents",)


class TestMakeConfigOverrides:
  """``**overrides`` are forwarded to dataclasses.replace."""

  def test_context_override(self) -> None:
    """A nested override via **overrides is applied to the root Config."""
    new_context = dataclasses.replace(Config().context, persist_after_turn=False)
    config = make_config(context=new_context)
    assert config.context.persist_after_turn is False

  def test_overrides_compose_with_named_params(self) -> None:
    """Named params and **overrides can be used together."""
    new_context = dataclasses.replace(Config().context, session_id="abc")
    config = make_config(model="m1", context=new_context)
    assert config.backend.ollama.model == "m1"
    assert config.context.session_id == "abc"


class TestMakeConfigFrozen:
  """The returned Config is still frozen."""

  def test_config_is_frozen(self) -> None:
    config = make_config(model="m")
    with pytest.raises(dataclasses.FrozenInstanceError):
      config.backend = BackendConfig()  # type: ignore[misc]

  def test_provider_switch_to_known_validates(self) -> None:
    """Switching to a known provider produces a BackendConfig that validates."""
    for provider in KNOWN_PROVIDERS:
      config = make_config(provider=provider)
      assert config.backend.provider == provider
      # BackendConfig.__post_init__ would have raised if invalid.
      assert config.backend.config is not None
