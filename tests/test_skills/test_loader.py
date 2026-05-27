"""Tests for skill loader."""

import os
from pathlib import Path

import pytest

from yoker.exceptions import ConfigurationError, FileNotFoundError
from yoker.skills.loader import (
  MAX_SKILL_SIZE_KB,
  load_skill,
  load_skills,
  load_skills_from_env,
  parse_skill_frontmatter,
)


class TestParseSkillFrontmatter:
  """Tests for parse_skill_frontmatter function."""

  def test_parse_valid_frontmatter(self) -> None:
    """Parse skill with valid YAML frontmatter."""
    content = """---
name: commit
description: Guide git commits
triggers:
  - commit these changes
  - create a commit
tools:
  - Bash
  - Read
---

# commit

Guide git commit operations.
"""
    frontmatter, body = parse_skill_frontmatter(content)

    assert frontmatter["name"] == "commit"
    assert frontmatter["description"] == "Guide git commits"
    assert frontmatter["triggers"] == ["commit these changes", "create a commit"]
    assert frontmatter["tools"] == ["Bash", "Read"]
    assert "# commit" in body
    assert "Guide git commit operations." in body

  def test_parse_minimal_frontmatter(self) -> None:
    """Parse skill with minimal frontmatter."""
    content = """---
name: test
description: A test skill
---

Test content
"""
    frontmatter, body = parse_skill_frontmatter(content)

    assert frontmatter["name"] == "test"
    assert frontmatter["description"] == "A test skill"
    assert "Test content" in body

  def test_parse_no_frontmatter(self) -> None:
    """Parse skill without frontmatter."""
    content = "# Test\n\nNo frontmatter here."
    frontmatter, body = parse_skill_frontmatter(content)

    assert frontmatter == {}
    assert content in body

  def test_parse_empty_frontmatter(self) -> None:
    """Parse skill with empty frontmatter."""
    content = """---
---

Test content
"""
    frontmatter, body = parse_skill_frontmatter(content)

    assert frontmatter == {}
    assert "Test content" in body

  def test_parse_invalid_yaml(self) -> None:
    """Parse skill with invalid YAML raises error."""
    content = """---
name: test
invalid yaml: [unterminated
---

Test content
"""
    with pytest.raises(ConfigurationError) as exc_info:
      parse_skill_frontmatter(content)

    assert "Invalid YAML in frontmatter" in str(exc_info.value)

  def test_parse_non_dict_frontmatter(self) -> None:
    """Parse skill with non-dict frontmatter raises error."""
    content = """---
- item1
- item2
---

Test content
"""
    with pytest.raises(ConfigurationError) as exc_info:
      parse_skill_frontmatter(content)

    assert "must be a YAML dictionary" in str(exc_info.value)


