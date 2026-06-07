"""Tests for skills configuration parsing."""

from pathlib import Path

from yoker.config.loader import load_config


class TestParseSkills:
  """Test _parse_skills function."""

  def test_parse_skills_with_all_fields(self, tmp_path: Path) -> None:
    """Test parsing skills configuration with all fields."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"

[skills]
directories = ["./skills", "~/.yoker/skills"]
discovery = false
""")

    config = load_config(config_file)

    assert config.skills.directories == ("./skills", "~/.yoker/skills")
    assert config.skills.discovery is False

  def test_parse_skills_with_directories_only(self, tmp_path: Path) -> None:
    """Test parsing skills configuration with directories only."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"

[skills]
directories = ["./custom-skills"]
""")

    config = load_config(config_file)

    assert config.skills.directories == ("./custom-skills",)
    assert config.skills.discovery is True  # default

  def test_parse_skills_with_discovery_only(self, tmp_path: Path) -> None:
    """Test parsing skills configuration with discovery only."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"

[skills]
discovery = false
""")

    config = load_config(config_file)

    assert config.skills.directories == ()  # default
    assert config.skills.discovery is False

  def test_parse_skills_missing_section(self, tmp_path: Path) -> None:
    """Test parsing config without [skills] section."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"
""")

    config = load_config(config_file)

    # Should use defaults from SkillsConfig
    assert config.skills.directories == ()
    assert config.skills.discovery is True

  def test_parse_skills_empty_directories(self, tmp_path: Path) -> None:
    """Test parsing skills with empty directories list."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"

[skills]
directories = []
""")

    config = load_config(config_file)

    assert config.skills.directories == ()

  def test_parse_skills_non_list_directories(self, tmp_path: Path) -> None:
    """Test parsing skills with non-list directories (should use default)."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"

[skills]
directories = "not-a-list"
""")

    config = load_config(config_file)

    # Non-list should fallback to empty tuple
    assert config.skills.directories == ()

  def test_parse_skills_single_directory(self, tmp_path: Path) -> None:
    """Test parsing skills with single directory."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test"
version = "1.0"

[skills]
directories = ["./skills"]
""")

    config = load_config(config_file)

    assert config.skills.directories == ("./skills",)

  def test_config_integration_with_skills(self, tmp_path: Path) -> None:
    """Test that skills config integrates with full config."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[harness]
name = "test-harness"
version = "2.0"

[backend]
provider = "ollama"

[backend.ollama]
model = "test-model"

[skills]
directories = ["./skills", "/custom/skills"]
discovery = false
""")

    config = load_config(config_file)

    # Verify other sections work correctly
    assert config.harness.name == "test-harness"
    assert config.backend.ollama.model == "test-model"

    # Verify skills section
    assert config.skills.directories == ("./skills", "/custom/skills")
    assert config.skills.discovery is False

