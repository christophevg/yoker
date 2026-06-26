"""Test that plugin skills are loaded correctly and warnings are emitted."""

from unittest.mock import patch

from yoker.plugins.loader import _load_manifest_skills, load_plugin


def test_plugin_skills_are_loaded():
  """Test that skills from plugin manifest skills_dir are loaded."""
  # demo plugin has skills_dir="skills" with one skill:
  # - greeting (skills/greeting/SKILL.md)
  plugin = load_plugin("yoker_plugin_demo")

  # Plugin should have loaded the skill from skills_dir
  assert len(plugin.skills) == 1, (
    f"Expected 1 skill, got {len(plugin.skills)}: {[s.simple_name for s in plugin.skills]}"
  )

  # Check that skill has correct name
  skill = plugin.skills[0]
  assert skill.simple_name == "greeting", f"Expected skill 'greeting', got '{skill.simple_name}'"

  # Check that skill is properly namespaced
  assert skill.namespace == "yoker_plugin_demo", (
    f"Expected namespace 'yoker_plugin_demo', got '{skill.namespace}'"
  )


def test_plugin_skills_dir_not_exists_warning(capsys):
  """Test that warning is emitted when skills_dir is specified but directory doesn't exist."""
  # Create a mock manifest with skills_dir pointing to non-existent directory
  from types import SimpleNamespace

  # Mock manifest with skills_dir that doesn't exist
  manifest = SimpleNamespace(
    skills=[],
    skills_dir="nonexistent_directory",
  )

  # Mock find_package_subdirectory to return None (directory not found)
  with patch("yoker.plugins.loader.find_package_subdirectory", return_value=None):
    # Load skills from the manifest
    skills = _load_manifest_skills(manifest, "test_package")

    # Should return empty list
    assert skills == []

    # Check that warning was emitted to stdout (structlog uses PrintLogger)
    captured = capsys.readouterr()
    assert "plugin_skills_dir_not_found" in captured.out
    assert "test_package" in captured.out
    assert "nonexistent_directory" in captured.out


def test_plugin_skills_dir_exists_but_empty(caplog):
  """Test that no warning is emitted when skills_dir exists but is empty."""
  from pathlib import Path
  from types import SimpleNamespace

  # Mock manifest with skills_dir that exists but is empty
  manifest = SimpleNamespace(
    skills=[],
    skills_dir="empty_skills",
  )

  # Create a mock traversable that is a directory but has no skills
  mock_path = Path("/tmp/empty_skills")  # Will exist as a Path object

  # Mock find_package_subdirectory to return a path
  with patch("yoker.plugins.loader.find_package_subdirectory", return_value=mock_path):
    # Mock load_skills to return empty dict
    with patch("yoker.plugins.loader.load_skills", return_value={}):
      # Load skills from the manifest
      skills = _load_manifest_skills(manifest, "test_package")

      # Should return empty list
      assert skills == []

      # Should NOT emit a warning about skills_dir not found
      assert not any(
        "plugin_skills_dir_not_found" in record.message for record in caplog.records
      ), f"Should not warn when skills_dir exists, got: {[r.message for r in caplog.records]}"


def test_plugin_skills_inline():
  """Test that inline skills from manifest are loaded."""
  from types import SimpleNamespace

  from yoker.skills.schema import Skill

  # Create a manifest with inline skills only (no skills_dir)
  inline_skill = Skill(
    simple_name="inline_skill",
    description="An inline skill",
    content="Inline skill content",
    source_path="manifest",
    namespace="test_package",
  )

  manifest = SimpleNamespace(
    skills=[inline_skill],
    skills_dir=None,  # No skills_dir
  )

  # Load skills from the manifest
  skills = _load_manifest_skills(manifest, "test_package")

  # Should return the inline skill
  assert len(skills) == 1
  assert skills[0].simple_name == "inline_skill"


def test_plugin_skills_combined():
  """Test that inline skills and discovered skills are combined."""
  from pathlib import Path
  from types import SimpleNamespace

  from yoker.skills.schema import Skill

  # Create a manifest with both inline skills and skills_dir
  inline_skill = Skill(
    simple_name="inline_skill",
    description="An inline skill",
    content="Inline skill content",
    source_path="manifest",
    namespace="test_package",
  )

  manifest = SimpleNamespace(
    skills=[inline_skill],
    skills_dir="skills",
  )

  # Create a discovered skill
  discovered_skill = Skill(
    simple_name="discovered_skill",
    description="A discovered skill",
    content="Discovered skill content",
    source_path="/path/to/skills/discovered/SKILL.md",
    namespace="test_package",
  )

  # Mock find_package_subdirectory to return a path
  mock_path = Path("/tmp/skills")

  with patch("yoker.plugins.loader.find_package_subdirectory", return_value=mock_path):
    # Mock load_skills to return a skill
    with patch(
      "yoker.plugins.loader.load_skills", return_value={"discovered_skill": discovered_skill}
    ):
      # Load skills from the manifest
      skills = _load_manifest_skills(manifest, "test_package")

      # Should return both skills
      assert len(skills) == 2
      skill_names = {s.simple_name for s in skills}
      assert skill_names == {"inline_skill", "discovered_skill"}
