"""Tests for the annotation-driven Config writer (MBI-002 task 2.5).

These are logic tests for :mod:`yoker.config.writer`: TOML rendering,
annotation-driven inline comments, overrides, the generic "new field picked up
automatically" property, and ``chmod 600`` on write.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import tomllib

from yoker.config import Config, OllamaConfig
from yoker.config.writer import render_config_toml, write_config

# chmod 600 permission checks rely on POSIX permission bits that are not
# enforceable on Windows NTFS (the Windows stat mode masks everything to
# 0o666 for regular files). Skip the permission-mode assertions there.
_IS_WINDOWS = os.name == "nt"


class TestRenderBasics:
  """Basic rendering behavior."""

  def test_render_produces_valid_toml(self) -> None:
    """The rendered string parses as TOML."""
    toml_text = render_config_toml(Config())
    parsed = tomllib.loads(toml_text)
    # A few sanity checks on the parsed structure.
    assert parsed["backend"]["provider"] == "ollama"
    assert parsed["backend"]["ollama"]["base_url"] == "http://localhost:11434"
    assert parsed["backend"]["ollama"]["model"] == "qwen3.5:cloud"

  def test_render_ends_with_newline(self) -> None:
    assert render_config_toml(Config()).endswith("\n")

  def test_render_omits_none_defaults(self) -> None:
    """Fields whose default is None (e.g. api_key) are omitted by default."""
    toml_text = render_config_toml(Config())
    parsed = tomllib.loads(toml_text)
    assert "api_key" not in parsed["backend"]["ollama"]

  def test_render_inserts_blank_line_between_sections(self) -> None:
    """A blank line separates each table header from the previous section.

    Per MBI-002 PR #34 feedback, rendered TOML has an empty line between
    sections/tables. The first table header has no leading blank line; every
    subsequent header is preceded by a blank line.
    """
    toml_text = render_config_toml(Config())
    lines = toml_text.splitlines()
    header_idx = [i for i, line in enumerate(lines) if line.startswith("[")]
    # There is more than one section in the default config.
    assert len(header_idx) > 1
    # The first header has no blank line before it (it is at the top).
    assert header_idx[0] == 0 or not all(bl == "" for bl in lines[: header_idx[0]])
    # Every subsequent header is preceded by a blank line.
    for i in header_idx[1:]:
      assert lines[i - 1] == "", f"expected blank line before header at line {i}"

  def test_render_first_header_has_no_leading_blank(self) -> None:
    """The very first table header is at the top of the document (no leading blank)."""
    toml_text = render_config_toml(Config())
    assert toml_text.startswith("[")


class TestAnnotationDrivenComments:
  """Inline comments come from field metadata, not writer hardcoding."""

  def test_help_comment_appears_for_model(self) -> None:
    toml_text = render_config_toml(Config())
    # The help annotation on OllamaConfig.model must surface as an inline comment.
    model_line = next(line for line in toml_text.splitlines() if line.startswith("model ="))
    assert "# Default model to use" in model_line

  def test_help_comment_appears_for_base_url(self) -> None:
    toml_text = render_config_toml(Config())
    base_url_line = next(line for line in toml_text.splitlines() if line.startswith("base_url ="))
    assert "# URL of the Ollama API server" in base_url_line

  def test_fields_without_help_have_no_comment(self) -> None:
    """A field without a ``help`` annotation renders with no inline comment."""
    toml_text = render_config_toml(Config())
    # timeout_seconds has a help annotation in our config; pick a field without
    # one to verify the negative case: OllamaParameters.temperature has help,
    # so use a field known to lack it. The `version` field on HarnessConfig
    # has no help annotation.
    version_line = next(line for line in toml_text.splitlines() if line.startswith("version ="))
    assert "#" not in version_line


class TestOverrides:
  """Override behavior."""

  def test_override_replaces_default_value(self) -> None:
    toml_text = render_config_toml(Config(), overrides={"backend.ollama.model": "llama3.2:latest"})
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == "llama3.2:latest"

  def test_override_can_add_api_key(self) -> None:
    toml_text = render_config_toml(Config(), overrides={"backend.ollama.api_key": "secret-key"})
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["api_key"] == "secret-key"

  def test_override_does_not_mutate_input_config(self) -> None:
    config = Config()
    original_model = config.backend.ollama.model
    render_config_toml(config, overrides={"backend.ollama.model": "other"})
    assert config.backend.ollama.model == original_model


class TestGenericProperty:
  """The writer picks up newly annotated fields with no writer change."""

  def test_new_annotated_field_is_rendered_automatically(self) -> None:
    """A dataclass with a freshly-annotated field renders it via introspection."""

    @dataclass(frozen=True)
    class _Nested:
      value: int = field(default=7, metadata={"help": "a nested value"})

    @dataclass(frozen=True)
    class _Sample:
      name: str = field(default="demo", metadata={"help": "the name"})
      nested: _Nested = field(default_factory=_Nested)

    toml_text = render_config_toml(_Sample())  # type: ignore[arg-type]
    parsed = tomllib.loads(toml_text)
    assert parsed["name"] == "demo"
    assert parsed["nested"]["value"] == 7
    # The help comment from the new field is surfaced without writer changes.
    name_line = next(line for line in toml_text.splitlines() if line.startswith("name ="))
    assert "# the name" in name_line
    value_line = next(line for line in toml_text.splitlines() if line.startswith("value ="))
    assert "# a nested value" in value_line


class TestWriteConfig:
  """File-writing behavior and permissions."""

  def test_write_creates_file_with_content(self, tmp_path: Path) -> None:
    dest = tmp_path / "yoker.toml"
    write_config(Config(), dest)
    assert dest.exists()
    parsed = tomllib.loads(dest.read_text(encoding="utf-8"))
    assert parsed["backend"]["ollama"]["model"] == "qwen3.5:cloud"

  def test_write_applies_chmod_600(self, tmp_path: Path) -> None:
    dest = tmp_path / "yoker.toml"
    write_config(Config(), dest)
    # File is written on all platforms.
    assert dest.exists()
    if _IS_WINDOWS:
      pytest.skip("chmod 600 not enforceable on Windows NTFS")
    mode = dest.stat().st_mode & 0o777
    assert mode == 0o600

  def test_write_tightens_permissions_on_existing_file(self, tmp_path: Path) -> None:
    """A pre-existing world-readable file is tightened to 0o600 after write."""
    dest = tmp_path / "yoker.toml"
    dest.write_text("loose = true", encoding="utf-8")
    os.chmod(dest, 0o644)
    write_config(Config(), dest)
    # File is overwritten on all platforms.
    assert tomllib.loads(dest.read_text(encoding="utf-8"))["backend"]["provider"] == "ollama"
    if _IS_WINDOWS:
      pytest.skip("chmod 600 not enforceable on Windows NTFS")
    mode = dest.stat().st_mode & 0o777
    assert mode == 0o600

  def test_write_with_overrides(self, tmp_path: Path) -> None:
    dest = tmp_path / "yoker.toml"
    write_config(
      Config(),
      dest,
      overrides={"backend.ollama.api_key": "super-secret"},
    )
    parsed = tomllib.loads(dest.read_text(encoding="utf-8"))
    assert parsed["backend"]["ollama"]["api_key"] == "super-secret"
    # Permissions still tightened when an API key is present (POSIX only).
    if _IS_WINDOWS:
      pytest.skip("chmod 600 not enforceable on Windows NTFS")
    assert (dest.stat().st_mode & 0o777) == 0o600


class TestRoundTrip:
  """Rendering default Config round-trips through tomllib cleanly."""

  def test_default_config_round_trips(self) -> None:
    toml_text = render_config_toml(Config())
    parsed = tomllib.loads(toml_text)
    # Re-construct a Config from the parsed dict via keyword wiring for the
    # fields we overrode/kept; just assert the key wizard fields survived.
    assert parsed["backend"]["ollama"]["model"] == OllamaConfig().model
    assert parsed["ui"]["mode"] == "interactive"
    assert parsed["plugins"]["enabled"] is False
