"""Tests for demo script loader."""

from pathlib import Path

import pytest

from yoker.demo import DemoScript, load_demo_script, load_demo_scripts
from yoker.exceptions import ConfigurationError, FileNotFoundError


class TestLoadDemoScript:
  """Tests for load_demo_script."""

  def test_load_valid_script(self, tmp_path: Path) -> None:
    """Load a valid demo script."""
    script_file = tmp_path / "test.md"
    script_file.write_text(
      "---\n"
      "title: Test Demo\n"
      "description: A test demo\n"
      "output: media/test.svg\n"
      "events: media/events-test.jsonl\n"
      "---\n"
      "\n"
      "## Messages\n"
      "\n"
      "- Hello\n"
      "- World\n"
    )
    script = load_demo_script(script_file)
    assert script.title == "Test Demo"
    assert script.description == "A test demo"
    assert script.output == "media/test.svg"
    assert script.events == "media/events-test.jsonl"
    assert script.messages == ("Hello", "World")
    assert script.source_path == str(script_file)

  def test_load_multiline_messages(self, tmp_path: Path) -> None:
    """Load script with multiline messages."""
    script_file = tmp_path / "multiline.md"
    script_file.write_text(
      "---\n"
      "title: Multiline\n"
      "output: out.svg\n"
      "---\n"
      "\n"
      "## Messages\n"
      "\n"
      "- First message\n"
      "  spanning multiple lines\n"
      "- Second message\n"
    )
    script = load_demo_script(script_file)
    assert script.messages == (
      "First message\nspanning multiple lines",
      "Second message",
    )

  def test_load_no_frontmatter(self, tmp_path: Path) -> None:
    """Script without frontmatter is invalid (no title)."""
    script_file = tmp_path / "nofront.md"
    script_file.write_text("## Messages\n\n- Hello\n")
    with pytest.raises(ConfigurationError) as exc_info:
      load_demo_script(script_file)
    assert "title" in str(exc_info.value)

  def test_load_no_messages_section(self, tmp_path: Path) -> None:
    """Script without Messages section raises error."""
    script_file = tmp_path / "nomsg.md"
    script_file.write_text("---\ntitle: No Messages\n---\n\n## Other\n\nSome content\n")
    with pytest.raises(ConfigurationError) as exc_info:
      load_demo_script(script_file)
    assert "messages" in str(exc_info.value)

  def test_load_empty_messages(self, tmp_path: Path) -> None:
    """Script with empty Messages section raises error."""
    script_file = tmp_path / "emptymsg.md"
    script_file.write_text("---\ntitle: Empty Messages\n---\n\n## Messages\n")
    with pytest.raises(ConfigurationError) as exc_info:
      load_demo_script(script_file)
    assert "messages" in str(exc_info.value)

  def test_load_missing_file(self, tmp_path: Path) -> None:
    """Loading nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
      load_demo_script(tmp_path / "nonexistent.md")

  def test_load_asterisk_bullets(self, tmp_path: Path) -> None:
    """Support asterisk bullet lists."""
    script_file = tmp_path / "asterisk.md"
    script_file.write_text(
      "---\ntitle: Asterisk\noutput: out.svg\n---\n\n## Messages\n\n* Hello\n* World\n"
    )
    script = load_demo_script(script_file)
    assert script.messages == ("Hello", "World")

  def test_load_defaults(self, tmp_path: Path) -> None:
    """Optional fields default to empty strings."""
    script_file = tmp_path / "defaults.md"
    script_file.write_text("---\ntitle: Defaults\n---\n\n## Messages\n\n- Hello\n")
    script = load_demo_script(script_file)
    assert script.description == ""
    assert script.output == ""
    assert script.events == ""


class TestLoadDemoScripts:
  """Tests for load_demo_scripts."""

  def test_load_directory(self, tmp_path: Path) -> None:
    """Load all scripts from directory."""
    (tmp_path / "a.md").write_text("---\ntitle: Alpha\n---\n\n## Messages\n\n- Hello\n")
    (tmp_path / "b.md").write_text("---\ntitle: Beta\n---\n\n## Messages\n\n- World\n")
    scripts = load_demo_scripts(tmp_path)
    assert len(scripts) == 2
    assert "Alpha" in scripts
    assert "Beta" in scripts

  def test_load_empty_directory(self, tmp_path: Path) -> None:
    """Empty directory returns empty dict."""
    scripts = load_demo_scripts(tmp_path)
    assert scripts == {}

  def test_load_duplicate_titles(self, tmp_path: Path) -> None:
    """Duplicate titles raise ConfigurationError."""
    (tmp_path / "a.md").write_text("---\ntitle: Same\n---\n\n## Messages\n\n- Hello\n")
    (tmp_path / "b.md").write_text("---\ntitle: Same\n---\n\n## Messages\n\n- World\n")
    with pytest.raises(ConfigurationError) as exc_info:
      load_demo_scripts(tmp_path)
    assert "Duplicate" in str(exc_info.value)

  def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
    """Nonexistent directory raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
      load_demo_scripts(tmp_path / "nonexistent")


class TestDemoScriptDataclass:
  """Tests for DemoScript dataclass."""

  def test_frozen(self) -> None:
    """DemoScript is frozen (immutable)."""
    script = DemoScript(
      title="Test",
      description="Desc",
      output="out.svg",
      events="events.jsonl",
      messages=("Hello",),
      source_path="test.md",
    )
    with pytest.raises(AttributeError):
      script.title = "Changed"