class TestLoadSkill:
  """Tests for load_skill function."""

  def test_load_skill_basic(self, tmp_path: Path) -> None:
    """Load a basic skill from file."""
    skill_file = tmp_path / "test.md"
    skill_file.write_text("""---
name: test-skill
description: A test skill for unit tests
---

# Test Skill

This is a test skill content.
""")

    skill = load_skill(skill_file)

    assert skill.name == "test-skill"
    assert skill.description == "A test skill for unit tests"
    assert "Test Skill" in skill.content
    assert skill.triggers == ()
    assert skill.tools == ()
    assert skill.source_path == str(skill_file)

  def test_load_skill_with_triggers(self, tmp_path: Path) -> None:
    """Load skill with trigger phrases."""
    skill_file = tmp_path / "trigger.md"
    skill_file.write_text("""---
name: commit
description: Guide commits
triggers:
  - commit these changes
  - create a commit
---

# commit

Commit guide.
""")

    skill = load_skill(skill_file)

    assert skill.name == "commit"
    assert skill.triggers == ("commit these changes", "create a commit")

  def test_load_skill_with_single_trigger(self, tmp_path: Path) -> None:
    """Load skill with single trigger (not list)."""
    skill_file = tmp_path / "trigger.md"
    skill_file.write_text("""---
name: test
description: Test
trigger: run this test
---

Content
""")

    skill = load_skill(skill_file)

    assert skill.triggers == ("run this test",)

  def test_load_skill_with_tools(self, tmp_path: Path) -> None:
    """Load skill with tools list."""
    skill_file = tmp_path / "tools.md"
    skill_file.write_text("""---
name: test
description: Test
tools:
  - Bash
  - Read
  - Write
---

Content
""")

    skill = load_skill(skill_file)

    assert skill.tools == ("Bash", "Read", "Write")

  def test_load_skill_with_comma_separated_tools(self, tmp_path: Path) -> None:
    """Load skill with comma-separated tools string."""
    skill_file = tmp_path / "tools.md"
    skill_file.write_text("""---
name: test
description: Test
tools: "Bash, Read, Write"
---

Content
""")

    skill = load_skill(skill_file)

    assert skill.tools == ("Bash", "Read", "Write")

  def test_load_skill_with_namespace(self, tmp_path: Path) -> None:
    """Load skill with namespace prefix."""
    skill_file = tmp_path / "ns.md"
    skill_file.write_text("""---
name: test
description: Test
---

Content
""")

    skill = load_skill(skill_file, namespace="pkg")

    assert skill.name == "test"
    assert skill.namespace == "pkg"
    assert skill.full_name == "pkg:test"

  def test_load_skill_full_name_no_namespace(self, tmp_path: Path) -> None:
    """Skill without namespace has simple full_name."""
    skill_file = tmp_path / "test.md"
    skill_file.write_text("""---
name: test
description: Test
---

Content
""")

    skill = load_skill(skill_file)

    assert skill.full_name == "test"

  def test_load_skill_file_not_found(self) -> None:
    """Load skill from non-existent file raises error."""
    with pytest.raises(FileNotFoundError) as exc_info:
      load_skill("/nonexistent/skill.md")

    assert "not found" in str(exc_info.value)

  def test_load_skill_missing_name(self, tmp_path: Path) -> None:
    """Load skill without name raises error."""
    skill_file = tmp_path / "bad.md"
    skill_file.write_text("""---
description: Test
---

Content
""")

    with pytest.raises(ConfigurationError) as exc_info:
      load_skill(skill_file)

    assert "name" in str(exc_info.value)

  def test_load_skill_missing_description(self, tmp_path: Path) -> None:
    """Load skill without description raises error."""
    skill_file = tmp_path / "bad.md"
    skill_file.write_text("""---
name: test
---

Content
""")

    with pytest.raises(ConfigurationError) as exc_info:
      load_skill(skill_file)

    assert "description" in str(exc_info.value)

  def test_load_skill_size_limit(self, tmp_path: Path) -> None:
    """Load skill exceeding size limit raises error."""
    skill_file = tmp_path / "large.md"
    # Create content larger than MAX_SKILL_SIZE_KB
    large_content = "x" * (MAX_SKILL_SIZE_KB * 1024 + 1)
    skill_file.write_text(f"""---
name: test
description: Test
---

{large_content}
""")

    with pytest.raises(ConfigurationError) as exc_info:
      load_skill(skill_file)

    assert "exceeds maximum size" in str(exc_info.value)

  def test_load_skill_path_validation(self, tmp_path: Path) -> None:
    """Load skill validates path against allowed directories."""
    skill_file = tmp_path / "test.md"
    skill_file.write_text("""---
name: test
description: Test
---

Content
""")

    # Loading with allowed_paths should work
    skill = load_skill(skill_file, allowed_paths=[str(tmp_path)])
    assert skill.name == "test"

    # Loading with disallowed path should fail
    with pytest.raises(ConfigurationError) as exc_info:
      load_skill(skill_file, allowed_paths=["/other/path"])

    assert "outside allowed directories" in str(exc_info.value)

  def test_load_skill_symlink_resolution(self, tmp_path: Path) -> None:
    """Load skill resolves symlinks before validation."""
    # Create actual file
    actual_file = tmp_path / "actual.md"
    actual_file.write_text("""---
name: test
description: Test
---

Content
""")

    # Create symlink
    symlink = tmp_path / "link.md"
    symlink.symlink_to(actual_file)

    # Should resolve symlink and validate
    skill = load_skill(symlink, allowed_paths=[str(tmp_path)])
    assert skill.name == "test"


