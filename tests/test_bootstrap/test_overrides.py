"""Tests for :func:`yoker.bootstrap.wizard.build_bootstrap_overrides`.

This is the pure-logic helper that turns the wizard's collected choices
into the dotted-key override dict passed to :func:`write_config`. It is
unit-tested here because it is logic (not wizard IO); the wizard flow
itself is not unit-tested per the owner's PR #34 directive.
"""

from yoker.bootstrap.steps import ConnectionChoice
from yoker.bootstrap.wizard import (
  OLLAMA_CLOUD_BASE_URL,
  build_bootstrap_overrides,
)


class TestBuildBootstrapOverrides:
  """``build_bootstrap_overrides`` maps wizard choices to config overrides."""

  def test_app_path_only_sets_model(self) -> None:
    """The ollama-app path (no key) only overrides the model."""
    overrides = build_bootstrap_overrides("llama3.2", ConnectionChoice(use_api_key=False))
    assert overrides == {"backend.ollama.model": "llama3.2"}

  def test_app_path_does_not_set_base_url(self) -> None:
    """The app path keeps the default localhost base_url (no override)."""
    overrides = build_bootstrap_overrides("llama3.2", ConnectionChoice(use_api_key=False))
    assert "backend.ollama.base_url" not in overrides
    assert "backend.ollama.api_key" not in overrides

  def test_api_key_path_sets_api_key_and_cloud_base_url(self) -> None:
    """The API-key path sets the key AND points base_url at the cloud."""
    overrides = build_bootstrap_overrides(
      "llama3.2",
      ConnectionChoice(use_api_key=True, api_key="ollama-abc123"),
    )
    assert overrides["backend.ollama.model"] == "llama3.2"
    assert overrides["backend.ollama.api_key"] == "ollama-abc123"
    assert overrides["backend.ollama.base_url"] == OLLAMA_CLOUD_BASE_URL

  def test_api_key_path_uses_cloud_endpoint_not_localhost(self) -> None:
    """The cloud base_url is not the localhost default."""
    overrides = build_bootstrap_overrides(
      "llama3.2",
      ConnectionChoice(use_api_key=True, api_key="ollama-abc123"),
    )
    assert overrides["backend.ollama.base_url"] != "http://localhost:11434"
    assert overrides["backend.ollama.base_url"].startswith("https://")

  def test_api_key_path_with_empty_key_falls_back_to_app_path(self) -> None:
    """An empty key is treated like the app path (no key, no cloud url)."""
    overrides = build_bootstrap_overrides(
      "llama3.2",
      ConnectionChoice(use_api_key=True, api_key=None),
    )
    assert overrides == {"backend.ollama.model": "llama3.2"}
    assert "backend.ollama.api_key" not in overrides
    assert "backend.ollama.base_url" not in overrides
