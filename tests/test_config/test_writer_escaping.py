"""Tests for TOML string escaping in config writer.

This test suite verifies that the writer properly escapes special characters
in string values according to TOML specification.
"""

import tomllib

from yoker.config import Config
from yoker.config.writer import render_config_toml


class TestTomlStringEscaping:
  """Test TOML string escaping for special characters."""

  def test_escape_newline(self) -> None:
    """Newlines in strings should be escaped as \\n."""
    config = Config()
    overrides = {"backend.ollama.model": "model\nwith\nnewlines"}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    # TOML parser should interpret \n as newline
    assert parsed["backend"]["ollama"]["model"] == "model\nwith\nnewlines"

  def test_escape_tab(self) -> None:
    """Tabs in strings should be escaped as \\t."""
    config = Config()
    overrides = {"backend.ollama.model": "model\twith\ttabs"}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == "model\twith\ttabs"

  def test_escape_carriage_return(self) -> None:
    """Carriage returns in strings should be escaped as \\r."""
    config = Config()
    overrides = {"backend.ollama.model": "model\rwith\rcarriage"}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == "model\rwith\rcarriage"

  def test_escape_backslash(self) -> None:
    """Backslashes in strings should be escaped as \\\\."""
    config = Config()
    overrides = {"backend.ollama.model": r"model\with\backslashes"}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == r"model\with\backslashes"

  def test_escape_quotes(self) -> None:
    """Double quotes in strings should be escaped as \\"."""
    config = Config()
    overrides = {"backend.ollama.model": 'model"with"quotes'}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == 'model"with"quotes'

  def test_escape_control_characters(self) -> None:
    """Control characters should be escaped as \\uXXXX."""
    config = Config()
    # Test with null byte (0x00) and bell character (0x07)
    overrides = {"backend.ollama.model": "model\x00with\x07control"}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == "model\x00with\x07control"

  def test_escape_mixed_special_characters(self) -> None:
    """Strings with multiple special characters should be escaped correctly."""
    config = Config()
    overrides = {"backend.ollama.model": 'line1\nline2\t"quoted"\r\npath\\to\\file'}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == 'line1\nline2\t"quoted"\r\npath\\to\\file'

  def test_normal_string_not_affected(self) -> None:
    """Strings without special characters should not be modified."""
    config = Config()
    overrides = {"backend.ollama.model": "qwen3.5:cloud"}
    toml_text = render_config_toml(config, overrides=overrides)
    parsed = tomllib.loads(toml_text)
    assert parsed["backend"]["ollama"]["model"] == "qwen3.5:cloud"