class TestLoadSkills:
  """Tests for load_skills function."""

  def test_load_skills_directory(self, tmp_path: Path) -> None:
    """Load all skills from directory."""
    # Create multiple skill files
    (tmp_path / "skill1.md").write_text("""---
name: skill-one
description: First skill
---

Content 1
""")
    (tmp_path / "skill2.md").write_text("""---
name: skill-two
description: Second skill
---

Content 2
""")

    skills = load_skills(tmp_path)

    assert len(skills) == 2
    assert "skill-one" in skills
    assert "skill-two" in skills

  def test_load_skills_namespace(self, tmp_path: Path) -> None:
    """Load skills with namespace prefix."""
    (tmp_path / "test.md").write_text("""---
name: test
description: Test
---

Content
""")

    skills = load_skills(tmp_path, namespace="pkg")

    assert len(skills) == 1
    assert "pkg:test" in skills
    assert skills["pkg:test"].full_name == "pkg:test"

  def test_load_skills_duplicate_name(self, tmp_path: Path) -> None:
    """Load skills with duplicate names raises error."""
    (tmp_path / "first.md").write_text("""---
name: duplicate
description: First
---

Content 1
""")
    (tmp_path / "second.md").write_text("""---
name: duplicate
description: Second
---

Content 2
""")

    with pytest.raises(ConfigurationError) as exc_info:
      load_skills(tmp_path)

    assert "Duplicate" in str(exc_info.value)

  def test_load_skills_directory_not_found(self) -> None:
    """Load skills from non-existent directory raises error."""
    with pytest.raises(FileNotFoundError) as exc_info:
      load_skills("/nonexistent/dir")

    assert "not found" in str(exc_info.value)

  def test_load_skills_not_directory(self, tmp_path: Path) -> None:
    """Load skills from file (not directory) raises error."""
    skill_file = tmp_path / "file.md"
    skill_file.write_text("content")

    with pytest.raises(ConfigurationError) as exc_info:
      load_skills(skill_file)

    assert "not a directory" in str(exc_info.value)

  def test_load_skills_empty_directory(self, tmp_path: Path) -> None:
    """Load skills from empty directory returns empty dict."""
    skills = load_skills(tmp_path)
    assert skills == {}

  def test_load_skills_ignores_non_markdown(self, tmp_path: Path) -> None:
    """Load skills ignores non-markdown files."""
    (tmp_path / "skill.md").write_text("""---
name: test
description: Test
---

Content
""")
    (tmp_path / "data.txt").write_text("ignored")
    (tmp_path / "config.toml").write_text("ignored = true")

    skills = load_skills(tmp_path)

    assert len(skills) == 1
    assert "test" in skills


class TestLoadSkillsFromEnv:
  """Tests for load_skills_from_env function."""

  def test_load_skills_from_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Load skills from unset env var returns empty dict."""
    monkeypatch.delenv("YOKER_SKILLS_PATH", raising=False)

    skills = load_skills_from_env()

    assert skills == {}

  def test_load_skills_from_env_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Load skills from empty env var returns empty dict."""
    monkeypatch.setenv("YOKER_SKILLS_PATH", "")

    skills = load_skills_from_env()

    assert skills == {}

  def test_load_skills_from_env_single_path(
    self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
  ) -> None:
    """Load skills from single directory in env var."""
    (tmp_path / "test.md").write_text("""---
name: test
description: Test
---

Content
""")

    monkeypatch.setenv("YOKER_SKILLS_PATH", str(tmp_path))

    skills = load_skills_from_env()

    assert "test" in skills

  def test_load_skills_from_env_multiple_paths(
    self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
  ) -> None:
    """Load skills from multiple directories in env var."""
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()

    (dir1 / "a.md").write_text("""---
name: skill-a
description: Skill A
---

Content A
""")
    (dir2 / "b.md").write_text("""---
name: skill-b
description: Skill B
---

Content B
""")

    monkeypatch.setenv("YOKER_SKILLS_PATH", f"{dir1}{os.pathsep}{dir2}")

    skills = load_skills_from_env()

    assert "skill-a" in skills
    assert "skill-b" in skills

  def test_load_skills_from_env_custom_var(
    self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
  ) -> None:
    """Load skills from custom env var name."""
    (tmp_path / "test.md").write_text("""---
name: test
description: Test
---

Content
""")

    monkeypatch.setenv("CUSTOM_SKILLS", str(tmp_path))

    skills = load_skills_from_env(env_var="CUSTOM_SKILLS")

    assert "test" in skills

  def test_load_skills_from_env_ignores_invalid_paths(
    self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
  ) -> None:
    """Load skills ignores invalid paths in env var."""
    (tmp_path / "test.md").write_text("""---
name: test
description: Test
---

Content
""")

    # Mix of valid and invalid paths
    monkeypatch.setenv(
      "YOKER_SKILLS_PATH", f"/nonexistent{os.pathsep}{tmp_path}{os.pathsep}/also/nonexistent"
    )

    skills = load_skills_from_env()

    # Should still load from valid path
    assert "test" in skills
